from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import re
import uuid
import zipfile

from latka_jazn.tools.chat_export_dedupe import plan_conversation
from latka_jazn.tools.chat_export_reader import build_conversation_graph, sha256_file
from latka_jazn.tools.chat_export_store import ChatExportArchiveStore

from .html_semantics import HtmlEmbeddedJsonParser, HtmlParseMode

_JSON_ASSIGNMENT_RE = re.compile(r"(?:var|let|const)\s+jsonData\s*=", re.IGNORECASE)


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _decode_assignment(text: str) -> Any | None:
    match = _JSON_ASSIGNMENT_RE.search(text)
    if not match:
        return None
    decoder = json.JSONDecoder()
    index = match.end()
    while index < len(text) and text[index].isspace():
        index += 1
    value, _ = decoder.raw_decode(text, index)
    return value


def _conversation_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict) and isinstance(item.get("mapping"), dict)]
    if isinstance(value, dict):
        for key in ("conversations", "items", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                found = _conversation_records(nested)
                if found:
                    return found
        if isinstance(value.get("mapping"), dict):
            return [value]
    return []


class _RenderedConversationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_conversation = False
        self._capture_title = False
        self._capture_message = False
        self._title: list[str] = []
        self._message: list[str] = []
        self._messages: list[str] = []
        self._conversation_depth = 0
        self.conversations: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        classes = set(attr.get("class", "").split())
        if tag.lower() == "div" and "conversation" in classes and not self._in_conversation:
            self._in_conversation = True
            self._conversation_depth = 1
            self._title = []
            self._messages = []
        elif self._in_conversation and tag.lower() == "div":
            self._conversation_depth += 1
        elif self._in_conversation and tag.lower() == "h4":
            self._capture_title = True
        elif self._in_conversation and tag.lower() == "pre" and "message" in classes:
            self._capture_message = True
            self._message = []

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower == "h4" and self._capture_title:
            self._capture_title = False
        elif lower == "pre" and self._capture_message:
            self._capture_message = False
            message = "".join(self._message).strip()
            if message:
                self._messages.append(message)
        elif lower == "div" and self._in_conversation:
            self._conversation_depth -= 1
            if self._conversation_depth <= 0:
                title = "".join(self._title).strip() or "Rozmowa z HTML"
                if self._messages:
                    self.conversations.append((title, list(self._messages)))
                self._in_conversation = False
                self._conversation_depth = 0

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title.append(data)
        if self._capture_message:
            self._message.append(data)


def _synthetic_conversation(title: str, messages: Iterable[str], *, source_key: str, ordinal: int) -> dict[str, Any]:
    conversation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"jazn-html:{source_key}:{ordinal}:{title}"))
    mapping: dict[str, Any] = {}
    parent: str | None = None
    current: str | None = None
    for index, text in enumerate(messages):
        node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{conversation_id}:node:{index}:{text}"))
        message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{conversation_id}:message:{index}:{text}"))
        role = "user" if index % 2 == 0 else "assistant"
        mapping[node_id] = {
            "id": node_id,
            "parent": parent,
            "children": [],
            "message": {
                "id": message_id,
                "author": {"role": role},
                "create_time": None,
                "content": {"content_type": "text", "parts": [text]},
                "metadata": {"source": "rendered_html_fallback"},
            },
        }
        if parent is not None:
            mapping[parent]["children"].append(node_id)
        parent = node_id
        current = node_id
    return {
        "id": conversation_id,
        "title": title,
        "create_time": None,
        "update_time": None,
        "current_node": current,
        "mapping": mapping,
        "metadata": {"source": "rendered_html_fallback"},
    }


def _read_html_source(path: Path) -> tuple[str, str]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as archive:
            names = [name for name in archive.namelist() if name.lower().endswith((".html", ".htm"))]
            if not names:
                raise ValueError("ZIP nie zawiera pliku HTML.")
            preferred = sorted(names, key=lambda item: (0 if Path(item).name.lower() in {"chat.html", "chat-0.html"} else 1, len(item), item.casefold()))[0]
            return archive.read(preferred).decode("utf-8-sig", errors="strict"), preferred
    return path.read_text(encoding="utf-8-sig", errors="strict"), path.name


