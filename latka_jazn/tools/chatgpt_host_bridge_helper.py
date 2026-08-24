from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, TextIO

from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import (
    CHATGPT_BRIDGE_PROTOCOL,
    CHATGPT_HOST_VISIBLE_REPLY_TEXT_FIELDS,
    chat_gpt_contract,
    persist_chatgpt_host_visible_reply,
    write_chat_bridge_payload,
)
from latka_jazn.version import schema_version
from latka_jazn.core.host_visible_finalization import finalize_host_visible_text, sha256_host_visible_text
from latka_jazn.core.json_types import is_json_object, json_object
from latka_jazn.core.message_envelope import normalize_newlines

MAX_HOST_BRIDGE_JSON_BYTES = 2 * 1024 * 1024


class ChatgptHostBridgeHelperError(ValueError):
    """Raised for controlled host-bridge helper input errors."""


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _first_nonempty_text(payload: dict[str, Any], fields: Iterable[str]) -> tuple[str, str]:
    for field in fields:
        value = payload.get(field)
        text = _safe_text(value)
        if text:
            return text, field
    return "", "<missing>"


def iter_json_values_from_text(text: str) -> Iterable[dict[str, Any]]:
    """Yield JSON object values from a JSON document or JSONL text.

    JSON Lines is the bridge format: one UTF-8 JSON value per line.  The helper
    also accepts a single pretty-printed JSON object because users often save
    the phase-1 packet to a file from a terminal.
    """
    raw = (text or "").strip()
    if not raw:
        return
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                yield value
        return
    if isinstance(value, dict):
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def read_limited_text(path: Path | str, *, max_bytes: int = MAX_HOST_BRIDGE_JSON_BYTES) -> str:
    path = Path(path)
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise ChatgptHostBridgeHelperError(
            f"Plik {path} ma {len(data)} B, limit wejścia mostu to {max_bytes} B."
        )
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ChatgptHostBridgeHelperError(
            f"Nieobsługiwane kodowanie pliku {path}. Użyj UTF-8 albo UTF-16 z BOM."
        ) from exc


def load_chatgpt_host_request_from_text(text: str) -> dict[str, Any]:
    """Select exactly one unambiguous phase-1 host-generation request."""
    matches: list[dict[str, Any]] = []
    for value in iter_json_values_from_text(text):
        bridge_value = value.get("chatgpt_host_bridge")
        if not is_json_object(bridge_value):
            presentation = json_object(value.get("chatgpt_host_presentation"))
            bridge_value = presentation.get("chatgpt_host_bridge") if presentation else None
        bridge = bridge_value if is_json_object(bridge_value) else value
        if bridge.get("phase") == "host_visible_generation_requested" and bridge.get("host_must_generate_visible_reply") is True:
            matches.append(value)
    if not matches:
        raise ChatgptHostBridgeHelperError("Nie znaleziono pakietu phase=host_visible_generation_requested.")
    if len(matches) != 1:
        raise ChatgptHostBridgeHelperError(
            f"Znaleziono {len(matches)} pakiety host-generation; wybór jest niejednoznaczny. Podaj plik z jedną turą."
        )
    return matches[0]


def load_chatgpt_host_request(path: Path | str, *, max_bytes: int = MAX_HOST_BRIDGE_JSON_BYTES) -> dict[str, Any]:
    return load_chatgpt_host_request_from_text(read_limited_text(path, max_bytes=max_bytes))


def load_external_tool_evidence(path: Path | str) -> list[dict[str, Any]]:
    """Load one bounded JSON array of host-attested external-tool evidence."""

    value = json.loads(read_limited_text(path))
    if not isinstance(value, list):
        raise ChatgptHostBridgeHelperError(
            "Plik external_tool_evidence musi zawierać tablicę JSON."
        )
    if len(value) > 8:
        raise ChatgptHostBridgeHelperError(
            "external_tool_evidence przekracza limit 8 wpisów."
        )
    evidence: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ChatgptHostBridgeHelperError(
                f"external_tool_evidence[{index}] nie jest obiektem JSON."
            )
        evidence.append(dict(item))
    return evidence


def _host_bridge_from_runtime_packet(runtime_payload: dict[str, Any]) -> dict[str, Any]:
    bridge = runtime_payload.get("chatgpt_host_bridge")
    if is_json_object(bridge):
        return bridge
    presentation = json_object(runtime_payload.get("chatgpt_host_presentation"))
    bridge = presentation.get("chatgpt_host_bridge") if presentation else None
    if is_json_object(bridge):
        return bridge
    if runtime_payload.get("phase") or runtime_payload.get("host_reply_jsonl_shape"):
        return runtime_payload
    return {}


