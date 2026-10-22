"""Non-autobiographical, per-candidate model execution provenance.

Configured provider or an adapter's describe() is never evidence of generation.
A completed response is evidence of the adapter's returned result, while actual
model identification additionally requires a transport-observed model name.
"""
from __future__ import annotations

from typing import Any

from .base import ModelAdapterRequest, ModelAdapterResponse


def model_turn_evidence(
    request: ModelAdapterRequest,
    response: ModelAdapterResponse,
) -> dict[str, Any]:
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    turn_id = str(metadata.get("turn_id") or "").strip()
    trace_id = str(metadata.get("trace_id") or "").strip()
    completed = bool(
        response.status == "completed" and response.generated
        and bool(response.text or response.tool_calls)
    )
    attempts = response.transport.get("attempts") if isinstance(response.transport, dict) else None
    actual_model = None
    if isinstance(attempts, list):
        for attempt in reversed(attempts):
            if isinstance(attempt, dict) and isinstance(attempt.get("actual_model"), str):
                actual_model = attempt["actual_model"].strip() or None
                if actual_model:
                    break
    matched = bool(actual_model and actual_model == response.model)
    return {
        "schema_version": "jazn_model_turn_evidence/v1",
        "turn_id": turn_id or None,
        "trace_id": trace_id or None,
        "lineage_verified": bool(turn_id and trace_id),
        "adapter_id": response.adapter_id or None,
        "provider": response.provider or None,
        "declared_model": response.model or None,
        "transport_observed_model": actual_model,
        "model_identity_verified_from_provider": bool(completed and matched),
        "endpoint_used": response.endpoint_used,
        "generation_observed": completed,
        "adapter_response_status": response.status,
        "evidence_origin": "adapter_response_observed" if completed else "not_verified",
        "truth_boundary": (
            "Execution evidence of one adapter candidate only, not proof it was "
            "selected as final visible answer. Unverified model identity, route "
            "and runtime/source lineage must not be inferred from configuration."
        ),
    }
