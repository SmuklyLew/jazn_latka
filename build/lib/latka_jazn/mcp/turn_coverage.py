from __future__ import annotations

"""Fail-closed reconciliation of host messages and accepted Jaźń turns.

A live daemon cannot observe ChatGPT messages that were never sent to it.
The host MUST independently supply expected message IDs and SHA-256 digests.
No raw user text or reply bodies are needed. This is not an auto-router.
"""

import argparse
import hmac
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from latka_jazn.core.host_visible_finalization import sha256_host_visible_text

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_RECORDS = 10_000
_MAX_JSON_BYTES = 2_097_152


def _id(value: object) -> str:
    return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= 128 else ""


def _digest(value: object) -> str:
    candidate = value.strip().lower() if isinstance(value, str) else ""
    return candidate if _SHA256.fullmatch(candidate) else ""


def _object(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _final_result(record: Mapping[str, Any]) -> Mapping[str, Any]:
    # MCP returns structuredContent; operators may provide the inner object.
    outer = _object(record.get("final"))
    inner = outer.get("structuredContent")
    return _object(inner) if isinstance(inner, Mapping) else outer


def _report(reason: str, *, expected_count: int = 0) -> dict[str, Any]:
    return {
        "schema_version": "jazn_chatgpt_turn_coverage/v1",
        "ok": False,
        "reason_code": reason,
        "expected_count": expected_count,
        "supplied_host_manifest_coverage_verified": False,
        "chatgpt_platform_auto_routing_verified": False,
        "current_message_toolset_verified": False,
        "truth_boundary": (
            "Only an independently supplied host manifest can be reconciled with "
            "gate/finalization receipts. Unlisted ChatGPT messages are unknowable "
            "from Jaźń alone. No server report can certify conversation-wide "
            "automatic MCP invocation or current-message tool availability."
        ),
    }


def audit_turn_coverage(expected: object, observed: object) -> dict[str, Any]:
    """Reconcile host [{message_id,user_text_sha256}] with runtime receipts.

    Each observed row contains message_id, gate (host_pre_response_gate
    telemetry), and final (accepted MCP display_exact result). Host origin
    and completeness of the expected manifest must be validated externally.
    """
    if not isinstance(expected, list) or not isinstance(observed, list):
        return _report("invalid_manifest_type")
    if not expected:
        return _report("expected_host_manifest_missing")
    if len(expected) > _MAX_RECORDS or len(observed) > _MAX_RECORDS:
        return _report("manifest_record_limit_exceeded")

    expected_by_id: dict[str, str] = {}
    for item in expected:
        row = _object(item)
        message_id = _id(row.get("message_id"))
        digest = _digest(row.get("user_text_sha256"))
        if not message_id or not digest:
            return _report("invalid_expected_message_binding")
        if message_id in expected_by_id:
            return _report("duplicate_expected_message_id")
        expected_by_id[message_id] = digest

    observed_by_id: dict[str, Mapping[str, Any]] = {}
    for item in observed:
        row = _object(item)
        message_id = _id(row.get("message_id"))
        if not message_id:
            return _report("invalid_observed_message_id", expected_count=len(expected))
        if message_id in observed_by_id:
            return _report("duplicate_observed_message_id", expected_count=len(expected))
        observed_by_id[message_id] = row

    missing = sorted(set(expected_by_id).difference(observed_by_id))
    unexpected = sorted(set(observed_by_id).difference(expected_by_id))
    rejected: list[str] = []
    used_turn_ids: set[str] = set()
    used_request_hashes: set[str] = set()
    accepted_count = 0
    for message_id, digest in expected_by_id.items():
        if message_id not in observed_by_id:
            continue
        row = observed_by_id[message_id]
        gate = _object(row.get("gate"))
        final = _final_result(row)
        turn_id, trace_id = _id(gate.get("runtime_turn_id")), _id(gate.get("trace_id"))
        final_turn_id, final_trace_id = _id(final.get("turn_id")), _id(final.get("trace_id"))
        request_hash = _digest(final.get("host_request_contract_hash"))
        text_digest = _digest(gate.get("user_text_sha256"))
        finalized_digest = _digest(final.get("final_text_sha256"))
        final_outer = _object(row.get("final"))
        source_gate = _object(final.get("host_pre_response_gate"))
        final_text = final.get("final_visible_text")
        text_integrity = (
            not isinstance(final_text, str)
            or (
                bool(final_text)
                and hmac.compare_digest(finalized_digest, sha256_host_visible_text(final_text))
            )
        )
        two_phase_accepted = (
            gate.get("presentation_action") == "generate_then_finalize"
            and final.get("accepted") is True
            and bool(request_hash)
        )
        # A self-finalized runtime reply uses display_exact immediately:
        # there is no host continuation token or phase-2 accepted flag.
        direct_exact_accepted = (
            gate.get("presentation_action") == "display_exact"
            and gate.get("visible_output_source") == "runtime_exact"
            and final.get("visible_output_source") == "runtime_exact"
            and final.get("host_route_bound") is True
            and source_gate.get("host_route_bound") is True
            and source_gate.get("presentation_action") == "display_exact"
            and hmac.compare_digest(_digest(source_gate.get("user_text_sha256")), digest)
            and _id(source_gate.get("runtime_turn_id")) == turn_id
            and _id(source_gate.get("trace_id")) == trace_id
        )
        valid = (
            gate.get("host_pre_response_gate") is True
            and gate.get("runtime_turn_invoked") is True
            and gate.get("turn_ingress_gate_enforced") is True
            and gate.get("host_route_bound") is True
            and gate.get("host_routing_bypass_detected") is not True
            and hmac.compare_digest(text_digest, digest)
            and bool(turn_id and trace_id)
            and final_outer.get("isError") is not True
            and final.get("ok") is True
            and final.get("action") == "display_exact"
            and final.get("must_display_exactly") is True
            and bool(finalized_digest)
            and text_integrity
            and hmac.compare_digest(turn_id, final_turn_id)
            and hmac.compare_digest(trace_id, final_trace_id)
            and turn_id not in used_turn_ids
            and (not request_hash or request_hash not in used_request_hashes)
            and (two_phase_accepted or direct_exact_accepted)
        )
        if not valid:
            rejected.append(message_id)
            continue
        used_turn_ids.add(turn_id)
        if request_hash:
            used_request_hashes.add(request_hash)
        accepted_count += 1

    complete = not (missing or unexpected or rejected)
    return {
        **_report(
            "supplied_host_manifest_covered" if complete else "host_turn_coverage_incomplete",
            expected_count=len(expected_by_id),
        ),
        "ok": complete,
        "observed_count": len(observed_by_id),
        "accepted_count": accepted_count,
        "missing_message_ids": missing,
        "unexpected_message_ids": unexpected,
        "unaccepted_message_ids": rejected,
        "supplied_host_manifest_coverage_verified": complete,
    }


def _read_array(path: Path) -> object:
    if path.stat().st_size > _MAX_JSON_BYTES:
        raise ValueError("input_file_too_large")
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only host-manifest turn coverage audit (no replay)",
        allow_abbrev=False,
    )
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--observed", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_turn_coverage(_read_array(args.expected), _read_array(args.observed))
    except (OSError, ValueError, UnicodeError) as exc:
        result = _report(f"input_unavailable_or_invalid:{type(exc).__name__}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
