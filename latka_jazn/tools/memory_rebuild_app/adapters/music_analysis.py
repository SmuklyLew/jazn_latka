from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
import json

from ..intermediate import IntermediateRecord, PreparedSource, canonical_json, sha256_file
from ..settings import MemoryRebuildSettings
from ..source_detection import SourceProbe
from .common import stable_key


def _analysis_rows(path: Path) -> Iterator[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
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


def _text(raw: dict[str, Any]) -> tuple[str, str]:
    title = str(
        raw.get("tytuł") or raw.get("tytul") or raw.get("title")
        or raw.get("utwór") or raw.get("utwor") or raw.get("song")
        or raw.get("nazwa") or raw.get("_source_key") or "Analiza utworu"
    ).strip()
    fields = (
        "analiza", "analysis", "opis", "description", "tekst", "lyrics", "summary",
        "interpretacja", "motywy", "emocje", "wnioski", "notes",
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
                    raw=raw,
                    provenance={"analysis_title": title},
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
