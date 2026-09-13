from __future__ import annotations

from latka_jazn.bootstrap.chatgpt_host_preflight_types import HostPackageMaterializationState
from latka_jazn.packaging.attachment_materialization import (
    AttachmentMaterializationReport,
    AttachmentMaterializationState,
)


def aggregate_attachment_state(
    reports: tuple[AttachmentMaterializationReport, ...],
) -> HostPackageMaterializationState:
    if not reports:
        return HostPackageMaterializationState.UNKNOWN
    states = {report.state for report in reports}
    if states == {AttachmentMaterializationState.READY}:
        return HostPackageMaterializationState.READY
    if AttachmentMaterializationState.MATERIALIZING in states:
        return HostPackageMaterializationState.MATERIALIZING
    if states & {
        AttachmentMaterializationState.MISSING,
        AttachmentMaterializationState.INCOMPLETE,
    }:
        return HostPackageMaterializationState.INCOMPLETE
    if states & {
        AttachmentMaterializationState.SIZE_MISMATCH,
        AttachmentMaterializationState.HASH_MISMATCH,
    }:
        return HostPackageMaterializationState.INVALID
    return HostPackageMaterializationState.UNKNOWN
