from __future__ import annotations

from typing import Iterable

from latka_jazn.bootstrap.chatgpt_host_discovery_evidence import HostDiscoveryEvidence
from latka_jazn.bootstrap.chatgpt_ingress_policy import (
    ChatGptIngressMode,
    local_executor_fallback_allowed,
    normalize_chatgpt_ingress_mode,
)
from latka_jazn.bootstrap.chatgpt_host_preflight_attachment import aggregate_attachment_state
from latka_jazn.bootstrap.chatgpt_host_preflight_route import resolve_preflight_route
from latka_jazn.bootstrap.chatgpt_host_preflight_types import ChatGptHostPreflightDecision
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutorObservation,
    aggregate_host_executor_observations,
)
from latka_jazn.packaging.attachment_materialization import AttachmentMaterializationReport
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("chatgpt_host_preflight")


def _executor_availability_evidence(capability: object) -> bool | None:
    surfaces = tuple(getattr(capability, "surfaces", ()) or ())
    states = tuple(str(surface.get("executor_state") or "unknown") for surface in surfaces)
    if any(state == "available" for state in states):
        return True
    if states and all(state == "host_executor_unavailable" for state in states):
        return False
    return None


def _remote_runtime_availability_evidence(capability: object) -> bool | None:
    if bool(getattr(capability, "remote_runtime_transport_available", False)):
        return True

    surfaces = tuple(getattr(capability, "surfaces", ()) or ())
    remote_probe_observed = any(
        str(surface.get("remote_runtime_transport") or "none") != "none"
        or surface.get("remote_runtime_reason_code") is not None
        for surface in surfaces
    )
    if remote_probe_observed:
        return False
    return None


def plan_chatgpt_host_preflight(
    executor_observations: Iterable[HostExecutorObservation],
    *,
    attachment_reports: Iterable[AttachmentMaterializationReport] = (),
    package_required: bool = False,
    discovery_evidence: HostDiscoveryEvidence | None = None,
    ingress_mode: ChatGptIngressMode | str = ChatGptIngressMode.OPERATOR_RECOVERY,
) -> ChatGptHostPreflightDecision:
    mode = normalize_chatgpt_ingress_mode(ingress_mode)
    capability = aggregate_host_executor_observations(executor_observations)
    discovery = discovery_evidence or HostDiscoveryEvidence()
    reports = tuple(attachment_reports)
    package_state = aggregate_attachment_state(reports)
    route = resolve_preflight_route(
        capability,
        package_state=package_state,
        package_required=package_required,
        ingress_mode=mode,
    )
    return ChatGptHostPreflightDecision(
        schema_version=SCHEMA_VERSION,
        environment_state=capability.environment_state,
        filesystem_state=capability.filesystem_state,
        package_state=package_state,
        runtime_state="unverified",
        executor_available=_executor_availability_evidence(capability),
        library_search_available=discovery.library_search_available,
        library_materialize_available=discovery.library_materialize_available,
        system_search_attempted=discovery.system_search_attempted,
        system_candidate_found=discovery.system_candidate_found,
        remote_runtime_available=_remote_runtime_availability_evidence(capability),
        ingress_mode=mode,
        local_executor_fallback_allowed=local_executor_fallback_allowed(mode),
        bootstrap_allowed=route.bootstrap_allowed,
        remote_runtime_allowed=route.remote_runtime_allowed,
        handoff_required=route.handoff_required,
        next_action=route.next_action,
        execution_route=route.execution_route,
        reason_code=route.reason_code,
        canonical_resume_entrypoint=route.resume,
        capability_snapshot=capability,
        attachments=tuple(report.to_dict() for report in reports),
        handoff_state=capability.execution_handoff_state,
    )


def plan_chatgpt_adaptive_ingress_preflight(
    executor_observations: Iterable[HostExecutorObservation],
    *,
    attachment_reports: Iterable[AttachmentMaterializationReport] = (),
    package_required: bool = False,
    discovery_evidence: HostDiscoveryEvidence | None = None,
) -> ChatGptHostPreflightDecision:
    """Plan one ordinary ChatGPT message with remote-first bounded local fallback."""

    return plan_chatgpt_host_preflight(
        executor_observations,
        attachment_reports=attachment_reports,
        package_required=package_required,
        discovery_evidence=discovery_evidence,
        ingress_mode=ChatGptIngressMode.HYBRID_ADAPTIVE,
    )


def plan_chatgpt_remote_ingress_preflight(
    executor_observations: Iterable[HostExecutorObservation],
    *,
    attachment_reports: Iterable[AttachmentMaterializationReport] = (),
    package_required: bool = False,
    discovery_evidence: HostDiscoveryEvidence | None = None,
) -> ChatGptHostPreflightDecision:
    """Plan an explicit strict remote-only ChatGPT message."""

    return plan_chatgpt_host_preflight(
        executor_observations,
        attachment_reports=attachment_reports,
        package_required=package_required,
        discovery_evidence=discovery_evidence,
        ingress_mode=ChatGptIngressMode.REMOTE_ONLY,
    )
