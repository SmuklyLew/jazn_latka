from __future__ import annotations

from pathlib import Path

from latka_jazn.tools.chat_export_reader import build_conversation_graph

from ..html_import import read_html_conversations
from ..intermediate import PreparedSource, sha256_file
from ..settings import MemoryRebuildSettings
from ..source_detection import SourceProbe
from .common import conversation_records


class ChatHtmlAdapter:
    adapter_id = "chat-html/v16.1"

    def supports(self, path: Path, probe: SourceProbe) -> bool:
        return (
            probe.kind == "chat"
            and path.suffix.casefold() in {".html", ".htm", ".zip"}
            and (path.suffix.casefold() != ".zip" or "explicit_chat_html" in " ".join(probe.reasons))
        )

    def prepare(
        self, path: Path, probe: SourceProbe, settings: MemoryRebuildSettings,
    ) -> PreparedSource:
        del probe, settings
        _, member, mode, warnings = read_html_conversations(path)

        def records():
            raw, _, _, _ = read_html_conversations(path)
            yield from conversation_records(build_conversation_graph(item) for item in raw)

        return PreparedSource(
            adapter_id=self.adapter_id,
            source_kind="chatgpt_conversation",
            source_sha256=sha256_file(path),
            source_name=path.name,
            source_member=member,
            metadata={"mode": mode, "warnings": list(warnings)},
            record_factory=records,
            native_projection="html",
        )


__all__ = ["ChatHtmlAdapter"]
