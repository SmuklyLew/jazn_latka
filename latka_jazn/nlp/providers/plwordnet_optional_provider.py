from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from latka_jazn.nlp.providers.base import ProviderLookupResult


class PlWordNetOptionalProvider:
    """Read-only adapter for an explicitly provisioned local plWordNet index.

    The runtime never downloads or redistributes plWordNet automatically.  A
    local resource can be provisioned as ``resources/plwordnet/index.sqlite3``
    with a simple ``lexical_entries`` table.  This keeps the core source small
    while making semantic relations available when a licensed resource exists.
    """

    name = "plwordnet_optional"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.resource_dir = self.root / "resources" / "plwordnet"
        self.index_path = self.resource_dir / "index.sqlite3"
        self.metadata_path = self.resource_dir / "resource.json"

    def _metadata(self) -> dict[str, object]:
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _table_available(connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lexical_entries'"
        ).fetchone()
        return row is not None

    def lookup(self, term: str, language: str = "pl") -> ProviderLookupResult:
        now = datetime.now(timezone.utc).isoformat()
        if language != "pl":
            return ProviderLookupResult(
                self.name,
                "language_not_supported",
                term,
                language,
                error="plWordNet provider supports Polish resources.",
                retrieved_at_utc=now,
            )
        if not self.resource_dir.exists():
            return ProviderLookupResult(
                self.name,
                "provider_unavailable",
                term,
                language,
                error="No local plWordNet resource directory; Jaźń does not download large resources at startup.",
                retrieved_at_utc=now,
                license_hint="Check plWordNet/Słowosieć license before distributing imported data.",
            )
        if not self.index_path.is_file():
            return ProviderLookupResult(
                self.name,
                "resource_present_not_indexed",
                term,
                language,
                error="Local resource is present but resources/plwordnet/index.sqlite3 is missing.",
                retrieved_at_utc=now,
                license_hint=str(self._metadata().get("license_note") or "Check local plWordNet resource license."),
            )
        metadata = self._metadata()
        try:
            uri = f"file:{self.index_path.resolve().as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
            connection.row_factory = sqlite3.Row
            try:
                if not self._table_available(connection):
                    return ProviderLookupResult(
                        self.name,
                        "index_schema_unsupported",
                        term,
                        language,
                        error="lexical_entries table missing in local plWordNet index.",
                        retrieved_at_utc=now,
                        license_hint=str(metadata.get("license_note") or "Check local plWordNet resource license."),
                    )
                rows = connection.execute(
                    """
                    SELECT term, lemma, pos, definition, relations_json, source_version
                    FROM lexical_entries
                    WHERE lower(term)=lower(?) OR lower(lemma)=lower(?)
                    ORDER BY CASE WHEN lower(term)=lower(?) THEN 0 ELSE 1 END, lemma
                    LIMIT 24
                    """,
                    (term, term, term),
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            return ProviderLookupResult(
                self.name,
                "provider_error",
                term,
                language,
                error=f"{type(exc).__name__}:{exc}",
                retrieved_at_utc=now,
                license_hint=str(metadata.get("license_note") or "Check local plWordNet resource license."),
            )

        lemmas: list[str] = []
        poses: list[str] = []
        definitions: list[str] = []
        relations: dict[str, list[str]] = {}
        source_versions: list[str] = []
        for row in rows:
            lemma = str(row["lemma"] or "").strip()
            pos = str(row["pos"] or "").strip()
            definition = str(row["definition"] or "").strip()
            source_version = str(row["source_version"] or "").strip()
            if lemma and lemma not in lemmas:
                lemmas.append(lemma)
            if pos and pos not in poses:
                poses.append(pos)
            if definition and definition not in definitions:
                definitions.append(definition)
            if source_version and source_version not in source_versions:
                source_versions.append(source_version)
            try:
                row_relations = json.loads(str(row["relations_json"] or "{}"))
            except json.JSONDecodeError:
                row_relations = {}
            if isinstance(row_relations, dict):
                for key, values in row_relations.items():
                    if not isinstance(values, list):
                        continue
                    target = relations.setdefault(str(key), [])
                    for value in values:
                        item = str(value).strip()
                        if item and item not in target:
                            target.append(item)

        return ProviderLookupResult(
            self.name,
            "ok" if rows else "not_found",
            term,
            language,
            lemmas=lemmas,
            part_of_speech=poses,
            definitions=definitions,
            retrieved_at_utc=now,
            confidence=0.88 if rows else 0.0,
            license_hint=str(metadata.get("license_note") or "Local plWordNet resource; verify license/provenance before redistribution."),
            raw={
                "relations": relations,
                "source_versions": source_versions,
                "index_path": str(self.index_path),
                "read_only": True,
            },
        )
