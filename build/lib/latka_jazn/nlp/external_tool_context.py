from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
import unicodedata
from typing import Any

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("external_tool_context")
_DIACRITICS = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


@dataclass(slots=True)
class ExternalToolContext:
    present: bool
    requested_tools: list[str] = field(default_factory=list)
    raw_markers: list[str] = field(default_factory=list)
    primary_tool: str | None = None
    tool_only: bool = False
    assistance_intent: str = "external_tool_assistance_request"
    schema_version: str = SCHEMA_VERSION

    def requests(self, tool_id: str) -> bool:
        return str(tool_id or "").strip().lower() in self.requested_tools

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExternalToolContextParser:
    """Extract connector/tool context without changing the primary user goal."""

    ALIASES: dict[str, tuple[str, ...]] = {
        "github": ("@github", "github"),
        "web": ("@wyszukiwanie w sieci", "wyszukiwanie w sieci", "web.run", "@web"),
        "google_drive": ("@google drive", "google drive", "dysk google", "@drive"),
        "gmail": ("@gmail", "gmail"),
        "google_calendar": ("@google calendar", "google calendar", "kalendarz google"),
        "slack": ("@slack", "slack"),
        "linear": ("@linear", "linear"),
    }

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "").strip().lower())

    @staticmethod
    def fold(text: str) -> str:
        return (text or "").translate(_DIACRITICS).lower()

    def parse(self, text: str) -> ExternalToolContext:
        normalized = self.normalize(text)
        folded = self.fold(normalized)
        requested: list[str] = []
        raw: list[str] = []
        residual = folded
        for tool_id, aliases in self.ALIASES.items():
            matched_alias: str | None = None
            for alias in sorted(aliases, key=len, reverse=True):
                folded_alias = self.fold(alias)
                if folded_alias in folded:
                    matched_alias = alias
                    residual = residual.replace(folded_alias, " ")
                    break
            if matched_alias is not None:
                requested.append(tool_id)
                raw.append(matched_alias)
        residual = re.sub(r"[@#,:;.!?()\[\]{}\-]+", " ", residual)
        residual = re.sub(r"\s+", " ", residual).strip()
        tool_only = bool(requested) and residual in {"", "uzyj", "użyj", "sprawdz", "sprawdź"}
        return ExternalToolContext(
            present=bool(requested),
            requested_tools=requested,
            raw_markers=raw,
            primary_tool=requested[0] if requested else None,
            tool_only=tool_only,
        )
