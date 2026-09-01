from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RuntimeReadiness:
    """Unambiguous release, activation and live-runtime readiness state."""

    installation_ok: bool
    activation_prerequisites_ready: bool
    release_metadata_current: bool
    release_ready: bool
    live_runtime_ready: bool
    transactional_memory_ready: bool
    transactional_memory_exists: bool | None
    required_dependencies_ready: bool = True
    dependency_source: str = "legacy_unchecked"
    dependency_missing: tuple[str, ...] = ()

    @property
    def activation_ready(self) -> bool:
        """Backward-compatible alias for activation prerequisites readiness."""

        return self.activation_prerequisites_ready

    def summary(self) -> dict[str, str]:
        if self.transactional_memory_ready:
            memory_status = "ready"
        elif self.transactional_memory_exists is False:
            memory_status = "missing"
        else:
            memory_status = "not_ready"

        return {
            "installation": "ready" if self.installation_ok else "not_ready",
            "activation_prerequisites": (
                "ready" if self.activation_prerequisites_ready else "not_ready"
            ),
            "dependencies": "ready" if self.required_dependencies_ready else "not_ready",
            "release": "ready" if self.release_ready else "not_ready",
            "runtime": "active_trusted" if self.live_runtime_ready else "inactive",
            "transactional_memory": memory_status,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["activation_ready"] = self.activation_ready
        payload["summary"] = self.summary()
        return payload


@dataclass(frozen=True, slots=True)
class VoiceLiveReadiness:
    """Live Voice evidence projected from the canonical daemon status."""

    active_state_trusted: bool
    pid_alive: bool
    daemon_identity_verified: bool
    endpoint_probe_performed: bool
    endpoint_reachable: bool
    endpoint_pid_matches: bool
    endpoint_root_matches: bool
    endpoint_identity_matches: bool
    heartbeat_fresh: bool
    resolved_active_root_matches: bool
    integrity_ok: bool
    provenance_ok: bool
    blocking_reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blocking_reasons

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["voice_live_ready"] = self.ready
        payload["required_evidence_class"] = "required"
        payload["truth_boundary"] = (
            "Voice live readiness is a projection of canonical status_daemon evidence. "
            "A marker, PID, heartbeat, or endpoint response is insufficient on its own."
        )
        return payload


def _same_runtime_path(left: Any, right: Any) -> bool:
    if left in (None, "") or right in (None, ""):
        return False
    try:
        left_path = os.path.normcase(str(Path(str(left)).expanduser().resolve()))
        right_path = os.path.normcase(str(Path(str(right)).expanduser().resolve()))
    except (OSError, RuntimeError, ValueError):
        return False
    return left_path == right_path


def evaluate_voice_live_readiness(
    *,
    daemon: Mapping[str, Any],
    expected_active_root: Path | str,
) -> VoiceLiveReadiness:
    """Require the complete canonical daemon identity/readiness proof for Voice."""

    resolved_root = daemon.get("resolved_active_root") or daemon.get("subject_runtime_root")
    checks = {
        "active_state_not_active_trusted": (
            daemon.get("active_state") or daemon.get("runtime_active_state")
        )
        == "active_trusted",
        "pid_not_alive": daemon.get("pid_alive") is True,
        "daemon_identity_not_verified": daemon.get("process_identity_confirmed") is True,
        "endpoint_not_probed": daemon.get("endpoint_probe_performed") is True,
        "endpoint_unreachable": daemon.get("endpoint_reachable") is True,
        "endpoint_pid_mismatch": daemon.get("endpoint_pid_matches") is True,
        "endpoint_root_mismatch": daemon.get("endpoint_root_matches") is True,
        "endpoint_identity_mismatch": daemon.get("endpoint_identity_matches") is True,
        "heartbeat_stale_or_unknown": daemon.get("heartbeat_fresh") is True,
        "resolved_active_root_mismatch": _same_runtime_path(
            resolved_root,
            expected_active_root,
        ),
        "package_integrity_not_verified": daemon.get("package_integrity_verified") is True,
        "source_provenance_not_verified": daemon.get("source_provenance_verified") is True,
    }
    return VoiceLiveReadiness(
        active_state_trusted=checks["active_state_not_active_trusted"],
        pid_alive=checks["pid_not_alive"],
        daemon_identity_verified=checks["daemon_identity_not_verified"],
        endpoint_probe_performed=checks["endpoint_not_probed"],
        endpoint_reachable=checks["endpoint_unreachable"],
        endpoint_pid_matches=checks["endpoint_pid_mismatch"],
        endpoint_root_matches=checks["endpoint_root_mismatch"],
        endpoint_identity_matches=checks["endpoint_identity_mismatch"],
        heartbeat_fresh=checks["heartbeat_stale_or_unknown"],
        resolved_active_root_matches=checks["resolved_active_root_mismatch"],
        integrity_ok=checks["package_integrity_not_verified"],
        provenance_ok=checks["source_provenance_not_verified"],
        blocking_reasons=tuple(reason for reason, passed in checks.items() if not passed),
    )


CAPABILITY_READINESS_CLASSES = {
    "required",
    "optional",
    "degraded_allowed",
    "not_applicable",
    "unknown",
}


def evaluate_system_readiness_profile(
    *,
    profile: str,
    capabilities: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate an explicit capability profile without folding arbitrary booleans."""

    normalized: dict[str, dict[str, Any]] = {}
    blocking: list[str] = []
    optional_unavailable: list[str] = []
    degraded: list[str] = []
    unknown: list[str] = []
    for capability, raw in capabilities.items():
        classification = str(raw.get("classification") or "unknown")
        if classification not in CAPABILITY_READINESS_CLASSES:
            classification = "unknown"
        ready_value = raw.get("ready")
        ready = ready_value if isinstance(ready_value, bool) else None
        status = str(raw.get("status") or "unknown")
        blocks_system_ready = bool(
            classification == "unknown"
            or (classification == "required" and ready is not True)
        )
        if blocks_system_ready:
            blocking.append(capability)
        if classification == "optional" and ready is not True:
            optional_unavailable.append(capability)
        if classification == "degraded_allowed" and ready is not True:
            degraded.append(capability)
        if classification == "unknown":
            unknown.append(capability)
        normalized[capability] = {
            "classification": classification,
            "ready": ready,
            "status": status,
            "blocks_system_fully_ready": blocks_system_ready,
        }
    return {
        "profile": profile,
        "system_fully_ready": not blocking,
        "capabilities": normalized,
        "blocking_capabilities": blocking,
        "optional_unavailable": optional_unavailable,
        "degraded_capabilities": degraded,
        "unknown_capabilities": unknown,
        "truth_boundary": (
            "Only explicit required capabilities and unknown classifications block "
            "system_fully_ready. Optional, degraded_allowed, and not_applicable "
            "capabilities are reported without being coerced into required booleans."
        ),
    }


def _dependency_readiness(root: Path | str | None = None) -> dict[str, Any]:
    """Resolve core+archive Python readiness without importing optional providers."""

    try:
        from latka_jazn.dependencies.runtime import dependency_activation_status

        project_root = (
            Path(root).expanduser().resolve()
            if root is not None
            else Path(__file__).resolve().parents[2]
        )
        status = dependency_activation_status(project_root)
        if not isinstance(status, dict):
            raise TypeError("dependency_activation_status_not_mapping")
        return status
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "required_ready": False,
            "selected_source": "unavailable",
            "missing_or_incompatible_distributions": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def evaluate_runtime_readiness(
    *,
    required_checks: Mapping[str, Any],
    package_integrity_checks: Mapping[str, Any],
    provenance: Mapping[str, Any],
    daemon: Mapping[str, Any],
    transactional_memory: Mapping[str, Any],
    dependency_root: Path | str | None = None,
    dependency_evidence: Mapping[str, Any] | None = None,
) -> RuntimeReadiness:
    """Evaluate readiness from explicit evidence using one shared decision contract.

    Production callers normally omit ``dependency_evidence`` and the evaluator
    observes the active core+archive dependency environment itself. Deterministic
    callers may inject a previously observed dependency status. This keeps the
    decision function reproducible without weakening the production dependency
    gate or making historical readiness tests depend on the ambient test venv.
    """

    if dependency_evidence is None:
        dependency_status = _dependency_readiness(dependency_root)
    else:
        dependency_status = dict(dependency_evidence)
    required_dependencies_ready = dependency_status.get("required_ready") is True
    installation_ok = bool(
        all(bool(value) for value in required_checks.values())
        and required_dependencies_ready
    )
    activation_prerequisites_ready = bool(
        installation_ok
        and package_integrity_checks.get("present")
        and package_integrity_checks.get("parse_ok")
        and package_integrity_checks.get("version_matches")
        and package_integrity_checks.get("primary_present")
        and package_integrity_checks.get("legacy_alias_absent")
        and package_integrity_checks.get("canonical_source_name")
        and package_integrity_checks.get("verification_ok")
    )
    live_runtime_ready = bool(
        (daemon.get("active_state") or daemon.get("runtime_active_state"))
        == "active_trusted"
        and daemon.get("pid_alive")
        and daemon.get("endpoint_reachable")
        and daemon.get("heartbeat_fresh")
    )

    # A manifest-bound filesystem snapshot is sufficient for activation/runtime
    # trust, but it intentionally makes no Git/GitHub revision claims. Keep that
    # weaker provenance class out of release-readiness even though the transport
    # status remains backward-compatible with verified_export_without_git_history.
    release_metadata_current = bool(
        package_integrity_checks.get("verification_ok")
        and provenance.get("version_matches_runtime")
        and provenance.get("generation_mode") != "filesystem_snapshot"
        and provenance.get("status")
        in {"clean_checkout_verified", "verified_export_without_git_history"}
    )
    release_ready = bool(
        activation_prerequisites_ready and release_metadata_current
    )

    exists_value = transactional_memory.get("exists")
    transactional_memory_exists = exists_value if isinstance(exists_value, bool) else None

    return RuntimeReadiness(
        installation_ok=installation_ok,
        activation_prerequisites_ready=activation_prerequisites_ready,
        release_metadata_current=release_metadata_current,
        release_ready=release_ready,
        live_runtime_ready=live_runtime_ready,
        transactional_memory_ready=bool(transactional_memory.get("ready")),
        transactional_memory_exists=transactional_memory_exists,
        required_dependencies_ready=required_dependencies_ready,
        dependency_source=str(dependency_status.get("selected_source") or "unknown"),
        dependency_missing=tuple(
            str(item)
            for item in dependency_status.get("missing_or_incompatible_distributions") or []
        ),
    )
