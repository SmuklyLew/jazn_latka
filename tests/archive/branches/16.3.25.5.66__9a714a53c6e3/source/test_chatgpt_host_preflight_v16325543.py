from __future__ import annotations

import hashlib
from pathlib import Path

from latka_jazn.bootstrap.chatgpt_host_preflight import (
    HostPackageMaterializationState,
    plan_chatgpt_host_preflight,
)
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostEnvironmentState,
    HostExecutorObservation,
    HostFilesystemState,
)
from latka_jazn.packaging.attachment_materialization import probe_attachment_materialization


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _degraded_executor_observations() -> list[HostExecutorObservation]:
    return [
        HostExecutorObservation(
            process_created=False,
            error_class="ClientError",
            alternative_surface_available=True,
            surface="python_tool",
        ),
        HostExecutorObservation(
            process_created=True,
            command_completed=True,
            returncode=0,
            filesystem_probe_succeeded=True,
            surface="terminal",
        ),
    ]


def test_degraded_host_with_verified_package_can_resume_bootstrap(tmp_path: Path) -> None:
    payload = b"verified-package-part"
    part = tmp_path / "package.zip.001"
    part.write_bytes(payload)
    attachment = probe_attachment_materialization(
        part,
        expected_size_bytes=len(payload),
        expected_sha256=_sha(payload),
    )

    decision = plan_chatgpt_host_preflight(
        _degraded_executor_observations(),
        attachment_reports=[attachment],
        package_required=True,
    )

    assert decision.environment_state is HostEnvironmentState.DEGRADED
    assert decision.filesystem_state is HostFilesystemState.OBSERVED
    assert decision.package_state is HostPackageMaterializationState.READY
    assert decision.bootstrap_allowed is True
    assert decision.canonical_resume_entrypoint == "run.py"
    assert decision.reason_code == "host_degraded_package_ready"


def test_observed_filesystem_does_not_make_truncated_package_bootstrap_safe(tmp_path: Path) -> None:
    part = tmp_path / "package.zip.004"
    part.write_bytes(b"partial")
    attachment = probe_attachment_materialization(
        part,
        expected_size_bytes=419_430_400,
        expected_sha256="d33424dddfeeba821ce57f8c20f3dc126b4e77809a1e8732534f20039d7bacc2",
    )

    decision = plan_chatgpt_host_preflight(
        _degraded_executor_observations(),
        attachment_reports=[attachment],
        package_required=True,
    )

    assert decision.environment_state is HostEnvironmentState.DEGRADED
    assert decision.filesystem_state is HostFilesystemState.OBSERVED
    assert decision.package_state is HostPackageMaterializationState.INCOMPLETE
    assert decision.bootstrap_allowed is False
    assert decision.reason_code == "attachment_package_incomplete"
    assert decision.runtime_state == "unverified"


def test_missing_attachment_is_package_incomplete_not_filesystem_unavailable(tmp_path: Path) -> None:
    attachment = probe_attachment_materialization(
        tmp_path / "missing.zip.006",
        expected_size_bytes=8,
        expected_sha256=_sha(b"12345678"),
    )

    decision = plan_chatgpt_host_preflight(
        _degraded_executor_observations(),
        attachment_reports=[attachment],
        package_required=True,
    )

    assert decision.filesystem_state is HostFilesystemState.OBSERVED
    assert decision.package_state is HostPackageMaterializationState.INCOMPLETE
    assert decision.bootstrap_allowed is False


def test_required_package_without_attachment_evidence_stays_blocked() -> None:
    decision = plan_chatgpt_host_preflight(
        _degraded_executor_observations(),
        package_required=True,
    )

    assert decision.package_state is HostPackageMaterializationState.UNKNOWN
    assert decision.bootstrap_allowed is False
    assert decision.reason_code == "required_package_not_observed"


def test_no_required_package_allows_canonical_discovery_on_degraded_host() -> None:
    decision = plan_chatgpt_host_preflight(
        _degraded_executor_observations(),
        package_required=False,
    )

    assert decision.environment_state is HostEnvironmentState.DEGRADED
    assert decision.package_state is HostPackageMaterializationState.UNKNOWN
    assert decision.bootstrap_allowed is True
    assert decision.canonical_resume_entrypoint == "run.py"
