"""Readiness probes must not promote HTTP reachability into service success."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.jazn_run_studio import probes
from tools.jazn_run_studio.core import Controller, Settings


@pytest.fixture
def controller(tmp_path: Path) -> Controller:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").touch()
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").touch()
    return Controller(tmp_path, Settings(model="gemma3:latest", cloudflare_url="https://test.workers.dev"))


@pytest.mark.parametrize(
    ("code", "ready", "state", "error"),
    [
        (200, True, "succeeded", None),
        (200, False, "failed", "service_not_ready"),
        (503, False, "failed", "service_not_ready"),
        (401, False, "failed", "service_not_ready"),
    ],
)
def test_gateway_http_reachability_is_not_readiness(
    controller: Controller, monkeypatch: pytest.MonkeyPatch,
    code: int, ready: bool, state: str, error: str | None,
) -> None:
    monkeypatch.setattr(
        probes, "read_json",
        lambda _url: (code, {"ready": ready, "gateway_live": True}),
    )
    job = controller.probe("gateway")
    assert job.done.wait(5)
    assert job.state == state and job.error == error
    events = []
    while not controller.events.empty():
        events.append(controller.events.get_nowait())
    assert any(kind == "probe" and value.get("ready") is ready for _key, kind, value in events)


@pytest.mark.parametrize("ready", [True, False])
def test_cloudflare_health_is_not_automatically_ready(
    controller: Controller, monkeypatch: pytest.MonkeyPatch, ready: bool,
) -> None:
    monkeypatch.setattr(
        probes, "read_json",
        lambda _url, *, timeout: (200, {"ready": ready}),
    )
    job = controller.probe("cloudflare")
    assert job.done.wait(5)
    assert job.state == ("succeeded" if ready else "failed")
    assert job.error == (None if ready else "service_not_ready")


@pytest.mark.parametrize(
    ("models", "expected_state", "expected_error"),
    [
        (["gemma3:latest"], "succeeded", None),
        (["another:latest"], "failed", "selected_model_missing"),
    ],
)
def test_ollama_missing_selected_model_is_not_ready_for_selected_model(
    controller: Controller, monkeypatch: pytest.MonkeyPatch,
    models: list[str], expected_state: str, expected_error: str | None,
) -> None:
    monkeypatch.setattr(
        probes, "read_json",
        lambda _url: (200, {"models": [{"name": name} for name in models]}),
    )
    job = controller.probe("ollama")
    assert job.done.wait(5)
    assert job.state == expected_state and job.error == expected_error
    assert any(
        kind == "probe" and value.get("generation_verified") is False
        for _key, kind, value in list(controller.events.queue)
    )
