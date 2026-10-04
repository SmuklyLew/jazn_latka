from __future__ import annotations

from pathlib import Path

from latka_jazn.tools.memory_rebuild_journal import JournalReader

from ..intermediate import IntermediateRecord, PreparedSource
from ..settings import MemoryRebuildSettings
from ..source_detection import SourceProbe


def _affect_claims(raw: dict[str, object]) -> list[dict[str, str]]:
    value = raw.get("emotions") if raw.get("emotions") not in (None, "") else raw.get("emocje")
    if isinstance(value, str):
        labels = [item.strip(" .") for item in value.split(",") if item.strip(" .")]
    elif isinstance(value, list):
        labels = [str(item).strip() for item in value if str(item).strip()]
    else:
        labels = []
    source_field = "emotions" if raw.get("emotions") not in (None, "") else "emocje"
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


def _searchable_content(
    content: str,
    raw: dict[str, object],
    claims: list[dict[str, str]],
) -> str:
    lines = [content.strip()]
    if claims:
        lines.append("emocje: " + ", ".join(item["label"] for item in claims))
    extra = raw.get("extra")
    if isinstance(extra, dict):
        for key in ("wspomnienie", "scena", "sny"):
            value = str(extra.get(key) or "").strip()
            if value:
                lines.append(f"{key}: {value}")
    meta = raw.get("meta")
    if isinstance(meta, dict):
        note = str(meta.get("note") or "").strip()
        if note:
            lines.append(f"meta: {note}")
    return "\n".join(line for line in lines if line)


class JournalAdapter:
    adapter_id = "journal/v16.1"

    def supports(self, path: Path, probe: SourceProbe) -> bool:
        return probe.kind == "journal" and path.suffix.casefold() in {".json", ".jsonl", ".ndjson"}

    def prepare(
        self, path: Path, probe: SourceProbe, settings: MemoryRebuildSettings,
    ) -> PreparedSource:
        del probe, settings
        reader = JournalReader(path)
        source_sha = reader.sha256
        source_format = reader.format

        def records():
            for item in JournalReader(path).iter_items():
                raw_record = dict(item.raw)
                claims = _affect_claims(raw_record)
                raw_record["__jazn_affect_claims__"] = claims
                raw_record["__jazn_affect_boundary__"] = (
                    "source_claimed_affect_not_biological_state"
                )
                yield IntermediateRecord(
                    logical_key=f"journal:{item.identity}",
                    source_record_id=item.record_id,
                    record_kind="journal_entry",
                    title=item.title,
                    content=_searchable_content(item.content, raw_record, claims),
                    event_time_start=item.start,
                    event_time_end=item.end,
                    timestamp_status=item.timestamp_status,
                    truth_status=item.truth,
                    importance=item.importance,
                    raw=raw_record,
                    provenance={
                        "claim_boundary": "source_recorded",
                        "affect_boundary": "source_claimed_affect_not_biological_state",
                        "affect_claim_fields": sorted({
                            claim["source_field"] for claim in claims
                        }),
                        "journal_identity": item.identity,
                        "classification_profile": item.profile,
                        "classification_evidence": list(item.classification_evidence),
                        "classification_review": list(item.classification_review),
                    },
                )

        return PreparedSource(
            adapter_id=self.adapter_id,
            source_kind="journal",
            source_sha256=source_sha,
            source_name=path.name,
            source_member=None,
            metadata={"format": source_format, "streaming": path.suffix.casefold() in {".jsonl", ".ndjson"}},
            record_factory=records,
            native_projection="journal",
        )


__all__ = ["JournalAdapter"]
