from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import hashlib

SCHEMA_VERSION = "raw_chat_importer/v2"


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(slots=True)
class RawChatStatus:
    status: str
    chat_html_present: bool
    sqlite_index_available: bool
    chat_html_sha256: str | None = None
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Surowy import rozmów korzysta wyłącznie z jawnego memory/raw/chat.html "
        "albo z istniejącego, zweryfikowanego indeksu SQLite. Runtime nie rozpakowuje archiwum 7z."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RawChatImporter:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def inspect(self) -> RawChatStatus:
        raw = self.root / "memory" / "raw" / "chat.html"
        runtime = self.root / "workspace_runtime"
        sqlite_dir = self.root / "memory" / "sqlite"
        dbs = []
        for parent in (runtime, sqlite_dir):
            if parent.exists():
                dbs.extend(parent.glob("*.sqlite3"))
        chat_present = raw.is_file()
        index_available = bool(dbs)
        if chat_present and index_available:
            status = "raw_and_index_available"
        elif chat_present:
            status = "raw_only"
        elif index_available:
            status = "index_only"
        else:
            status = "unavailable"
        return RawChatStatus(
            status=status,
            chat_html_present=chat_present,
            sqlite_index_available=index_available,
            chat_html_sha256=_sha(raw),
        )
