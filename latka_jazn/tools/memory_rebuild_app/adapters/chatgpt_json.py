from __future__ import annotations

from pathlib import Path

from latka_jazn.tools.chat_export_reader import ChatExportReader

from ..intermediate import PreparedSource
from ..settings import MemoryRebuildSettings
from ..source_detection import SourceProbe
from .common import conversation_records


class ChatGptJsonAdapter:
    adapter_id = "chatgpt-json/v16.1"

    def supports(self, path: Path, probe: SourceProbe) -> bool:
        if path.is_dir():
            return True
        return probe.kind == "chat" and path.suffix.casefold() in {".json", ".zip"}

    def prepare(
        self, path: Path, probe: SourceProbe, settings: MemoryRebuildSettings,
    ) -> PreparedSource:
        del probe, settings
        with ChatExportReader(path) as reader:
            info = reader.info

        def records():
            with ChatExportReader(path) as source:
                yield from conversation_records(source.iter_graphs())

        return PreparedSource(
            adapter_id=self.adapter_id,
            source_kind="chatgpt_conversation",
            source_sha256=info.sha256,
            source_name=path.name,
            source_member=info.conversations_member,
            metadata={
                "source_kind": info.source_kind,
                "size_bytes": info.size_bytes,
                "crc_checked": info.crc_checked,
                "crc_ok": info.crc_ok,
                "conversation_members": list(info.conversation_members),
            },
            record_factory=records,
            native_projection="chatgpt",
        )


__all__ = ["ChatGptJsonAdapter"]
