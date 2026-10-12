from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.tools import chatgpt_host_bridge_helper


def _host_generation_packet() -> dict[str, Any]:
    return {
        "chatgpt_host_bridge": {
            "phase": "host_visible_generation_requested",
            "host_must_generate_visible_reply": True,
            "turn_id": "turn-helper-provenance",
            "trace_id": "trace-helper-provenance",
            "timestamp_header": "🕒 2026-08-24 22:00:00",
            "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": "2026-08-24T20:00:00+00:00",
            "timestamp_source": "test",
            "timestamp_trusted": True,
            "author_id": "latka_runtime",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
            "state_emoticon": "🌿",
            "host_request_contract_hash": "a" * 64,
        }
    }


def test_loader_uses_the_top_level_packet_when_nested_bridge_is_not_an_object() -> None:
    packet: dict[str, Any] = {
        "phase": "host_visible_generation_requested",
        "host_must_generate_visible_reply": True,
        "chatgpt_host_bridge": ["invalid", "shape"],
    }

    loaded = chatgpt_host_bridge_helper.load_chatgpt_host_request_from_text(
        json.dumps(packet)
    )

    assert loaded == packet


def test_reply_builder_rejects_non_object_nested_contracts() -> None:
    packet: dict[str, Any] = {
        "chatgpt_host_bridge": {
            "phase": "host_visible_generation_requested",
            "host_reply_jsonl_shape": ["invalid", "shape"],
        },
        "runtime_turn_contract": ["invalid"],
        "final_response_contract": ["invalid"],
        "conversation_decision": ["invalid"],
    }

    payload, missing = (
        chatgpt_host_bridge_helper.build_chatgpt_host_visible_reply_payload(
            packet,
            final_text="Odpowiedź",
        )
    )

    assert payload is None
    assert "turn_id" in missing
    assert "timestamp_trusted" in missing


def test_reply_builder_preserves_declared_memory_and_external_tool_evidence() -> None:
    evidence = [
        {
            "tool": "web.run",
            "operation": "search",
            "source_refs": ["turn12search3"],
            "source_urls": ["https://example.org/source"],
        }
    ]

    payload, missing = chatgpt_host_bridge_helper.build_chatgpt_host_visible_reply_payload(
        _host_generation_packet(),
        final_text="Przywołuję źródłowy fragment i wynik wyszukiwania.",
        used_memory_item_ids=["memory-2025-1"],
        external_tool_evidence=evidence,
    )

    assert missing == []
    assert payload is not None
    assert payload["used_memory_item_ids"] == ["memory-2025-1"]
    assert payload["external_tool_evidence"] == evidence


def test_helper_cli_forwards_memory_ids_and_bounded_tool_evidence(
    tmp_path: Path,
) -> None:
    evidence = [
        {
            "tool": "GitHub",
            "operation": "fetch_file",
            "source_refs": ["turn27file0"],
            "source_urls": ["https://github.com/SmuklyLew/jazn_latka"],
        }
    ]
    evidence_path = tmp_path / "external-tool-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    output = io.StringIO()

    exit_code = chatgpt_host_bridge_helper.main(
        [
            "--build-only",
            "--used-memory-item-id",
            "memory-2025-1",
            "--external-tool-evidence-json",
            str(evidence_path),
            "--final-text",
            "Przywołuję źródłowy fragment i wynik z GitHub.",
        ],
        stdin=io.StringIO(json.dumps(_host_generation_packet())),
        stdout=output,
    )

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["used_memory_item_ids"] == ["memory-2025-1"]
    assert payload["external_tool_evidence"] == evidence


def test_reply_builder_rejects_unbounded_memory_and_tool_declarations() -> None:
    payload, missing = chatgpt_host_bridge_helper.build_chatgpt_host_visible_reply_payload(
        _host_generation_packet(),
        final_text="Odpowiedź",
        used_memory_item_ids=[f"memory-{index}" for index in range(9)],
        external_tool_evidence=[{} for _ in range(9)],
    )

    assert payload is None
    assert "used_memory_item_ids_limit_exceeded" in missing
    assert "external_tool_evidence_limit_exceeded" in missing


def test_helper_reports_unavailable_default_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = io.StringIO()
    monkeypatch.setattr(chatgpt_host_bridge_helper.sys, "stdin", None)

    exit_code = chatgpt_host_bridge_helper.main(
        ["--build-only", "--final-text", "Odpowiedź"],
        stdout=output,
    )

    assert exit_code == 2
    error = json.loads(output.getvalue())
    assert error["error_code"] == "host_visible_reply_helper_failed"
    assert "stdin jest niedostępny" in error["error"]


def test_helper_fails_explicitly_when_default_stdout_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chatgpt_host_bridge_helper.sys, "stdout", None)

    with pytest.raises(
        RuntimeError,
        match="chatgpt_host_bridge_stdout_unavailable",
    ):
        chatgpt_host_bridge_helper.main(
            ["--build-only", "--final-text", "Odpowiedź"],
            stdin=io.StringIO("{}"),
        )