def _trace_from_runtime_packet(runtime_payload: dict[str, Any]) -> dict[str, Any]:
    return json_object(runtime_payload.get("trace"))


def build_chatgpt_host_visible_reply_payload(
    runtime_payload: dict[str, Any],
    *,
    final_text: str,
    state_emoticon: str | None = None,
    used_memory_item_ids: Iterable[str] | None = None,
    external_tool_evidence: Iterable[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Build phase-2 JSONL from the verified phase-1 turn envelope."""
    bridge = _host_bridge_from_runtime_packet(runtime_payload)
    shape = json_object(bridge.get("host_reply_jsonl_shape"))
    trace = _trace_from_runtime_packet(runtime_payload)
    turn_contract = json_object(runtime_payload.get("runtime_turn_contract"))
    final_contract = json_object(runtime_payload.get("final_response_contract"))
    decision = json_object(runtime_payload.get("conversation_decision"))
    timestamp_contract = json_object(decision.get("timestamp_contract"))

    values: dict[str, Any] = {
        "turn_id": _safe_text(bridge.get("turn_id") or shape.get("turn_id") or trace.get("turn_id") or turn_contract.get("turn_id") or final_contract.get("turn_id")),
        "trace_id": _safe_text(bridge.get("trace_id") or shape.get("trace_id") or trace.get("trace_id") or turn_contract.get("trace_id") or final_contract.get("trace_id")),
        "timestamp_header": _safe_text(bridge.get("timestamp_header") or shape.get("timestamp_header") or trace.get("timestamp_header") or final_contract.get("timestamp_header")),
        "timezone": _safe_text(bridge.get("timezone") or shape.get("timezone") or trace.get("timezone") or final_contract.get("timezone") or timestamp_contract.get("timezone") or timestamp_contract.get("timezone_key")),
        "timestamp_sample_iso": _safe_text(bridge.get("timestamp_sample_iso") or shape.get("timestamp_sample_iso") or final_contract.get("timestamp_sample_iso") or timestamp_contract.get("sample_iso")),
        "timestamp_source": _safe_text(bridge.get("timestamp_source") or shape.get("timestamp_source") or final_contract.get("timestamp_source") or timestamp_contract.get("source")),
        "timestamp_trusted": bridge.get("timestamp_trusted") if isinstance(bridge.get("timestamp_trusted"), bool) else (shape.get("timestamp_trusted") if isinstance(shape.get("timestamp_trusted"), bool) else (final_contract.get("timestamp_trusted") if isinstance(final_contract.get("timestamp_trusted"), bool) else timestamp_contract.get("trusted"))),
        "author_id": _safe_text(bridge.get("author_id") or shape.get("author_id") or final_contract.get("author_id")),
        "author_label": _safe_text(bridge.get("author_label") or shape.get("author_label") or final_contract.get("author_label")),
        "author_source": _safe_text(bridge.get("author_source") or shape.get("author_source") or final_contract.get("author_source")),
        "state_emoticon": _safe_text(bridge.get("state_emoticon") or shape.get("state_emoticon") or final_contract.get("state_emoticon")),
        "host_request_contract_hash": _safe_text(bridge.get("host_request_contract_hash") or shape.get("host_request_contract_hash")),
    }
    text = normalize_newlines(final_text)
    memory_item_ids = [_safe_text(item) for item in (used_memory_item_ids or [])]
    tool_evidence_items = list(external_tool_evidence or [])
    missing: list[str] = []
    phase = _safe_text(bridge.get("phase"))
    if phase != "host_visible_generation_requested" or bridge.get("host_must_generate_visible_reply") is not True:
        missing.append("chatgpt_host_bridge.phase=host_visible_generation_requested")
    for field in ("turn_id", "trace_id", "timestamp_header", "timezone", "timestamp_sample_iso", "timestamp_source", "author_id", "author_label", "author_source", "state_emoticon"):
        if not values[field]:
            missing.append(field)
    if not isinstance(values["timestamp_trusted"], bool):
        missing.append("timestamp_trusted")
    if not values["host_request_contract_hash"]:
        missing.append("host_request_contract_hash")
    if not text.strip():
        missing.append("final_text")
    if state_emoticon is not None and _safe_text(state_emoticon) != values["state_emoticon"]:
        missing.append("state_emoticon_mismatch")
    if len(memory_item_ids) > 8:
        missing.append("used_memory_item_ids_limit_exceeded")
    for index, item_id in enumerate(memory_item_ids):
        if not item_id:
            missing.append(f"used_memory_item_ids_empty:{index}")
    if len(tool_evidence_items) > 8:
        missing.append("external_tool_evidence_limit_exceeded")
    for index, item in enumerate(tool_evidence_items):
        if not isinstance(item, dict):
            missing.append(f"external_tool_evidence_not_object:{index}")
    if missing:
        return None, missing

    original_hash = sha256_host_visible_text(text)
    finalization = finalize_host_visible_text(
        required_timestamp_header=values["timestamp_header"],
        timezone=values["timezone"],
        timestamp_sample_iso=values["timestamp_sample_iso"],
        timestamp_source=values["timestamp_source"],
        timestamp_trusted=values["timestamp_trusted"],
        author_id=values["author_id"],
        author_label=values["author_label"],
        author_source=values["author_source"],
        state_emoticon=values["state_emoticon"],
        turn_id=values["turn_id"],
        trace_id=values["trace_id"],
        text=text,
        supplied_turn_id=values["turn_id"],
        supplied_trace_id=values["trace_id"],
        supplied_text_sha256=original_hash,
        max_utf8_bytes=MAX_HOST_BRIDGE_JSON_BYTES,
    )
    if not finalization.accepted:
        return None, [f"finalization:{item.code}" for item in finalization.violations]

    payload: dict[str, Any] = {
        "type": "host_visible_reply",
        **values,
        "final_text": finalization.final_visible_text,
        "final_text_sha256": sha256_host_visible_text(finalization.final_visible_text),
        "used_memory_item_ids": memory_item_ids,
        "external_tool_evidence": [dict(item) for item in tool_evidence_items],
        "finalization_result": finalization.to_dict(),
        "builder": {
            "schema_version": schema_version("chatgpt_host_visible_reply_builder"),
            "source": "chatgpt_host_bridge_helper",
            "truth_boundary": "Ten JSONL nie jest lokalną generacją modelu. To widoczna odpowiedź hosta ChatGPT oparta wyłącznie na zweryfikowanej kopercie tury.",
        },
    }
    return payload, []

def build_chatgpt_host_reply_helper_meta(*, line_index: int | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "protocol_version": CHATGPT_BRIDGE_PROTOCOL,
        "accepted_input_fields": list(CHATGPT_HOST_VISIBLE_REPLY_TEXT_FIELDS),
        "accepted_input_shapes": [
            "json_object.type=host_visible_reply",
            "runtime_packet.chatgpt_host_bridge.host_reply_jsonl_shape + final_text",
        ],
        "preferred_input_field": "final_text",
        "client": "chatgpt_host_bridge_helper",
        "lifecycle": "chatgpt_host_visible_reply_helper",
        "mode": "chatgpt_bridge_without_api_key",
        "command": "--chat-gpt",
        "requires_api_key": False,
        "uses_openai_api": False,
        "canonical_command": "--chat-gpt",
        "input_kind": "json_host_visible_reply_helper",
        "input_field": "final_text",
        "truth_boundary": "Helper buduje albo zapisuje host_visible_reply bez ręcznego składania JSON w shellu.",
    }
    if line_index is not None:
        meta["line_index"] = line_index
    return meta


def record_chatgpt_host_visible_reply_from_runtime_packet(
    *,
    config: JaznConfig,
    runtime_payload: dict[str, Any],
    final_text: str,
    state_emoticon: str | None = None,
    used_memory_item_ids: Iterable[str] | None = None,
    external_tool_evidence: Iterable[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    reply_payload, missing = build_chatgpt_host_visible_reply_payload(
        runtime_payload,
        final_text=final_text,
        state_emoticon=state_emoticon,
        used_memory_item_ids=used_memory_item_ids,
        external_tool_evidence=external_tool_evidence,
    )
    if missing:
        return None, missing
    return persist_chatgpt_host_visible_reply(
        config=config,
        payload=reply_payload or {},
        chat_bridge_meta=build_chatgpt_host_reply_helper_meta(line_index=1),
        contract=chat_gpt_contract().to_dict(),
    )


def _read_stdin_limited(stdin: TextIO, *, max_bytes: int = MAX_HOST_BRIDGE_JSON_BYTES) -> str:
    text = stdin.read(max_bytes + 1)
    if len(text.encode("utf-8")) > max_bytes:
        raise ChatgptHostBridgeHelperError(f"stdin przekroczył limit {max_bytes} B dla pakietu host bridge.")
    return text


def _resolve_final_text(args: argparse.Namespace) -> str:
    sources = [bool(args.final_text), bool(args.final_text_file), bool(args.message)]
    if sum(sources) != 1:
        raise ChatgptHostBridgeHelperError("Podaj dokładnie jedno źródło tekstu: --final-text, --final-text-file albo tekst po --.")
    if args.final_text:
        return args.final_text
    if args.final_text_file:
        return read_limited_text(args.final_text_file)
    message = list(args.message or [])
    if message and message[0] == "--":
        message = message[1:]
    return " ".join(message).strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatgpt_host_bridge_reply.py",
        description="Build or record a --chat-gpt host_visible_reply from a phase-1 runtime JSONL packet.",
        allow_abbrev=False,
    )
    parser.add_argument("--root", type=Path, default=None, help="Folder główny aktywnego runtime Jaźni.")
    parser.add_argument("--from-runtime-json", type=Path, default=None, help="Plik z wynikiem fazy 1 --chat-gpt JSONL. Użyj '-' albo pomiń, aby czytać stdin.")
    parser.add_argument("--final-text", default=None, help="Widoczna odpowiedź hosta ChatGPT do zapisania w runtime.")
    parser.add_argument("--final-text-file", type=Path, default=None, help="Plik UTF-8 z widoczną odpowiedzią hosta ChatGPT.")
    parser.add_argument("--state-emoticon", default=None, help="Opcjonalna ikona stanu zapisywana przy final_visible_reply.")
    parser.add_argument(
        "--used-memory-item-id",
        action="append",
        default=[],
        help="Identyfikator źródła pamięci faktycznie użytego przez hosta; maksymalnie 8.",
    )
    parser.add_argument(
        "--external-tool-evidence-json",
        type=Path,
        default=None,
        help="Plik JSON z maksymalnie 8 wpisami host-attested evidence dla GitHub/web.run.",
    )
    parser.add_argument("--build-only", action="store_true", help="Tylko zbuduj JSONL host_visible_reply; nie zapisuj do runtime.")
    parser.add_argument("--pretty", action="store_true", help="Wypisz JSON z wcięciami zamiast jednej linii JSONL.")
    parser.add_argument("message", nargs=argparse.REMAINDER, help="Alternatywnie: tekst hosta po --, bez ręcznego składania JSON.")
    return parser


def main(argv: list[str] | None = None, *, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    if stdout is None:
        raise RuntimeError("chatgpt_host_bridge_stdout_unavailable")
    try:
        if args.from_runtime_json and str(args.from_runtime_json) != "-":
            runtime_payload = load_chatgpt_host_request(args.from_runtime_json)
        else:
            if stdin is None:
                raise ChatgptHostBridgeHelperError("stdin jest niedostępny dla pakietu host bridge.")
            runtime_payload = load_chatgpt_host_request_from_text(_read_stdin_limited(stdin))
        final_text = _resolve_final_text(args)
        external_tool_evidence = (
            load_external_tool_evidence(args.external_tool_evidence_json)
            if args.external_tool_evidence_json is not None
            else []
        )
        reply_payload, missing = build_chatgpt_host_visible_reply_payload(
            runtime_payload,
            final_text=final_text,
            state_emoticon=args.state_emoticon,
            used_memory_item_ids=args.used_memory_item_id,
            external_tool_evidence=external_tool_evidence,
        )
        if missing:
            payload = {
                "schema_version": schema_version("chatgpt_host_visible_reply_helper_error"),
                "ok": False,
                "error_code": "invalid_host_visible_reply_request",
                "missing": missing,
                "error": "Brakuje pól do zbudowania host_visible_reply: " + ", ".join(missing),
            }
            write_chat_bridge_payload(stdout, payload)
            return 2
        if args.build_only:
            output = reply_payload or {}
        else:
            output, persist_missing = persist_chatgpt_host_visible_reply(
                config=JaznConfig(root=args.root) if args.root else JaznConfig(),
                payload=reply_payload or {},
                chat_bridge_meta=build_chatgpt_host_reply_helper_meta(line_index=1),
                contract=chat_gpt_contract().to_dict(),
            )
            if persist_missing:
                output = {
                    "schema_version": schema_version("chatgpt_host_visible_reply_helper_error"),
                    "ok": False,
                    "error_code": "invalid_host_visible_reply",
                    "missing": persist_missing,
                    "error": "Brakuje pól dla host_visible_reply: " + ", ".join(persist_missing),
                }
                write_chat_bridge_payload(stdout, output)
                return 2
        if args.pretty:
            stdout.write(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            stdout.flush()
        else:
            write_chat_bridge_payload(
                stdout,
                output or {},
                output_mode="jsonl" if args.build_only else "host_packet",
            )
        return 0
    except (OSError, json.JSONDecodeError, ChatgptHostBridgeHelperError) as exc:
        payload = {
            "schema_version": schema_version("chatgpt_host_visible_reply_helper_error"),
            "ok": False,
            "error_code": "host_visible_reply_helper_failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_chat_bridge_payload(stdout, payload)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
