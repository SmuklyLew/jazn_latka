from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from html import unescape
from html.parser import HTMLParser
from typing import Any
import json
import re
import uuid


_JSON_ASSIGNMENT_RE = re.compile(r"(?:var|let|const)\s+jsonData\s*=", re.IGNORECASE)


class HtmlParseMode(str, Enum):
    EMBEDDED_JSON_LOSSLESS = "embedded_json_lossless"
    RENDERED_HTML_LOSSY = "rendered_html_lossy"
    INVALID_HTML = "invalid_html"


@dataclass(frozen=True, slots=True)
class HtmlParseResult:
    mode: HtmlParseMode
    raw_html: str
    raw_payload: Any
    semantic_payload: list[dict[str, Any]]
    warnings: tuple[str, ...] = ()


def _decode_assignment(text: str) -> Any:
    match = _JSON_ASSIGNMENT_RE.search(text)
    if match is None:
        raise ValueError("embedded jsonData assignment is missing")
    index = match.end()
    while index < len(text) and text[index].isspace():
        index += 1
    value, _ = json.JSONDecoder().raw_decode(text, index)
    return value


def _conversation_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict) and isinstance(item.get("mapping"), dict)]
    if isinstance(value, dict):
        for key in ("conversations", "items", "data"):
            found = _conversation_records(value.get(key))
            if found:
                return found
        if isinstance(value.get("mapping"), dict):
            return [value]
    return []


class HtmlSemanticNormalizer:
    """Decode semantic string values after JSON parsing; dictionary keys stay exact."""

    def normalize(self, value: Any) -> Any:
        if isinstance(value, str):
            return unescape(value)
        if isinstance(value, list):
            return [self.normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: self.normalize(item) for key, item in value.items()}
        return value


class _RenderedConversationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._in_conversation = False
        self._title_capture = False
        self._message_capture = False
        self._title: list[str] = []
        self._message: list[str] = []
        self._messages: list[str] = []
        self.conversations: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = set((dict(attrs).get("class") or "").split())
        lower = tag.casefold()
        if lower == "div" and "conversation" in classes and not self._in_conversation:
            self._in_conversation = True
            self._depth = 1
            self._title = []
            self._messages = []
        elif self._in_conversation and lower == "div":
            self._depth += 1
        elif self._in_conversation and lower == "h4":
            self._title_capture = True
        elif self._in_conversation and lower == "pre" and "message" in classes:
            self._message_capture = True
            self._message = []

    def handle_endtag(self, tag: str) -> None:
        lower = tag.casefold()
        if lower == "h4":
            self._title_capture = False
        elif lower == "pre" and self._message_capture:
            self._message_capture = False
            text = "".join(self._message).strip()
            if text:
                self._messages.append(text)
        elif lower == "div" and self._in_conversation:
            self._depth -= 1
            if self._depth <= 0:
                if self._messages:
                    self.conversations.append(("".join(self._title).strip() or "Rozmowa z HTML", list(self._messages)))
                self._in_conversation = False

    def handle_data(self, data: str) -> None:
        if self._title_capture:
            self._title.append(data)
        if self._message_capture:
            self._message.append(data)


def _synthetic_conversation(title: str, messages: list[str], ordinal: int) -> dict[str, Any]:
    conversation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"jazn-rendered-html:{ordinal}:{title}"))
    mapping: dict[str, Any] = {}
    parent: str | None = None
    for index, text in enumerate(messages):
        node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{conversation_id}:node:{index}:{text}"))
        mapping[node_id] = {
            "id": node_id,
            "parent": parent,
            "children": [],
            "message": {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{conversation_id}:message:{index}:{text}")),
                "author": {"role": "user" if index % 2 == 0 else "assistant"},
                "content": {"content_type": "text", "parts": [text]},
                "metadata": {"source": "rendered_html_lossy"},
            },
        }
        if parent is not None:
            mapping[parent]["children"].append(node_id)
        parent = node_id
    return {
        "id": conversation_id,
        "title": title,
        "current_node": parent,
        "mapping": mapping,
        "metadata": {"source": "rendered_html_lossy"},
    }


class HtmlEmbeddedJsonParser:
    def __init__(self, normalizer: HtmlSemanticNormalizer | None = None) -> None:
        self.normalizer = normalizer or HtmlSemanticNormalizer()

    def parse_text(self, raw_html: str) -> HtmlParseResult:
        warnings: list[str] = []
        try:
            raw_payload = _decode_assignment(raw_html)
        except (json.JSONDecodeError, ValueError) as exc:
            raw_payload = None
            warnings.append(f"embedded_json_unavailable:{type(exc).__name__}:{exc}")
        else:
            semantic = _conversation_records(self.normalizer.normalize(deepcopy(raw_payload)))
            if semantic:
                return HtmlParseResult(HtmlParseMode.EMBEDDED_JSON_LOSSLESS, raw_html, raw_payload, semantic, tuple(warnings))
            warnings.append("embedded_json_contains_no_conversation_graphs")

        rendered = _RenderedConversationParser()
        rendered.feed(raw_html)
        semantic = [
            _synthetic_conversation(title, messages, index)
            for index, (title, messages) in enumerate(rendered.conversations, start=1)
        ]
        if semantic:
            return HtmlParseResult(HtmlParseMode.RENDERED_HTML_LOSSY, raw_html, raw_payload, semantic, tuple(warnings))
        warnings.append("html_contains_no_recoverable_conversations")
        return HtmlParseResult(HtmlParseMode.INVALID_HTML, raw_html, raw_payload, [], tuple(warnings))


__all__ = ["HtmlEmbeddedJsonParser", "HtmlParseMode", "HtmlParseResult", "HtmlSemanticNormalizer"]
