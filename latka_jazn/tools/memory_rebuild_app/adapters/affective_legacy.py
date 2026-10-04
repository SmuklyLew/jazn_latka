from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Mapping
import hashlib

from ..intermediate import IntermediateRecord, PreparedSource, canonical_json, sha256_file
from ..settings import MemoryRebuildSettings
from ..source_detection import SourceProbe, load_legacy_affective_json


_AFFECT_KEYS = ("emocje", "emotions", "feelings", "uczucia", "affect")
_TEXT_KEYS = (
    "opis", "description", "content", "tekst", "text", "meta", "znaczenie",
    "rola", "poczucie_wiez", "poczucie_więzi", "wpływ_na_mnie", "wplyw_na_mnie",
    "obserwacja", "refleksja",
    "notatka", "podsumowanie",
)


def _labels(raw: Mapping[str, Any]) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    for field in _AFFECT_KEYS:
        value = raw.get(field)
        if isinstance(value, str):
            values = [item.strip(" .") for item in value.split(",") if item.strip(" .")]
        elif isinstance(value, (list, tuple, set)):
            values = [str(item).strip() for item in value if str(item).strip()]
        else:
            values = []
        for label in values:
            claims.append({
                "label": label,
                "source_field": field,
                "claim_kind": "explicit_source_label",
                "subject": "latka",
                "boundary": "source_claimed_affect_not_biological_state",
            })
    return claims


def _content(raw: Mapping[str, Any]) -> str:
    lines: list[str] = []
    for key in _TEXT_KEYS:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{key}: {value.strip()}")
        elif isinstance(value, list):
            values = [str(item).strip() for item in value if str(item).strip()]
            if values:
                lines.append(f"{key}: " + " | ".join(values))
    labels = _labels(raw)
    if labels:
        lines.append("emocje: " + ", ".join(item["label"] for item in labels))
    return "\n".join(lines) or canonical_json(dict(raw))


def _event(raw: Mapping[str, Any]) -> str | None:
    for key in ("datetime", "timestamp", "data", "date"):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return None


def _record(
    source_path: str,
    record_kind: str,
    title: str,
    value: Any,
    *,
    subject: str = "latka",
) -> IntermediateRecord:
    raw: dict[str, Any] = dict(value) if isinstance(value, Mapping) else {"value": value}
    claims = _labels(raw)
    raw["__jazn_affect_claims__"] = claims
    raw["__jazn_affect_boundary__"] = "source_claimed_affect_not_biological_state"
    raw["__jazn_source_path__"] = source_path
    rendered = _content(raw) if isinstance(value, Mapping) else str(value).strip()
    if not rendered:
        rendered = canonical_json(raw)
    digest = hashlib.sha256(
        canonical_json({"source_path": source_path, "raw": raw}).encode("utf-8")
    ).hexdigest()
    event = _event(raw)
    return IntermediateRecord(
        logical_key=f"affective:{digest}",
        source_record_id=source_path,
        record_kind=record_kind,
        title=title,
        content=rendered,
        event_time_start=event,
        event_time_end=event,
        timestamp_status="source_recorded" if event else "missing",
        role="assistant",
        truth_status="source_recorded",
        importance=0.75,
        raw=raw,
        provenance={
            "source_path": source_path,
            "affect_subject": subject,
            "claim_boundary": "assistant_claim",
            "affect_boundary": "source_claimed_affect_not_biological_state",
            "affect_claim_fields": sorted({
                item["source_field"] for item in claims
            }),
        },
    )


def _iter_records(payload: Mapping[str, Any]) -> Iterator[IntermediateRecord]:
    latka = payload.get("latka_ai_pamiec")
    if isinstance(latka, Mapping):
        for section, value in latka.items():
            if section == "meta":
                continue
            if isinstance(value, list):
                for index, item in enumerate(value):
                    yield _record(
                        f"latka_ai_pamiec.{section}[{index}]",
                        "affective_memory",
                        f"Łatka — {section}",
                        item,
                    )
            elif isinstance(value, Mapping):
                yield _record(
                    f"latka_ai_pamiec.{section}",
                    "affective_memory",
                    f"Łatka — {section}",
                    value,
                )
            elif isinstance(value, str) and value.strip():
                yield _record(
                    f"latka_ai_pamiec.{section}",
                    "affective_memory",
                    f"Łatka — {section}",
                    value,
                )

    quiet = payload.get("pytania_z_ciszy")
    if isinstance(quiet, list):
        for index, item in enumerate(quiet):
            if isinstance(item, str) and item.strip():
                yield _record(
                    f"pytania_z_ciszy[{index}]",
                    "quiet_question",
                    "Pytanie z ciszy",
                    item,
                )

    relations = payload.get("relacje")
    if isinstance(relations, Mapping):
        for name, item in relations.items():
            if isinstance(item, Mapping):
                yield _record(
                    f"relacje.{name}",
                    "relationship_affect",
                    f"Relacja — {name}",
                    item,
                    subject="latka",
                )

    projects = payload.get("projekty_meta")
    if isinstance(projects, Mapping):
        for section, value in projects.items():
            if isinstance(value, list):
                for index, item in enumerate(value):
                    yield _record(
                        f"projekty_meta.{section}[{index}]",
                        "affective_reflection",
                        f"Projekt / refleksja — {section}",
                        item,
                    )


class LegacyAffectiveJsonAdapter:
    adapter_id = "affective-legacy-json/v16.3.25.5.104"

    def supports(self, path: Path, probe: SourceProbe) -> bool:
        return probe.kind == "affective" and path.suffix.casefold() == ".json"

    def prepare(
        self, path: Path, probe: SourceProbe, settings: MemoryRebuildSettings,
    ) -> PreparedSource:
        del probe, settings
        payload, recovery = load_legacy_affective_json(path)
        if not isinstance(payload, Mapping):
            raise ValueError("Affective legacy JSON must be a top-level object.")
        records = list(_iter_records(payload))
        if not records:
            raise ValueError("Affective legacy JSON contains no recognized affective records.")

        def record_factory() -> Iterator[IntermediateRecord]:
            yield from records

        return PreparedSource(
            adapter_id=self.adapter_id,
            source_kind="affective",
            source_sha256=sha256_file(path),
            source_name=path.name,
            source_member=None,
            metadata={
                "logical_collection": "legacy_affective_memory",
                "record_count": len(records),
                "truth_boundary": "source_claimed_affect_not_biological_state",
                "legacy_json_recovery": recovery,
                "automatic_promotion": False,
            },
            record_factory=record_factory,
            native_projection="l0_only",
        )


__all__ = ["LegacyAffectiveJsonAdapter"]
