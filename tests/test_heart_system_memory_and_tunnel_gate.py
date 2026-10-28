"""Canonical memory continuity is not the same as memory availability."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.jazn_run_studio.core import Controller, Settings, StudioError
from tools.jazn_run_studio.status_summary import status_summary


def test_stale_wake_state_never_claims_autobiographical_continuity() -> None:
    data = {
        "runtime_version": "sample",
        "memory_availability": {"status": "available", "mode": "optional"},
        "startup": {
            "memory_continuity_status": {
                "status": "partial_unverified",
                "wake_context_ready": False,
                "continuity_claim_allowed": False,
            },
            "model_adapter_status": {"adapter_id": "null_model_adapter"},
        },
    }
    result = status_summary(data)
    assert "niepotwierdzona" in result["continuity"]
    assert "partial_unverified" in result["continuity"]
    assert "null_model_adapter" in result["model"]


def test_verified_continuity_requires_claim_and_wake_state() -> None:
    base = {"startup": {"memory_continuity_status": {
        "status": "ready", "continuity_claim_allowed": True,
        "wake_context_ready": False,
    }}}
    assert "niepotwierdzona" in status_summary(base)["continuity"]
    base["startup"]["memory_continuity_status"]["wake_context_ready"] = True
    assert "zweryfikowana ciągłość" in status_summary(base)["continuity"]


def test_studio_refuses_to_publish_loopback_noauth_gateway_as_public_mcp(tmp_path: Path) -> None:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").touch()
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").touch()
    controller = Controller(tmp_path, Settings())
    with pytest.raises(StudioError, match="--loopback-dev"):
        controller.start_service("cloudflare")
    assert "service:cloudflare" not in controller.jobs
