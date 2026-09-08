from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("turn_pipeline_contract")


@dataclass(slots=True)
class TurnPipelineContract:
    turn_id: str
    trace_id: str
    user_text_sha256: str
    identity_canon_sha256: str
    runtime_owns_turn: bool
    stages: dict[str, str]
    tool_policy: dict[str, Any]
    private_chain_of_thought_persisted: bool = False
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Kontrakt opisuje jawne etapy sterowania turą i ich stan. Nie zawiera prywatnego chain-of-thought; "
        "rozumowanie jest reprezentowane jako bounded operational plan i bramki weryfikacji."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_turn_pipeline_contract(
    *,
    turn_id: str,
    trace_id: str,
    user_text_sha256: str,
    identity_canon_sha256: str,
    host_generation_context: Mapping[str, Any] | None,
    requires_host_generation: bool,
    runtime_final_available: bool,
) -> dict[str, Any]:
    context = dict(host_generation_context or {})
    model_context = context.get("model_context") if isinstance(context.get("model_context"), Mapping) else {}
    thought = model_context.get("operational_thought_frame") if isinstance(model_context, Mapping) and isinstance(model_context.get("operational_thought_frame"), Mapping) else {}
    tool_policy = context.get("host_tool_turn_policy") if isinstance(context.get("host_tool_turn_policy"), Mapping) else {}
    stages = {
        "input_bound": "complete",
        "runtime_routing": "complete",
        "identity_context": "complete" if re.fullmatch(r"[0-9a-f]{64}", str(identity_canon_sha256 or "")) else "blocked",
        "operational_reasoning_plan": "complete" if thought else "degraded",
        "tool_authorization": "complete" if tool_policy.get("runtime_owns_turn") is True else "degraded",
        "candidate_generation": "host_pending" if requires_host_generation else "complete",
        "candidate_evaluation": "host_pending" if requires_host_generation else "complete",
        "runtime_finalization": "host_pending" if requires_host_generation else ("complete" if runtime_final_available else "blocked"),
        "visible_reply_authority": "complete" if runtime_final_available else ("host_pending" if requires_host_generation else "blocked"),
    }
    return TurnPipelineContract(
        turn_id=str(turn_id or ""),
        trace_id=str(trace_id or ""),
        user_text_sha256=str(user_text_sha256 or "").lower(),
        identity_canon_sha256=str(identity_canon_sha256 or "").lower(),
        runtime_owns_turn=True,
        stages=stages,
        tool_policy=dict(tool_policy),
    ).to_dict()


def finalize_turn_pipeline_contract(value: Any) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, Mapping) else {}
    stages = dict(payload.get("stages") or {})
    for key in ("candidate_generation", "candidate_evaluation", "runtime_finalization", "visible_reply_authority"):
        stages[key] = "complete"
    payload["stages"] = stages
    payload["runtime_owns_turn"] = True
    payload["private_chain_of_thought_persisted"] = False
    return payload


def validate_turn_pipeline_contract(value: Any) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, Mapping) else {}
    violations: list[str] = []
    if payload.get("runtime_owns_turn") is not True:
        violations.append("runtime_turn_ownership_missing")
    if payload.get("private_chain_of_thought_persisted") is not False:
        violations.append("private_chain_of_thought_must_not_be_persisted")
    for field in ("user_text_sha256", "identity_canon_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get(field) or "").lower()):
            violations.append(f"invalid_sha256:{field}")
    stages = payload.get("stages") if isinstance(payload.get("stages"), Mapping) else {}
    if stages.get("input_bound") != "complete" or stages.get("runtime_routing") != "complete":
        violations.append("turn_pipeline_not_rooted_in_runtime_input_and_routing")
    if stages.get("visible_reply_authority") == "complete" and stages.get("runtime_finalization") != "complete":
        violations.append("visible_reply_authorized_before_runtime_finalization")
    policy = payload.get("tool_policy") if isinstance(payload.get("tool_policy"), Mapping) else {}
    if policy and policy.get("tool_results_cannot_be_voice_source") is not True:
        violations.append("tool_voice_boundary_missing")
    return {
        "ok": not violations,
        "violations": violations,
        "schema_version": schema_version("turn_pipeline_contract_validation"),
    }
