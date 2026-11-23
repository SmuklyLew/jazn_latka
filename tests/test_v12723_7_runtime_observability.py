from __future__ import annotations

import argparse
from pathlib import Path

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core.message_envelope import clean_model_generated_body


def test_daemon_cli_channel_defaults_to_chatgpt_not_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JAZN_MODEL_ADAPTER", "local")
    monkeypatch.setenv("JAZN_LLM_ROUTE", "local")
    ns = main_module._build_parser().parse_args(["--daemon-send"])
    assert ns.daemon_channel == "chatgpt"
    settings, error = main_module._daemon_cli_channel_settings(ns, JaznConfig(root=tmp_path))
    assert error is None
    assert settings == {
        "client": "chatgpt_daemon_bridge",
        "command": "--chat",
        "model_channel_config": {},
    }


def test_explicit_ollama_channel_uses_turn_scoped_config(monkeypatch, tmp_path: Path) -> None:
    ns = main_module._build_parser().parse_args(
        ["--daemon-submit", "--daemon-channel", "ollama", "--ollama-model", "gemma3:latest"]
    )
    seen: list[str | None] = []

    def _probe(cfg: JaznConfig, *, model: str | None, **kwargs: object):
        seen.append(model)
        return cfg, {"available": True}

    monkeypatch.setattr(main_module, "resolve_ollama_cli_settings", _probe)
    monkeypatch.setattr(
        main_module,
        "model_channel_config_from_config",
        lambda cfg: {"model_adapter": "ollama", "llm_route_mode": "local"},
    )
    settings, error = main_module._daemon_cli_channel_settings(ns, JaznConfig(root=tmp_path))
    assert error is None
    assert seen == ["gemma3:latest"]
    assert settings == {
        "client": "ollama_terminal_one_shot",
        "command": "--chat-ollama",
        "model_channel_config": {"model_adapter": "ollama", "llm_route_mode": "local"},
    }


def test_unavailable_ollama_fails_before_submission(monkeypatch, tmp_path: Path) -> None:
    ns = argparse.Namespace(daemon_channel="ollama", daemon_final_only=False)
    monkeypatch.setattr(
        main_module,
        "resolve_ollama_cli_settings",
        lambda *args, **kwargs: (args[0], {"available": False, "reason": "ollama_unavailable"}),
    )
    settings, error = main_module._daemon_cli_channel_settings(ns, JaznConfig(root=tmp_path))
    assert settings == {}
    assert error is not None
    assert error["error_code"] == "ollama_unavailable"


def test_ollama_rejects_chatgpt_only_final_flag_without_probe(tmp_path: Path) -> None:
    ns = argparse.Namespace(daemon_channel="ollama", daemon_final_only=True)
    settings, error = main_module._daemon_cli_channel_settings(ns, JaznConfig(root=tmp_path))
    assert settings == {}
    assert error is not None
    assert error["error_code"] == "ollama_daemon_final_only_unsupported"


def test_host_phase_one_is_not_a_completed_visible_turn() -> None:
    observed = main_module._daemon_cli_completion({
        "ok": True, "execution_state": "host_visible_generation_requested",
        "daemon_job": {
            "job_status": "awaiting_host_finalization",
            "phase_result_ready": True,
            "done": False,
        },
    })
    assert observed["finalization"] == "awaiting_host"
    assert observed["phase_result_ready"] is True
    assert observed["finalized_successfully"] is False


def test_expired_rejected_and_completed_are_distinct() -> None:
    for status, expected in (
        ("host_finalization_expired", "expired"),
        ("host_finalization_rejected", "rejected"),
        ("completed", "accepted"),
    ):
        observed = main_module._daemon_cli_completion({
            "ok": status == "completed",
            "done": True,
            "job_status": status,
        })
        assert observed["finalization"] == expected
        assert observed["finalized_successfully"] is (status == "completed")


def test_model_trailing_detached_timestamp_echo_is_removed_before_envelope() -> None:
    raw = "Cześć! Jak Ci się to podoba? 🕒 2026-11-23 21:47:02"
    assert clean_model_generated_body(raw) == "Cześć! Jak Ci się to podoba?"


def test_model_timestamps_inside_meaningful_prose_are_preserved() -> None:
    for text in (
        "Witaj. 🕒 2026-11-23 21:47:02",
        "Ustalono godzinę 🕒 2026-11-23 21:47:02.",
        "Zapisz dokładnie: 🕒 2026-11-23 21:47:02",
        "Cześć? 🕒 2026-11-23 21:47:02 i potem rozmowa",
    ):
        assert clean_model_generated_body(text) == text
