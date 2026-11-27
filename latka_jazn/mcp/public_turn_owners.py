from __future__ import annotations

"""Public HTTP resource authorization only; not a turn lifecycle or result store."""

from contextlib import closing
import hashlib
import hmac
from pathlib import Path
import re

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.db.runtime_sqlite import (
    connect_runtime_readonly, connect_runtime_writable, runtime_sqlite_write_guard,
)

_DDL = """CREATE TABLE IF NOT EXISTS public_turn_owners (
    request_id TEXT PRIMARY KEY NOT NULL,
    owner_sha256 TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
)"""


def _owner_digest(subject: str) -> str:
    if not subject or not subject.strip():
        raise ValueError("public_turn_owner_missing")
    return hashlib.sha256(("public_http\0" + subject).encode("utf-8")).hexdigest()


class PublicTurnOwnerStore:
    """Immutable reservations outside MEMORY; never store messages or replies."""

    def __init__(self, root: Path) -> None:
        self.path = workspace_runtime_path(root) / "public_turn_owners.sqlite3"

    @staticmethod
    def matches(existing: tuple[str, str], subject: str, payload_sha256: str | None = None) -> bool:
        return hmac.compare_digest(existing[0], _owner_digest(subject)) and (
            payload_sha256 is None or hmac.compare_digest(existing[1], payload_sha256)
        )

    def lookup(self, request_id: str) -> tuple[str, str] | None:
        try:
            self.path.stat()
        except FileNotFoundError:
            return None
        with closing(connect_runtime_readonly(self.path)) as connection:
            row = connection.execute(
                "SELECT owner_sha256, payload_sha256 FROM public_turn_owners WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if row is None:
                return None
            values = (row[0], row[1])
            if not all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) for v in values):
                raise ValueError("public_turn_owner_record_invalid")
            return str(values[0]), str(values[1])

    def reserve(self, request_id: str, subject: str, payload_sha256: str) -> bool:
        """Caller must first verify absence in the daemon's admission history."""
        if not request_id or not re.fullmatch(r"[0-9a-f]{64}", payload_sha256):
            raise ValueError("public_turn_owner_reservation_invalid")
        owner = _owner_digest(subject)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One cross-process writer; never overwrite a winner, even on retry.
        with runtime_sqlite_write_guard(self.path, timeout_ms=30_000):
            with closing(connect_runtime_writable(self.path, timeout_ms=30_000,
                                                  synchronous="FULL")) as connection:
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(_DDL)
                    connection.execute(
                        "INSERT INTO public_turn_owners VALUES(?,?,?) ON CONFLICT(request_id) DO NOTHING",
                        (request_id, owner, payload_sha256),
                    )
                    row = connection.execute(
                        "SELECT owner_sha256, payload_sha256 FROM public_turn_owners WHERE request_id=?",
                        (request_id,),
                    ).fetchone()
                    return row is not None and self.matches((str(row[0]), str(row[1])), subject, payload_sha256)
