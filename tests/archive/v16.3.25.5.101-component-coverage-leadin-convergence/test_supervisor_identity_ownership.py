from __future__ import annotations

import json
import os
from pathlib import Path

from latka_jazn.core import runtime_supervisor
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


def test_supervisor_reclaims_live_reused_pid_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    pid_path = runtime_supervisor.supervisor_pid_path(root)
    owner_path = runtime_supervisor.supervisor_owner_path(root)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("4242", encoding="ascii")
    owner_path.write_text(
        json.dumps(
            {
                "pid": 4242,
                "runtime_root": str(root.resolve()),
                "process_fingerprint": _fingerprint(4242, "old-token"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_supervisor,
        "pid_is_alive",
        lambda pid: pid in {4242, os.getpid()},
    )
    monkeypatch.setattr(
        runtime_supervisor,
        "process_fingerprint",
        lambda pid, **_kwargs: _fingerprint(
            int(pid or os.getpid()),
            "new-token",
        ),
    )

    claimed, existing = runtime_supervisor._claim_supervisor_pid(root)
    assert claimed is True
    assert existing is None
    assert pid_path.read_text(encoding="ascii").strip() == str(os.getpid())


def test_supervisor_refuses_live_owner_when_identity_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    pid_path = runtime_supervisor.supervisor_pid_path(root)
    owner_path = runtime_supervisor.supervisor_owner_path(root)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("4242", encoding="ascii")
    owner_path.write_text(
        json.dumps(
            {
                "pid": 4242,
                "runtime_root": str(root.resolve()),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_supervisor,
        "pid_is_alive",
        lambda _pid: True,
    )
    monkeypatch.setattr(
        runtime_supervisor,
        "process_fingerprint",
        lambda pid, **_kwargs: {
            "schema_version": PROCESS_FINGERPRINT_SCHEMA_VERSION,
            "pid": pid,
            "platform": os.name,
            "available": False,
            "identity_token": None,
            "state": "alive_without_stable_token",
        },
    )

    claimed, existing = runtime_supervisor._claim_supervisor_pid(root)
    assert claimed is False
    assert existing == 4242
    assert pid_path.exists()
    assert owner_path.exists()


def test_supervisor_status_requires_fingerprint_bound_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    pid = 4242
    pid_path = runtime_supervisor.supervisor_pid_path(root)
    owner_path = runtime_supervisor.supervisor_owner_path(root)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(pid), encoding="ascii")
    owner_path.write_text(
        json.dumps(
            {
                "pid": pid,
                "runtime_root": str(root.resolve()),
                "process_fingerprint": _fingerprint(
                    pid,
                    "same-token",
                ),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_supervisor,
        "pid_is_alive",
        lambda _pid: True,
    )
    monkeypatch.setattr(
        runtime_supervisor,
        "process_fingerprint",
        lambda observed_pid, **_kwargs: _fingerprint(
            int(observed_pid),
            "same-token",
        ),
    )
    status = runtime_supervisor.supervisor_status(root)
    assert status["supervisor_pid_alive"] is True
    assert status["supervisor_identity_confirmed"] is True
    assert status["supervisor_active"] is True
