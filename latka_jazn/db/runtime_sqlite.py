from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import quote
import os
import sqlite3
import threading
import time

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("runtime_sqlite")
DEFAULT_BUSY_TIMEOUT_MS = 30_000
DEFAULT_SYNCHRONOUS = "FULL"
_WAL_RESET_FIXED_MAINLINE = (3, 51, 3)
_WAL_RESET_FIXED_BACKPORTS = {(3, 44): 6, (3, 50): 7}

_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}
_WRITE_GUARD_STATE = threading.local()


def _resolved_key(path: str | Path) -> str:
    raw = str(path)
    if raw == ":memory:":
        return raw
    return str(Path(path).expanduser().resolve())


def _process_lock(path: str | Path) -> threading.RLock:
    key = _resolved_key(path)
    with _LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PROCESS_LOCKS[key] = lock
        return lock


def _lock_file_path(path: str | Path) -> Path | None:
    if str(path) == ":memory:":
        return None
    db_path = Path(path).expanduser().resolve()
    return db_path.with_name(db_path.name + ".runtime-write.lock")


class _CrossProcessFileLock:
    def __init__(self, path: Path | None, *, timeout_seconds: float) -> None:
        self.path = path
        self.timeout_seconds = max(0.001, float(timeout_seconds))
        self._handle: Any | None = None

    def acquire(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                self._try_lock(handle)
                self._handle = handle
                return
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    handle.close()
                    raise sqlite3.OperationalError(
                        f"runtime sqlite write lock timeout after {self.timeout_seconds:.3g}s: {self.path}"
                    )
                time.sleep(min(0.05, max(0.001, deadline - time.monotonic())))

    @staticmethod
    def _try_lock(handle: Any) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


@contextmanager
def runtime_sqlite_write_guard(
    path: str | Path,
    *,
    timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> Iterator[None]:
    """Serialize runtime SQLite writes across threads and cooperating processes.

    The sidecar lock file is deliberately separate from SQLite's own WAL/SHM files.
    It narrows all Jaźń runtime writers for a database to one application-level
    writer at a time, which also prevents concurrent Jaźń checkpoints/writes on
    SQLite builds affected by the WAL-reset race. The guard is re-entrant for
    the same database on the same thread so connection setup can safely run
    inside a larger guarded transaction.
    """

    timeout_seconds = max(0.001, int(timeout_ms) / 1000)
    key = _resolved_key(path)
    process_lock = _process_lock(path)
    if not process_lock.acquire(timeout=timeout_seconds):
        raise sqlite3.OperationalError(
            f"runtime sqlite process lock timeout after {timeout_seconds:.3g}s: {key}"
        )

    depths = getattr(_WRITE_GUARD_STATE, "depths", None)
    if depths is None:
        depths = {}
        _WRITE_GUARD_STATE.depths = depths
    current_depth = int(depths.get(key, 0))
    if current_depth > 0:
        depths[key] = current_depth + 1
        try:
            yield
        finally:
            remaining = int(depths.get(key, 1)) - 1
            if remaining > 0:
                depths[key] = remaining
            else:
                depths.pop(key, None)
            process_lock.release()
        return

    file_lock = _CrossProcessFileLock(_lock_file_path(path), timeout_seconds=timeout_seconds)
    try:
        file_lock.acquire()
        depths[key] = 1
        yield
    finally:
        depths.pop(key, None)
        file_lock.release()
        process_lock.release()


def sqlite_wal_reset_fix_available(version_info: tuple[int, ...] | None = None) -> bool:
    version = tuple(version_info or sqlite3.sqlite_version_info)
    if version >= _WAL_RESET_FIXED_MAINLINE:
        return True
    if len(version) < 3:
        return False
    minimum_patch = _WAL_RESET_FIXED_BACKPORTS.get((version[0], version[1]))
    return minimum_patch is not None and version[2] >= minimum_patch


def runtime_sqlite_journal_mode(version_info: tuple[int, ...] | None = None) -> str:
    """Select WAL only when the loaded SQLite build contains the WAL-reset fix.

    SQLite documents the WAL-reset corruption race as WAL-specific.  Runtime
    stores therefore use the rollback journal on affected/unknown builds instead
    of pretending that the Jaźń writer lock upgrades the SQLite library itself.
    """

    return "WAL" if sqlite_wal_reset_fix_available(version_info) else "DELETE"


def runtime_sqlite_capabilities() -> dict[str, Any]:
    fixed = sqlite_wal_reset_fix_available()
    selected_journal_mode = runtime_sqlite_journal_mode()
    return {
        "schema_version": SCHEMA_VERSION,
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_version_info": list(sqlite3.sqlite_version_info),
        "sqlite_threadsafety": int(sqlite3.threadsafety),
        "wal_reset_fix_available": fixed,
        "runtime_writer_serialization": "cross_process_file_lock+process_rlock",
        "selected_journal_mode": selected_journal_mode,
        "journal_mode_policy": "wal_on_fixed_sqlite_else_delete",
        "wal_reset_mitigation_required": not fixed,
        "wal_reset_mitigation_active": not fixed and selected_journal_mode == "DELETE",
        "truth_boundary": (
            "The runtime reports the SQLite library actually loaded by Python. "
            "Fixed SQLite builds use WAL. Builds without a documented WAL-reset fix use DELETE rollback-journal mode, "
            "so the runtime does not rely on application-level serialization as a substitute for the SQLite fix. "
            "The cross-process/process-local writer guard remains defense in depth."
        ),
    }


def _readonly_uri(path: str | Path) -> str:
    resolved = str(Path(path).expanduser().resolve()).replace("\\", "/")
    return "file:" + quote(resolved, safe="/:" ) + "?mode=ro"


def connect_runtime_readonly(
    path: str | Path,
    *,
    timeout_ms: int = 10_000,
) -> sqlite3.Connection:
    db_path = Path(path).expanduser().resolve()
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    connection = sqlite3.connect(
        _readonly_uri(db_path),
        uri=True,
        timeout=max(0.001, int(timeout_ms) / 1000),
    )
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout={max(1, int(timeout_ms))}")
    connection.execute("PRAGMA query_only=ON")
    return connection


def connect_runtime_writable(
    path: str | Path,
    *,
    timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    synchronous: str = DEFAULT_SYNCHRONOUS,
    isolation_level: Literal["DEFERRED", "EXCLUSIVE", "IMMEDIATE"] | None = "DEFERRED",
    check_same_thread: bool = True,
    temp_store: str | None = None,
    cache_size: int | None = None,
) -> sqlite3.Connection:
    db_path = Path(path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    selected_sync = str(synchronous).upper()
    if selected_sync not in {"FULL", "NORMAL"}:
        raise ValueError("synchronous must be FULL or NORMAL")
    selected_temp = None if temp_store is None else str(temp_store).upper()
    if selected_temp not in {None, "FILE", "MEMORY"}:
        raise ValueError("temp_store must be FILE, MEMORY or None")
    timeout_value = max(1, int(timeout_ms))
    with runtime_sqlite_write_guard(db_path, timeout_ms=timeout_value):
        connection = sqlite3.connect(
            db_path,
            timeout=max(0.001, timeout_value / 1000),
            isolation_level=isolation_level,
            check_same_thread=check_same_thread,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute(f"PRAGMA busy_timeout={timeout_value}")
            connection.execute("PRAGMA foreign_keys=ON")
            selected_journal_mode = runtime_sqlite_journal_mode()
            current_mode_row = connection.execute("PRAGMA journal_mode").fetchone()
            current_mode = "" if current_mode_row is None else str(current_mode_row[0]).upper()
            if current_mode != selected_journal_mode:
                mode_row = connection.execute(f"PRAGMA journal_mode={selected_journal_mode}").fetchone()
                current_mode = "" if mode_row is None else str(mode_row[0]).upper()
            if current_mode != selected_journal_mode:
                raise sqlite3.OperationalError(
                    f"runtime sqlite journal mode activation failed for {db_path}: "
                    f"requested={selected_journal_mode}; returned={current_mode or current_mode_row!r}"
                )
            connection.execute(f"PRAGMA synchronous={selected_sync}")
            if selected_temp is not None:
                connection.execute(f"PRAGMA temp_store={selected_temp}")
            if cache_size is not None:
                connection.execute(f"PRAGMA cache_size={int(cache_size)}")
        except BaseException:
            connection.close()
            raise
    return connection


def sqlite_error_diagnostics(
    exc: BaseException,
    *,
    database: str | Path | None = None,
    operation: str | None = None,
) -> dict[str, Any]:
    return {
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "sqlite_errorcode": getattr(exc, "sqlite_errorcode", None),
        "sqlite_errorname": getattr(exc, "sqlite_errorname", None),
        "database": str(database) if database is not None else None,
        "operation": operation,
        "sqlite_version": sqlite3.sqlite_version,
    }