def read_html_conversations(
    source: str | Path,
) -> tuple[list[dict[str, Any]], str, str, tuple[str, ...]]:
    """Parse HTML into canonical conversation dictionaries without writing a database."""

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    source_hash = sha256_file(path)
    html, member = _read_html_source(path)
    result = HtmlEmbeddedJsonParser().parse_text(html)
    records = result.semantic_payload
    if result.mode is HtmlParseMode.INVALID_HTML:
        raise ValueError("HTML nie zawiera rozmów możliwych do odtworzenia.")
    return records, member, result.mode.value, result.warnings


@dataclass(slots=True, frozen=True)
class HtmlImportResult:
    source_path: str
    source_sha256: str
    source_member: str
    mode: str
    conversations_seen: int
    conversations_inserted: int
    conversations_updated: int
    nodes_inserted: int
    conflicts: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_member": self.source_member,
            "mode": self.mode,
            "conversations_seen": self.conversations_seen,
            "conversations_inserted": self.conversations_inserted,
            "conversations_updated": self.conversations_updated,
            "nodes_inserted": self.nodes_inserted,
            "conflicts": self.conflicts,
            "warnings": list(self.warnings),
            "automatic_l2": False,
            "automatic_l3": False,
        }


def import_chat_html(source: str | Path, database: str | Path, *, dry_run: bool = False) -> HtmlImportResult:
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    source_hash = sha256_file(path)
    records, member, mode, warnings_tuple = read_html_conversations(path)
    warnings = list(warnings_tuple)

    counters = {"conversations_inserted": 0, "conversations_updated": 0, "nodes_inserted": 0, "conflicts": 0}
    with ChatExportArchiveStore(database) as store:
        active = store.load_active_states()
        plans = []
        graphs = []
        for raw in records:
            graph = build_conversation_graph(raw)
            graphs.append(graph)
            plans.append(plan_conversation(graph, active.get(graph.conversation_id)))
        if not dry_run:
            existing = store.find_import_by_sha(source_hash)
            if existing:
                return HtmlImportResult(
                    source_path=str(path), source_sha256=source_hash, source_member=member,
                    mode="identical_source_duplicate", conversations_seen=len(graphs),
                    conversations_inserted=0, conversations_updated=0, nodes_inserted=0,
                    conflicts=0, warnings=tuple(warnings),
                )
            from latka_jazn.tools.chat_export_models import ExportSourceInfo
            info = ExportSourceInfo(
                path=str(path), source_name=path.name, source_kind="html", sha256=source_hash,
                size_bytes=path.stat().st_size, conversations_member=None, html_member=member,
                crc_checked=False, crc_ok=True,
            )
            with store.transaction():
                import_id = store.begin_import(info)
                for graph, plan in zip(graphs, plans):
                    delta = store.store_graph(import_id, graph, plan)
                    for key in counters:
                        counters[key] += int(delta.get(key, 0))
                store.finish_import(
                    import_id,
                    conversation_count=len(graphs),
                    node_count=sum(item.node_count for item in graphs),
                    message_count=sum(item.message_count for item in graphs),
                    report={
                        "source": "html_import",
                        "mode": mode,
                        "source_member": member,
                        "warnings": warnings,
                        "truth_boundary": "HTML jest źródłem rozmów; nie promuje treści do L2/L3.",
                        "imported_at_utc": _utc_now(),
                    },
                )
    return HtmlImportResult(
        source_path=str(path), source_sha256=source_hash, source_member=member, mode=mode,
        conversations_seen=len(records), conversations_inserted=counters["conversations_inserted"],
        conversations_updated=counters["conversations_updated"], nodes_inserted=counters["nodes_inserted"],
        conflicts=counters["conflicts"], warnings=tuple(warnings),
    )


__all__ = ["HtmlImportResult", "import_chat_html", "read_html_conversations"]
