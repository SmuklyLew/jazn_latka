from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from latka_jazn.core.chat_command_contract import extract_chatgpt_host_visible_reply_payload
from latka_jazn.core.engine import JaznEngine
from latka_jazn.core.model_executor_preflight import resolve_model_executor
from latka_jazn.memory.event_ledger import LedgerAppendResult, RuntimeEventLedger


SAMPLE = datetime(2026, 7, 28, 14, 30, 0, tzinfo=timezone.utc)
SAMPLE_ISO = SAMPLE.isoformat()
HEADER = f"🕒 {SAMPLE.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _FirstAttemptOllamaAdapter:
    def describe(self) -> dict:
        return {
            "adapter_id": "local_llm_adapter",
            "provider": "ollama",
            "model": "gemma3:latest",
            "configured": True,
            "can_attempt_model_guided_speech": True,
            "can_generate_model_guided_speech": False,
        }


def test_model_executor_allows_configured_ollama_first_attempt() -> None:
    preflight = resolve_model_executor(_FirstAttemptOllamaAdapter())

    assert preflight.available is True
    assert preflight.executor == "local_model"
    assert preflight.retry_allowed is True
    assert preflight.adapter_id == "local_llm_adapter"
    assert preflight.provider == "ollama"
    assert preflight.model == "gemma3:latest"
    assert preflight.reason == "configured_local_adapter_ready_for_first_attempt"


def test_host_reply_extraction_preserves_exact_trailing_newline_for_hash() -> None:
    final_text = "Treść hosta zachowana bajt w bajt.\n"
    payload = {
        "type": "host_visible_reply",
        "turn_id": "turn-1",
        "trace_id": "trace-1",
        "timestamp_header": HEADER,
        "timezone": "Europe/Warsaw",
        "timestamp_sample_iso": SAMPLE_ISO,
        "timestamp_source": "local_fallback",
        "timestamp_trusted": False,
        "author_id": "latka_runtime",
        "author_label": "Łatka",
        "author_source": "jazn_runtime",
        "state_emoticon": "🛠️",
        "final_text": final_text,
        "final_text_sha256": _sha(final_text),
    }

    extracted, missing = extract_chatgpt_host_visible_reply_payload(payload)

    assert missing == []
    assert extracted["final_text"] == final_text
    assert _sha(extracted["final_text"]) == payload["final_text_sha256"]


def test_event_ledger_accepts_and_persists_final_reply_client_context(tmp_path) -> None:
    ledger = RuntimeEventLedger(tmp_path, version="test-version")
    client_context = {
        "client": "chatgpt_visible_layer_jsonl",
        "lifecycle": "chatgpt_host_visible_reply_record",
    }
    envelope = {
        "schema_version": "external_final_visible_reply_envelope/v2",
        "trace": {
            "turn_id": "turn-1",
            "trace_id": "trace-1",
            "timestamp_header": HEADER,
        },
        "final_response_contract": {},
        "dialogue_state": {},
        "affect_mix": {},
    }

    result = ledger.append_final_visible_reply(
        envelope,
        final_text=f"{HEADER}\n🛠️ Łatka\n\nTest zapisu.",
        source="chatgpt_visible_layer_jsonl",
        client_context=client_context,
        local_time_label=HEADER,
    )

    assert result is not None
    records = [
        json.loads(line)
        for line in ledger.conversation_turns_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records[-1]["client_context"] == client_context
    assert records[-1]["metadata"]["turn_id"] == "turn-1"
    assert records[-1]["metadata"]["trace_id"] == "trace-1"


class _RecordingLedger:
    def __init__(self) -> None:
        self.call: dict | None = None

    def append_final_visible_reply(
        self,
        envelope: dict,
        *,
        final_text: str,
        source: str,
        client_context: dict,
        local_time_label: str,
    ) -> LedgerAppendResult:
        self.call = {
            "envelope": envelope,
            "final_text": final_text,
            "source": source,
            "client_context": client_context,
            "local_time_label": local_time_label,
        }
        return LedgerAppendResult(
            path="memory/raw/runtime_events/runtime_events_0001.jsonl",
            event_id="event-1",
            event_type="final_visible_assistant_reply",
            payload_sha256="a" * 64,
            bytes_written=123,
        )


def test_engine_persists_host_reply_with_keyword_contract_and_dict_result() -> None:
    engine = object.__new__(JaznEngine)
    engine.config = SimpleNamespace(version="test-version")
    ledger = _RecordingLedger()
    engine.event_ledger = ledger
    client_context = {
        "client": "chatgpt_visible_layer_jsonl",
        "lifecycle": "chatgpt_host_visible_reply_record",
    }

    result = engine.persist_final_visible_reply(
        turn_id="turn-1",
        trace_id="trace-1",
        timestamp_header=HEADER,
        timezone="Europe/Warsaw",
        timestamp_sample_iso=SAMPLE_ISO,
        timestamp_source="local_fallback",
        timestamp_trusted=False,
        author_id="latka_runtime",
        author_label="Łatka",
        author_source="jazn_runtime",
        final_text="Test końcowy mostu.",
        state_emoticon="🛠️",
        source="chatgpt_visible_layer_jsonl",
        client_context=client_context,
    )

    assert ledger.call is not None
    assert ledger.call["client_context"] == client_context
    assert ledger.call["local_time_label"] == HEADER
    assert ledger.call["final_text"] == result["final_visible_text"]
    assert result["turn_id"] == "turn-1"
    assert result["trace_id"] == "trace-1"
    assert result["final_visible_reply_capture"]["final_visible_text"] == result["final_visible_text"]
    assert result["ledger_append"]["event_id"] == "event-1"
    assert result["ledger_append"]["event_type"] == "final_visible_assistant_reply"
