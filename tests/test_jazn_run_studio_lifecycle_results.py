"""Operator success follows the canonical result, including older runtimes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

from latka_jazn.cli_commands.lifecycle import legacy_args
from tools.jazn_run_studio.core import Controller, Settings


def test_lifecycle_separator_forwards_port_without_changing_chat_text() -> None:
    assert legacy_args("start", ["--", "--daemon-port", "61234"]) == ["--daemon-start", "--daemon-port", "61234"]
    assert legacy_args("stop", ["--", "--daemon-port", "61234"]) == ["--daemon-stop", "--daemon-port", "61234"]
    assert legacy_args("chat", ["--", "--version"]) == ["--chat", "--", "--version"]


@pytest.mark.parametrize("operation", ["start", "stop"])
@pytest.mark.parametrize("ok", [True, False])
def test_public_lifecycle_exit_code_matches_runtime_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], operation: str, ok: bool,
) -> None:
    import main
    monkeypatch.setattr(main, operation + "_daemon", lambda *_a, **_k: {"ok": ok})
    for name in tuple(os.environ):
        if "TRUSTED_TIME" in name or name in {"CHATGPT_HOST_TIME_ISO", "OPENAI_HOST_TIME_ISO"}:
            monkeypatch.delenv(name, raising=False)
    code = main.legacy_main(["--root", str(tmp_path), "--daemon-" + operation])
    assert code == (0 if ok else 1)
    assert json.loads(capsys.readouterr().out)["ok"] is ok


@pytest.mark.parametrize("payload,expected", [('{"ok":true}', "succeeded"),
    ('{"ok":false,"error_code":"daemon_port_in_use_by_other_runtime"}', "failed"),
    ('unexpected output', "failed")])
def test_studio_does_not_trust_zero_exit_from_old_failed_runtime(tmp_path: Path, payload: str, expected: str) -> None:
    (tmp_path/"latka_jazn").mkdir()
    (tmp_path/"latka_jazn/version.py").touch()
    (tmp_path/"main.py").touch()
    (tmp_path/"run.py").write_text("print(" + repr(payload) + ")", encoding="utf-8")
    core = Controller(tmp_path, Settings(python=sys.executable))
    job = core.start_action("start")
    assert job.done.wait(5)
    assert job.returncode == 0
    assert job.state == expected


def test_explicit_off_route_keeps_deterministic_null_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    from latka_jazn.config import JaznConfig
    from latka_jazn.model_adapters import factory
    from latka_jazn.model_adapters.null_model_adapter import NullModelAdapter
    monkeypatch.setenv("JAZN_MODEL_ADAPTER", "null")
    monkeypatch.setenv("JAZN_LLM_ROUTE", "off")
    def unexpected_probe(*_a, **_k):
        raise AssertionError("An explicitly disabled model route must not probe or select Ollama")
    monkeypatch.setattr(factory, "build_llm_route_status", unexpected_probe)
    assert isinstance(factory.build_model_adapter(JaznConfig()), NullModelAdapter)
