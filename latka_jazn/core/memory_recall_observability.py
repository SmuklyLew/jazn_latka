from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from latka_jazn.version import schema_version


MEMORY_RECALL_OBSERVABILITY_VERSION = schema_version("memory_recall_observability")

_MISSING_PROVENANCE_LABELS = frozenset(
    {"", "brak dowodu", "unknown", "unavailable", "none"}
)
_MISSING_SOURCE_TYPES = frozenset({"", "unknown", "unclassified", "none"})
_REJECTED_TRUTH_STATUSES = frozenset(
    {"", "unknown", "rejected", "quarantined", "invalid", "superseded", "untrusted"}
)
_TRANSPORT_FIELDS = (
    "selected_transport",
    "fallback_reason",
    "requested_runtime_root",
    "resolved_active_root",
    "daemon_endpoint_root",
    "daemon_identity_verified",
)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _items(contract: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    raw = _mapping(contract).get("items")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _item_has_usable_provenance(item: Mapping[str, Any]) -> bool:
    metadata = _mapping(item.get("metadata"))
    source_type = str(
        metadata.get("semantic_source_type")
        or item.get("semantic_source_type")
        or ""
    ).strip().casefold()
    provenance_label = str(
        metadata.get("provenance_label")
        or item.get("provenance_label")
        or ""
    ).strip().casefold()
    truth_status = str(
        metadata.get("truth_status")
        or item.get("truth_status")
        or ""
    ).strip().casefold()
    source_locator = str(
        metadata.get("source_locator")
        or metadata.get("source_database")
        or item.get("source")
        or ""
    ).strip()
    return bool(
        source_type not in _MISSING_SOURCE_TYPES
        and provenance_label not in _MISSING_PROVENANCE_LABELS
        and truth_status not in _REJECTED_TRUTH_STATUSES
        and source_locator
    )


def build_memory_recall_observability(
    memory_context: Mapping[str, Any] | None,
    memory_recall_contract: Mapping[str, Any] | None,
    *,
    runtime_turn_id: str,
    trace_id: str,
) -> dict[str, Any]:
    """Summarize recall execution without copying private recall content.

    This contract deliberately records counts, source classes and correlation
    identifiers only. The content-bearing recall contract remains the sole
    input to NLG/finalization.
    """

    context = _mapping(memory_context)
    plan = _mapping(context.get("memory_search_plan"))
    living = _mapping(context.get("living_memory_search"))
    execution = _mapping(context.get("memory_recall_execution"))
    contract_items = _items(memory_recall_contract)
    recall_requested = plan.get("recall_requested") is True
    recall_executed = bool(
        execution.get("invoked") is True
        and execution.get("completed") is True
        and execution.get("cancelled") is not True
    )
    memory_search_ready = living.get("memory_search_ready") is True
    issue_count = len(living.get("issues") or []) if isinstance(living.get("issues"), list) else 0

    source_types: list[str] = []
    for item in contract_items:
        metadata = _mapping(item.get("metadata"))
        source_type = str(
            metadata.get("semantic_source_type")
            or item.get("semantic_source_type")
            or "unknown"
        ).strip() or "unknown"
        if source_type not in source_types:
            source_types.append(source_type)
    provenance_available = bool(
        contract_items
        and all(_item_has_usable_provenance(item) for item in contract_items)
    )

    if not recall_requested:
        status = "not_requested"
    elif not recall_executed:
        status = "recall_not_executed"
    elif not memory_search_ready:
        status = "memory_not_ready"
    elif issue_count and not contract_items:
        status = "memory_recall_unavailable"
    elif not contract_items:
        status = "recall_executed_zero_hits"
    elif not provenance_available:
        status = "recall_provenance_unavailable"
    else:
        status = "valid_grounded_recall"

    return {
        "schema_version": MEMORY_RECALL_OBSERVABILITY_VERSION,
        "memory_recall_requested": recall_requested,
        "memory_recall_executed": recall_executed,
        "memory_search_ready": memory_search_ready,
        "memory_recall_status": status,
        "memory_source_count": len(contract_items),
        "memory_provenance_available": provenance_available,
        "memory_source_types": source_types,
        "memory_issue_count": issue_count,
        "runtime_turn_id": str(runtime_turn_id),
        "trace_id": str(trace_id),
        "private_content_recorded_in_telemetry": False,
    }


def correlate_memory_recall_transport(
    observability: Mapping[str, Any] | None,
    transport: Mapping[str, Any] | None,
) -> dict[str, Any]:
    correlated = _mapping(observability)
    if not correlated:
        return {}
    transport_map = _mapping(transport)
    mismatches: list[str] = []
    for field in _TRANSPORT_FIELDS:
        transport_value = transport_map.get(field)
        if transport_value is None or transport_value == "":
            continue
        current = correlated.get(field)
        if current is not None and current != "" and current != transport_value:
            mismatches.append(field)
            continue
        correlated[field] = transport_value
    correlated["transport_correlation_valid"] = not mismatches
    correlated["transport_correlation_mismatches"] = mismatches
    return correlated


def memory_recall_truth_boundary_violation(
    observability: Mapping[str, Any] | None,
    *,
    recall_required: bool,
    expected_turn_id: str | None = None,
    expected_trace_id: str | None = None,
) -> str | None:
    data = _mapping(observability)
    if not data:
        return "memory_recall_observability_missing" if recall_required else None
    if recall_required and data.get("memory_recall_requested") is not True:
        return "memory_recall_request_mismatch"
    if data.get("memory_recall_requested") is not True:
        return None
    if data.get("memory_recall_executed") is not True:
        return "memory_recall_required_not_executed"
    if data.get("memory_search_ready") is not True:
        return "active_memory_not_ready"
    status = str(data.get("memory_recall_status") or "")
    if status == "memory_recall_unavailable":
        return "active_memory_unavailable"
    try:
        source_count = int(data.get("memory_source_count") or 0)
    except (TypeError, ValueError):
        return "memory_recall_observability_invalid"
    if source_count > 0 and data.get("memory_provenance_available") is not True:
        return "memory_recall_provenance_unavailable"
    if status == "recall_provenance_unavailable":
        return "memory_recall_provenance_unavailable"
    if expected_turn_id and str(data.get("runtime_turn_id") or "") != str(expected_turn_id):
        return "memory_recall_turn_id_mismatch"
    if expected_trace_id and str(data.get("trace_id") or "") != str(expected_trace_id):
        return "memory_recall_trace_id_mismatch"
    if data.get("transport_correlation_valid") is False:
        return "memory_recall_transport_correlation_mismatch"
    if str(data.get("selected_transport") or "") == "persistent_daemon":
        if data.get("daemon_identity_verified") is not True:
            return "daemon_identity_not_verified"
        resolved = str(data.get("resolved_active_root") or "")
        endpoint = str(data.get("daemon_endpoint_root") or "")
        if not resolved or not endpoint or resolved != endpoint:
            return "memory_runtime_root_mismatch"
    return None


__all__ = [
    "MEMORY_RECALL_OBSERVABILITY_VERSION",
    "build_memory_recall_observability",
    "correlate_memory_recall_transport",
    "memory_recall_truth_boundary_violation",
]
