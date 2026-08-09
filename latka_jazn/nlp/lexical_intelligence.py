from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from latka_jazn.nlp.polish_lexical_sources import MINI_LEXICON
from latka_jazn.nlp.providers.optional_morfeusz_provider import OptionalMorfeuszProvider
from latka_jazn.nlp.providers.plwordnet_optional_provider import PlWordNetOptionalProvider
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("lexical_intelligence")
CACHE_SCHEMA_VERSION = "lexical_intelligence_cache/v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


@dataclass(slots=True)
class LexicalEvidence:
    source: str
    status: str
    term: str
    lemmas: list[str] = field(default_factory=list)
    part_of_speech: list[str] = field(default_factory=list)
    definitions: list[str] = field(default_factory=list)
    semantic_relations: dict[str, list[str]] = field(default_factory=dict)
    confidence: float = 0.0
    license_note: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LexicalAnalysis:
    term: str
    normalized_term: str
    context: str
    evidence: list[LexicalEvidence]
    preferred_lemmas: list[str]
    context_disambiguation_required: bool
    cache_hit: bool = False
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Analiza leksykalna zachowuje źródło i licencję każdego wyniku. Morfeusz zwraca możliwe analizy "
        "fleksyjne, ale sam nie rozstrzyga znaczenia na podstawie kontekstu; brak lokalnego zasobu semantycznego "
        "nie może być uzupełniany zmyśloną definicją."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LexicalCache:
    """Small rebuildable cache; not a source of lexical truth by itself."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS lexical_cache(
                  cache_key TEXT PRIMARY KEY,
                  term TEXT NOT NULL,
                  context_hash TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  source_versions_json TEXT NOT NULL,
                  created_at_utc TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def key(term: str, context: str, source_versions: dict[str, str]) -> str:
        material = json.dumps(
            {"term": _norm(term), "context": _norm(context), "sources": source_versions},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT payload_json FROM lexical_cache WHERE cache_key=?", (key,)).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(str(row[0]))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def put(self, key: str, *, term: str, context: str, payload: dict[str, Any], source_versions: dict[str, str]) -> None:
        context_hash = hashlib.sha256(_norm(context).encode("utf-8")).hexdigest()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO lexical_cache(cache_key,term,context_hash,payload_json,source_versions_json,created_at_utc)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(cache_key) DO UPDATE SET
                  payload_json=excluded.payload_json,
                  source_versions_json=excluded.source_versions_json,
                  created_at_utc=excluded.created_at_utc
                """,
                (
                    key,
                    _norm(term),
                    context_hash,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(source_versions, ensure_ascii=False, sort_keys=True),
                    _utc_now(),
                ),
            )


class LexicalIntelligenceEngine:
    def __init__(
        self,
        *,
        root: Path | None = None,
        cache_path: Path | None = None,
        enable_morfeusz: bool = True,
    ) -> None:
        self.root = Path(root) if root is not None else Path.cwd()
        self.morfeusz = OptionalMorfeuszProvider() if enable_morfeusz else None
        self.plwordnet = PlWordNetOptionalProvider(self.root)
        self.cache = LexicalCache(cache_path) if cache_path else None

    def source_versions(self) -> dict[str, str]:
        return {
            "builtin": "local_jazn_mini_lexicon/v1",
            "morfeusz": "available" if self.morfeusz and self.morfeusz.available else "unavailable",
            "plwordnet": "local-index-if-present/v1",
        }

    def analyse(self, term: str, *, context: str = "", language: str = "pl") -> LexicalAnalysis:
        normalized = _norm(term)
        source_versions = self.source_versions()
        cache_key = LexicalCache.key(normalized, context, source_versions)
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                evidence = [LexicalEvidence(**item) for item in cached.get("evidence", []) if isinstance(item, dict)]
                return LexicalAnalysis(
                    term=term,
                    normalized_term=normalized,
                    context=context,
                    evidence=evidence,
                    preferred_lemmas=[str(item) for item in cached.get("preferred_lemmas", [])],
                    context_disambiguation_required=bool(cached.get("context_disambiguation_required")),
                    cache_hit=True,
                )

        evidence: list[LexicalEvidence] = []
        builtin = MINI_LEXICON.get(normalized)
        if isinstance(builtin, dict):
            evidence.append(
                LexicalEvidence(
                    source=str(builtin.get("source") or "local_jazn_mini_lexicon"),
                    status="ok",
                    term=normalized,
                    lemmas=[str(item) for item in builtin.get("lemma", [])],
                    definitions=[str(item) for item in builtin.get("definitions", [])],
                    confidence=0.96,
                    license_note="project-owned domain lexicon",
                    provenance={"resource": "latka_jazn.nlp.polish_lexical_sources.MINI_LEXICON"},
                )
            )

        if self.morfeusz is not None:
            morfeusz_result = self.morfeusz.lookup(normalized, language=language)
            evidence.append(
                LexicalEvidence(
                    source=self.morfeusz.name,
                    status=morfeusz_result.status,
                    term=normalized,
                    lemmas=list(morfeusz_result.lemmas),
                    part_of_speech=list(morfeusz_result.part_of_speech),
                    confidence=float(morfeusz_result.confidence or 0.0),
                    license_note="Morfeusz2/SGJP resource; distribution rules must be checked before bundling derived data",
                    provenance={"retrieved_at_utc": morfeusz_result.retrieved_at_utc, "error": morfeusz_result.error},
                )
            )

        plwordnet_result = self.plwordnet.lookup(normalized, language=language)
        relations = {}
        raw = plwordnet_result.raw if isinstance(plwordnet_result.raw, dict) else {}
        if isinstance(raw.get("relations"), dict):
            relations = {
                str(key): [str(item) for item in value if str(item).strip()]
                for key, value in raw["relations"].items()
                if isinstance(value, list)
            }
        evidence.append(
            LexicalEvidence(
                source=self.plwordnet.name,
                status=plwordnet_result.status,
                term=normalized,
                lemmas=list(plwordnet_result.lemmas),
                definitions=list(plwordnet_result.definitions),
                semantic_relations=relations,
                confidence=float(plwordnet_result.confidence or 0.0),
                license_note=plwordnet_result.license_hint,
                provenance={"retrieved_at_utc": plwordnet_result.retrieved_at_utc, "error": plwordnet_result.error},
            )
        )

        lemma_scores: dict[str, float] = {}
        for item in evidence:
            for lemma in item.lemmas:
                lemma_scores[lemma] = max(lemma_scores.get(lemma, 0.0), item.confidence)
        preferred = [item for item, _ in sorted(lemma_scores.items(), key=lambda pair: (-pair[1], pair[0]))]
        ambiguity = len(preferred) > 1 and bool(context.strip())
        result = LexicalAnalysis(
            term=term,
            normalized_term=normalized,
            context=context,
            evidence=evidence,
            preferred_lemmas=preferred[:8],
            context_disambiguation_required=ambiguity,
        )
        if self.cache:
            payload = result.to_dict()
            payload.pop("cache_hit", None)
            self.cache.put(cache_key, term=normalized, context=context, payload=payload, source_versions=source_versions)
        return result
