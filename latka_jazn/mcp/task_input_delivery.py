from __future__ import annotations

"""Strict input delivery contract for MCP Tasks.

A gateway may acknowledge client input only after the canonical runtime
accepted it for the existing request. A timeout or mismatched receipt is
never a successful tasks/update.
"""

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Protocol
import json

MAX_RESPONSES = 64
MAX_INPUT_BYTES = 65536


class TaskInputGateway(Protocol):
    def submit_task_input(
        self,
        *,
        daemon_request_id: str,
        task_id: str,
        input_responses: Mapping[str, Any],
        request_state: str | None,
        lineage: Mapping[str, str],
        input_sha256: str,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class TaskInputDelivery:
    keys: tuple[str, ...]
    digest: str
    responses: Mapping[str, Any]

    @classmethod
    def prepare(
        cls,
        *,
        outstanding: Mapping[str, Any],
        responses: Mapping[str, Any],
    ) -> TaskInputDelivery:
        if not responses or len(responses) > MAX_RESPONSES:
            raise ValueError("task_input_key_count_invalid")
        if any(not isinstance(k, str) or not k or len(k) > 128 for k in responses):
            raise ValueError("task_input_key_invalid")
        if not set(responses).issubset(outstanding):
            raise ValueError("task_input_key_not_outstanding")
        try:
            encoded = json.dumps(responses, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (ValueError, TypeError) as exc:
            raise ValueError("task_input_payload_not_json") from exc
        if len(encoded) > MAX_INPUT_BYTES:
            raise ValueError("task_input_payload_too_large")
        return cls(keys=tuple(sorted(responses)), digest=sha256(encoded).hexdigest(), responses=responses)

    def require_runtime_receipt(
        self, receipt: Mapping[str, Any], *, request_id: str, task_id: str,
    ) -> None:
        if (
            receipt.get("accepted") is not True
            or receipt.get("daemon_request_id") != request_id
            or receipt.get("task_id") != task_id
            or receipt.get("input_sha256") != self.digest
            or not isinstance(receipt.get("accepted_keys"), list)
            or tuple(sorted(receipt["accepted_keys"])) != self.keys
        ):
            raise RuntimeError("task_input_runtime_ack_unverified")


__all__ = ["TaskInputDelivery", "TaskInputGateway", "MAX_RESPONSES", "MAX_INPUT_BYTES"]
