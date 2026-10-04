from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
import json

from ..intermediate import IntermediateRecord, PreparedSource, canonical_json, sha256_file
from ..settings import MemoryRebuildSettings
from ..source_detection import SourceProbe, load_json_strict
from .common import stable_key


def _analysis_rows(path: Path) -> Iterator[dict[str, Any]]:
    value = load_json_strict(path)
    if isinstance(value, dict) and isinstance(value.get("analizy"), list):
        source = value["analizy"]
    elif isinstance(value, list):
        source = value
    elif isinstance(value, dict) and value and all(isinstance(item, dict) for item in value.values()):
        source = [dict(item, _source_key=str(key)) for key, item in value.items()]
    elif isinstance(value, dict):
        source = [value]
    else:
        raise ValueError("Analizy utworów muszą być obiektem lub listą obiektów JSON.")
    for item in source:
        if isinstance(item, dict):
            yield item


def _affect_claims(raw: dict[str, Any]) -> list[dict[str, str]]:
    value = raw.get("emocje") if raw.get("emocje") not in (None, "") else raw.get("emotions")
    if isinstance(value, str):
        labels = [item.strip(" .") for item in value.split(",") if item.strip(" .")]
    elif isinstance(value, list):
        labels = [str(item).strip() for item in value if str(item).strip()]
    else:
        labels = []
    source_field = "emocje" if raw.get("emocje") not in (None, "") else "emotions"
    return [
        {
            "label": label,
            "source_field": source_field,
            "claim_kind": "explicit_source_label",
            "subject": "latka",
            "boundary": "source_claimed_affect_not_biological_state",
        }
        for label in labels
    ]


def _text(raw: dict[str, Any]) -> tuple[str, str]:
    title = str(
        raw.get("tytuł") or raw.get("tytul") or raw.get("title")
        or raw.get("utwór") or raw.get("utwor") or raw.get("song")
        or raw.get("nazwa") or raw.get("_source_key") or "Analiza utworu"
    ).strip()
    fields = (
        "analiza", "analysis", "opis", "description", "tekst", "lyrics", "summary",
        "interpretacja", "motywy", "emocje", "emotions", "wnioski", "notes",
        "styl_gatunek", "tematyka", "zwiazek_z_ksiazka", "związek_z_książką",
        "lustro_emocji_latki", "refleksja_latki", "moje_odczucia_latki",
        "notatka_introspekcyjna", "podsumowanie",
    )
    fragments = [f"{name}: {raw[name]}" for name in fields if raw.get(name) not in (None, "", [], {})]
    return title, "\n".join(fragments) if fragments else canonical_json(raw)


class MusicAnalysisAdapter:
    adapter_id = "music-analysis/v16.1"

    def supports(self, path: Path, probe: SourceProbe) -> bool:
        return probe.kind == "music" and path.suffix.casefold() == ".json"

    def prepare(
        self, path: Path, probe: SourceProbe, settings: MemoryRebuildSettings,
    ) -> PreparedSource:
        del probe, settings

        def records():
            for raw in _analysis_rows(path):
                title, content = _text(raw)
                logical_key = stable_key(
                    "music-analysis",
                    raw,
                    ("id", "analysis_id", "uuid", "_source_key", "tytuł", "tytul", "title", "utwór", "utwor", "song"),
                )
                source_id = str(raw.get("id") or raw.get("analysis_id") or raw.get("uuid") or logical_key)
                event = str(raw.get("timestamp") or raw.get("data") or raw.get("date") or "").strip() or None
                raw_record = dict(raw)
                raw_record["__jazn_affect_claims__"] = _affect_claims(raw)
                raw_record["__jazn_affect_boundary__"] = (
                    "source_claimed_affect_not_biological_state"
                )
                yield IntermediateRecord(
                    logical_key=logical_key,
                    source_record_id=source_id,
                    record_kind="music_analysis",
                    title=title,
                    content=content,
                    event_time_start=event,
                    event_time_end=event,
                    timestamp_status="source_recorded" if event else "missing",
                    truth_status="source_recorded",
                    importance=float(raw.get("importance", 0.6) or 0.6),
                    raw=raw_record,
                    provenance={
                        "analysis_title": title,
                        "claim_boundary": "assistant_claim",
                        "affect_boundary": "source_claimed_affect_not_biological_state",
                        "affect_claim_fields": sorted({
                            item["source_field"]
                            for item in raw_record["__jazn_affect_claims__"]
                        }),
                    },
                )

        return PreparedSource(
            adapter_id=self.adapter_id,
            source_kind="music_analysis",
            source_sha256=sha256_file(path),
            source_name=path.name,
            source_member=None,
            metadata={"logical_collection": "music_analysis_current"},
            record_factory=records,
            native_projection="l0_only",
        )


__all__ = ["MusicAnalysisAdapter"]
