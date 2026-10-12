from __future__ import annotations

"""SQLite connection helpers that release Windows file handles deterministically."""

from typing import Literal
import sqlite3


class ClosingSQLiteConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


__all__ = ["ClosingSQLiteConnection"]
