"""Cooperative multi-process locking for Studio settings.

This protects cooperating writers, not against privileged filesystem
replacement during a time-of-check/time-of-use race.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import time
from typing import Iterator


class SettingsLockError(OSError):
    """Unsafe settings lock or lock timeout."""


def _reject_redirected(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink() or bool(getattr(item, "is_junction", lambda: False)()):
            raise SettingsLockError("Symlink/junction in settings or lock path")


@contextmanager
def exclusive_settings_lock(settings_path: Path, *, timeout: float = 8.0) -> Iterator[None]:
    """Serialize read-digest/check/write; keep the lock sidecar permanently."""
    target = Path(settings_path).absolute()
    _reject_redirected(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_redirected(target)
    lock = target.with_name(target.name + ".lock")
    _reject_redirected(lock)

    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock, flags, 0o600)
    held = False
    try:
        _reject_redirected(lock)
        opened = os.fstat(fd)
        actual = lock.lstat()
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (actual.st_dev, actual.st_ino)):
            raise SettingsLockError("Lock path identity differs from opened file")
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held = True
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise SettingsLockError("Timed out acquiring settings lock") from exc
                time.sleep(0.05)
        _reject_redirected(target)
        yield
    finally:
        try:
            if held:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
