from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import hashlib
import re

from .html_semantics import HtmlEmbeddedJsonParser, HtmlParseMode


class SourceRole(str, Enum):
    CANONICAL_CHAT_GRAPH = "canonical_chat_graph"
    LOSSLESS_CONTROL_GRAPH = "lossless_control_graph"
    LOSSY_RENDERED_CONTROL = "lossy_rendered_control"
    SUPPLEMENTAL_METADATA = "supplemental_metadata"
    SHARED_LINK_METADATA = "shared_link_metadata"
    PRIVATE_ACCOUNT_METADATA = "private_account_metadata"
    SOURCE_ATTACHMENT = "source_attachment"
    UNKNOWN_SIDECAR = "unknown_sidecar"


_CONVERSATIONS_RE = re.compile(r"^conversations(?:[-_ ]?\d+)?\.json$", re.IGNORECASE)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_source_role(relative_path: str) -> SourceRole:
    normalized = relative_path.replace("\\", "/")
    name = Path(normalized).name.casefold()
    first = normalized.split("/", 1)[0].casefold()
    if first in {"assets", "attachments"}:
        return SourceRole.SOURCE_ATTACHMENT
    if _CONVERSATIONS_RE.fullmatch(name):
        return SourceRole.CANONICAL_CHAT_GRAPH
    if name in {"chat.html", "chat.htm"}:
        return SourceRole.LOSSLESS_CONTROL_GRAPH
    if name == "message_feedback.json":
        return SourceRole.SUPPLEMENTAL_METADATA
    if name == "shared_conversations.json":
        return SourceRole.SHARED_LINK_METADATA
    if name in {"user.json", "account.json"}:
        return SourceRole.PRIVATE_ACCOUNT_METADATA
    return SourceRole.UNKNOWN_SIDECAR


def classify_source_path(path: str | Path, *, relative_path: str | None = None) -> SourceRole:
    """Classify HTML by parsed semantics while preserving path-only compatibility."""

    source = Path(path)
    role = classify_source_role(relative_path or source.name)
    if role is not SourceRole.LOSSLESS_CONTROL_GRAPH:
        return role
    if source.suffix.casefold() not in {".html", ".htm"}:
        return role
    try:
        raw_html = source.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return SourceRole.UNKNOWN_SIDECAR
    parsed = HtmlEmbeddedJsonParser().parse_text(raw_html)
    if parsed.mode is HtmlParseMode.EMBEDDED_JSON_LOSSLESS:
        return SourceRole.LOSSLESS_CONTROL_GRAPH
    if parsed.mode is HtmlParseMode.RENDERED_HTML_LOSSY:
        return SourceRole.LOSSY_RENDERED_CONTROL
    return SourceRole.UNKNOWN_SIDECAR


@dataclass(frozen=True, slots=True)
class SourceBundleMember:
    relative_path: str
    role: SourceRole
    source_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ChatGPTExportBundle:
    root: Path
    members: tuple[SourceBundleMember, ...]
    source_sha256: str

    @classmethod
    def discover(cls, root: str | Path) -> "ChatGPTExportBundle":
        resolved = Path(root).expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"ChatGPT export bundle must be a directory: {resolved}")
        paths = sorted(
            (item for item in resolved.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(resolved).as_posix().casefold(),
        )
        members = tuple(
            SourceBundleMember(
                relative_path=path.relative_to(resolved).as_posix(),
                role=classify_source_path(path, relative_path=path.relative_to(resolved).as_posix()),
                source_sha256=_sha256_file(path),
                size_bytes=path.stat().st_size,
            )
            for path in paths
        )
        if not members:
            raise ValueError(f"ChatGPT export bundle is empty: {resolved}")
        digest = hashlib.sha256()
        for item in members:
            digest.update(item.relative_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(item.role.value.encode("ascii"))
            digest.update(b"\0")
            digest.update(item.source_sha256.encode("ascii"))
            digest.update(b"\n")
        return cls(root=resolved, members=members, source_sha256=digest.hexdigest())

    @property
    def canonical_chat_members(self) -> tuple[str, ...]:
        def key(value: str) -> tuple[int, str]:
            name = Path(value).name.casefold()
            if name == "conversations.json":
                return (-1, value.casefold())
            match = re.fullmatch(r"conversations(?:[-_ ]?)(\d+)\.json", name)
            return (int(match.group(1)) if match else 0, value.casefold())

        return tuple(sorted(
            (item.relative_path for item in self.members if item.role is SourceRole.CANONICAL_CHAT_GRAPH),
            key=key,
        ))


__all__ = [
    "ChatGPTExportBundle",
    "SourceBundleMember",
    "SourceRole",
    "classify_source_path",
    "classify_source_role",
]
