from __future__ import annotations

from typing import Iterable

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


def plan_chatgpt_host_preflight(
    executor_observations: Iterable[HostExecutorObservation],
    *,
    attachment_reports: Iterable[AttachmentMaterializationReport] = (),
    package_required: bool = False,
) -> ChatGptHostPreflightDecision:
    capability = aggregate_host_executor_observations(executor_observations)
    reports = tuple(attachment_reports)
    package_state = aggregate_attachment_state(reports)
    route = resolve_preflight_route(
        capability,
        package_state=package_state,
        package_required=package_required,
    )
    return ChatGptHostPreflightDecision(
        schema_version=SCHEMA_VERSION,
        environment_state=capability.environment_state,
        filesystem_state=capability.filesystem_state,
        package_state=package_state,
        runtime_state="unverified",
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
