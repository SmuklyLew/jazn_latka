from __future__ import annotations

import json
import os
from pathlib import Path
import time

import pytest

from latka_jazn.core import runtime_root
from latka_jazn.core.process_identity import (
    PROCESS_FINGERPRINT_SCHEMA_VERSION,
)


def _fingerprint(pid: int, token: str) -> dict[str, object]:
    return {
        "schema_version": PROCESS_FINGERPRINT_SCHEMA_VERSION,
        "pid": pid,
        "platform": os.name,
        "available": True,
        "identity_token": token,
        "state": "observed",
    }


def _lock_path(root: Path, name: str) -> Path:
    return (
        runtime_root.workspace_runtime_path(root)
        / runtime_root.WORKSPACE_LOCK_DIR_NAME
        / f"{name}.lock"
    )


def test_old_lock_is_not_stolen_from_live_confirmed_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    lock = _lock_path(root, "daemon-reload")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps(
            {
                "schema_version": (
                    "runtime_workspace_transition_lock/v2"
                ),
                "pid": 4242,
                "process_fingerprint": _fingerprint(
                    4242,
                    "owner",
                ),
            }
        ),
        encoding="utf-8",
    )
    old = time.time() - 3600
    os.utime(lock, (old, old))

    monkeypatch.setattr(
        runtime_root,
        "process_is_alive",
        lambda _pid: True,
    )
    monkeypatch.setattr(
        runtime_root,
        "process_fingerprint",
        lambda pid: _fingerprint(int(pid), "owner"),
    )

    with pytest.raises(runtime_root.RuntimeWorkspaceBusyError):
        with runtime_root.runtime_workspace_transition_lock(
            root,
            "daemon-reload",
            stale_after_seconds=1.0,
        ):
            raise AssertionError(
                "live owner lock must not be stolen"
            )
    assert lock.exists()


def test_dead_owner_lock_is_reclaimed_without_age_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    lock = _lock_path(root, "daemon-reload")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps(
            {
                "schema_version": (
                    "runtime_workspace_transition_lock/v2"
                ),
                "pid": 4242,
                "process_fingerprint": _fingerprint(
                    4242,
                    "old",
                ),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        runtime_root,
        "process_is_alive",
        lambda _pid: False,
    )
    monkeypatch.setattr(
        runtime_root,
        "process_fingerprint",
        lambda pid: (
            _fingerprint(int(pid), "new")
            if pid
            else {
                "schema_version": (
                    PROCESS_FINGERPRINT_SCHEMA_VERSION
                ),
                "pid": None,
                "platform": os.name,
                "available": False,
                "identity_token": None,
                "state": "not_alive",
            }
        ),
    )

    with runtime_root.runtime_workspace_transition_lock(
        root,
        "daemon-reload",
        stale_after_seconds=3600.0,
    ) as claimed:
        assert claimed == lock
        assert lock.exists()
    assert not lock.exists()


def test_live_legacy_lock_without_fingerprint_fails_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    lock = _lock_path(root, "daemon-reload")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps({"pid": 4242}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        runtime_root,
        "process_is_alive",
        lambda _pid: True,
    )
    monkeypatch.setattr(
        runtime_root,
        "process_fingerprint",
        lambda pid: _fingerprint(
            int(pid),
            "observed",
        ),
    )

    with pytest.raises(runtime_root.RuntimeWorkspaceBusyError):
        with runtime_root.runtime_workspace_transition_lock(
            root,
            "daemon-reload",
        ):
            raise AssertionError(
                "unverified live legacy owner must fail closed"
            )
    assert lock.exists()


def test_pid_reuse_fingerprint_allows_stale_lock_reclaim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    lock = _lock_path(root, "daemon-reload")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps(
            {
                "pid": 4242,
                "process_fingerprint": _fingerprint(
                    4242,
                    "old-process",
                ),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        runtime_root,
        "process_is_alive",
        lambda _pid: True,
    )
    monkeypatch.setattr(
        runtime_root,
        "process_fingerprint",
        lambda pid: _fingerprint(
            int(pid),
            "new-process",
        ),
    )

    with runtime_root.runtime_workspace_transition_lock(
        root,
        "daemon-reload",
    ):
        assert lock.exists()
    assert not lock.exists()
