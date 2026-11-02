"""Read-only, bounded-memory keyset discovery; reports remain owned by RunStore."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import heapq
import json
import os
from pathlib import Path
import re
from typing import Callable

from tools.jazn_run_studio.tpa_reports import safe_child


@dataclass
class HistoryPage:
    runs: list[dict]
    errors: list[str]
    next_cursor: str | None
    total: int
    bytes_read: int


def _candidates(base: Path, limit: int, after: tuple[int, str] | None, index_file: str | None):
    # A bounded heap avoids retaining every directory or any report body.
    heap: list[tuple[int, str]] = []
    digest = 0
    count = 0
    if not base.exists():
        return heap, "0:0", 0
    with os.scandir(base) as entries:
        for entry in entries:
            if not re.fullmatch(r"run-[0-9a-f]{32}", entry.name):
                continue
            if index_file is None:
                stamp = entry.stat(follow_symlinks=False).st_mtime_ns
            else:
                # NTFS can publish a directory mtime late, including after a
                # read-only scan. The atomically replaced, closed report index
                # provides a stable order. A missing/refused index is still a
                # candidate, with an explicit canonical loader error if invalid.
                try:
                    folder = safe_child(base, entry.name)
                    index = safe_child(folder, index_file)
                    stamp = index.stat(follow_symlinks=False).st_mtime_ns
                except (OSError, ValueError):
                    stamp = 0
            key = (stamp, entry.name)
            # Commutative fingerprint: scandir order is not stable. Run names
            # are unique; mutations invalidate the cursor instead of skipping.
            digest ^= int.from_bytes(sha256(f"{stamp}:{entry.name}".encode()).digest())
            count += 1
            if after is not None and key >= after:
                continue
            if len(heap) < limit + 1:
                heapq.heappush(heap, key)
            elif key > heap[0]:
                heapq.heapreplace(heap, key)
    return sorted(heap, reverse=True), f"{count}:{digest:064x}", count


def read_page(base: Path, loader: Callable[[Path], tuple[dict, int]], *,
              limit: int = 100, cursor: str | None = None,
              byte_limit: int = 64 * 1024 * 1024, index_file: str | None = None) -> HistoryPage:
    """Advance past both valid and refused records, without losing a byte-bound run.

    Limits apply to one page. Individual evidence limits remain enforced by the
    canonical loader. A refused record is an error, never a successful result.
    A changing inventory explicitly requires refresh. No files are written.
    """
    if type(limit) is not int or not 1 <= limit <= 100 or type(byte_limit) is not int or byte_limit < 1:
        raise ValueError("Nieprawidłowy limit strony historii")
    if not base.is_absolute() or ".." in base.parts:
        raise ValueError("Wybierz absolutny katalog historii bez '..'")
    safe_child(base.parent, base.name)
    scope = sha256(os.fsencode(base) + b"\0" + (index_file or "").encode()).hexdigest()
    after = None
    expected = None
    if cursor is not None:
        try:
            if not isinstance(cursor, str) or len(cursor) > 600:
                raise ValueError()
            value = json.loads(cursor)
            if (set(value) != {"schema", "base", "generation", "after"}
                    or value["schema"] != 1 or value["base"] != scope
                    or not isinstance(value["generation"], str)
                    or not isinstance(value["after"], list) or len(value["after"]) != 2
                    or type(value["after"][0]) is not int
                    or not isinstance(value["after"][1], str)
                    or not re.fullmatch(r"run-[0-9a-f]{32}", value["after"][1])):
                raise ValueError()
            after = (value["after"][0], value["after"][1])
            expected = value["generation"]
        except (ValueError, TypeError, KeyError):
            raise ValueError("Nieprawidłowy kursor historii") from None
    candidates, generation, count = _candidates(base, limit, after, index_file)
    if expected is not None and expected != generation:
        raise ValueError("Historia zmieniła się; odśwież listę przebiegów")
    runs: list[dict] = []
    errors: list[str] = []
    used = 0
    last = after
    more = len(candidates) > limit
    for key in candidates[:limit]:
        folder = base / key[1]
        try:
            safe_child(base, folder.name)
            if not folder.is_dir():
                raise ValueError("Brak katalogu przebiegu")
            run, size = loader(folder)
            if size > byte_limit:
                raise ValueError("Pojedynczy przebieg przekracza limit strony")
            if used + size > byte_limit:
                # Do not consume this record: the next page starts with it.
                more = True
                break
            runs.append(run)
            used += size
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append(folder.name + ": " + type(exc).__name__ + "; brak potwierdzonego wyniku")
        last = key
    # Detect a write/addition during verification too, not just between pages.
    _, final_generation, _ = _candidates(base, 1, None, index_file)
    if generation != final_generation:
        raise ValueError("Historia zmieniła się podczas odczytu; odśwież listę przebiegów")
    next_cursor = None
    if more and last is not None:
        next_cursor = json.dumps({"schema": 1, "base": scope,
                                  "generation": generation, "after": last}, separators=(",", ":"))
    return HistoryPage(runs, errors, next_cursor, count, used)
