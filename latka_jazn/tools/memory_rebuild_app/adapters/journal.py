from __future__ import annotations

from pathlib import Path

from latka_jazn.tools.memory_rebuild_journal import JournalReader

from ..intermediate import IntermediateRecord, PreparedSource
from ..settings import MemoryRebuildSettings
from ..source_detection import SourceProbe


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
                yield IntermediateRecord(
                    logical_key=f"journal:{item.identity}",
                    source_record_id=item.record_id,
                    record_kind="journal_entry",
                    title=item.title,
                    content=item.content,
                    event_time_start=item.start,
                    event_time_end=item.end,
                    timestamp_status=item.timestamp_status,
                    truth_status=item.truth,
                    importance=item.importance,
                    raw=item.raw,
                    provenance={
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
