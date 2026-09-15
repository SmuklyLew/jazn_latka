from __future__ import annotations

"""Converge ChatGPT recovery onto SYSTEM-first / optional-MEMORY semantics.

Historical recovery correctly validated MEMORY fail-closed but also promoted
that validation into a core activation prerequisite.  The v16.3 contract keeps
validation fail-closed *for memory use* while allowing a verified SYSTEM to
start without it.  Explicit ``memory_mode=required`` remains blocking.
"""

from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("recovery_convergence")
_INSTALL_MARKER = "_optional_memory_recovery_convergence_installed"
_OPTIONAL_MEMORY_FAILURE_STATES = frozenset({
    "auto_memory_failed",
    "memory_verification_failed",
    "memory_recovery_not_ready",
    "memory_attached_not_ready",
    "memory_legacy_repack_failed",
})


def _daemon_active(status: dict[str, Any]) -> bool:
    return str(status.get("active_state") or status.get("runtime_active_state") or "") in {
        "active_trusted",
        "active_degraded",
    }


def _installation_evidence(module: ModuleType, root: Path, report: dict[str, Any]) -> bool:
    explicit = report.get("installation_ok")
    if isinstance(explicit, bool):
        return explicit
    after = report.get("preflight_after")
    if isinstance(after, dict):
        return bool(
            after.get("structure_ok")
            and after.get("manifest_ok")
            and after.get("provenance_ok")
        )
    try:
        probe = module.runtime_preflight(root)
    except Exception:
        return False
    return bool(probe.structure_ok and probe.manifest_ok and probe.provenance_ok)


def _ensure_core_activation(
    module: ModuleType,
    *,
    root: Path,
    report: dict[str, Any],
    start_runtime_daemon: bool,
    daemon_host: str,
    daemon_port: int,
    heartbeat_interval: float,
    startup_timeout: float,
) -> tuple[bool, bool]:
    """Ensure marker/daemon only after structural SYSTEM evidence exists."""

    installation_ok = _installation_evidence(module, root, report)
    if not installation_ok:
        return False, False

    try:
        report.setdefault(
            "marker",
            module.write_active_runtime_marker(
                root,
                action="chatgpt_recovery_optional_memory_convergence",
            ),
        )
    except Exception as exc:
        report["recovery_convergence_marker_error"] = f"{type(exc).__name__}:{exc}"
        return installation_ok, False

    cfg = JaznConfig(root=root)
    status = report.get("daemon_status")
    daemon_status = dict(status) if isinstance(status, dict) else {}
    if start_runtime_daemon and not _daemon_active(daemon_status):
        try:
            report["daemon_start_after_optional_memory_degradation"] = module.start_daemon(
                cfg,
                host=daemon_host,
                port=daemon_port,
                heartbeat_interval=heartbeat_interval,
                startup_timeout=startup_timeout,
            )
        except Exception as exc:
            report["daemon_start_after_optional_memory_degradation"] = {
                "ok": False,
                "error": f"{type(exc).__name__}:{exc}",
            }
        try:
            daemon_status = module.status_daemon(
                cfg,
                host=daemon_host,
                port=daemon_port,
            )
        except Exception as exc:
            daemon_status = {
                "active_state": "inactive",
                "error": f"{type(exc).__name__}:{exc}",
            }
        report["daemon_status"] = daemon_status
    elif not start_runtime_daemon:
        report.setdefault("daemon_status", daemon_status)

    daemon_gate_ok = bool(not start_runtime_daemon or _daemon_active(daemon_status))
    return installation_ok, daemon_gate_ok


def converge_recovery_result(
    module: ModuleType,
    result: Any,
    *,
    destination: Path,
    start_runtime_daemon: bool,
    daemon_host: str,
    daemon_port: int,
    heartbeat_interval: float,
    startup_timeout: float,
) -> Any:
    if getattr(result, "pending", False):
        return result

    root = Path(getattr(result, "active_root", destination)).expanduser().resolve()
    report_value = getattr(result, "report", {})
    report: dict[str, Any] = report_value if isinstance(report_value, dict) else {}
    cfg = JaznConfig(root=root)
    memory = cfg.memory_availability
    report["memory_availability"] = memory.to_dict()
    report["persistent_memory_required_for_core_runtime"] = memory.persistent_memory_required
    report["transactional_memory_required_for_core_runtime"] = False

    state = str(getattr(result, "state", "") or "")
    profile = str(report.get("effective_profile") or "").strip().lower()
    optional_attach_failure = bool(
        state in _OPTIONAL_MEMORY_FAILURE_STATES
        and memory.mode in {"optional", "off"}
        and profile != "combined"
    )

    if optional_attach_failure:
        report["memory_degradation"] = {
            "blocking_core_runtime": False,
            "state": state,
            "reason": "optional_external_memory_attach_failed",
            "recall_allowed": False,
            "truth_boundary": (
                "The external MEMORY attempt failed validation/attachment. SYSTEM activation may continue, "
                "but no recall or persistence claim may use that MEMORY until it validates successfully."
            ),
        }

    installation_ok, daemon_gate_ok = _ensure_core_activation(
        module,
        root=root,
        report=report,
        start_runtime_daemon=start_runtime_daemon,
        daemon_host=daemon_host,
        daemon_port=daemon_port,
        heartbeat_interval=heartbeat_interval,
        startup_timeout=startup_timeout,
    )
    daemon_status = report.get("daemon_status")
    daemon_active = _daemon_active(daemon_status if isinstance(daemon_status, dict) else {})
    memory_policy_ok = memory.required_satisfied and memory.core_runtime_allowed
    core_activation_ok = bool(installation_ok and daemon_active and memory_policy_ok)
    core_install_ok = bool(installation_ok and daemon_gate_ok and memory_policy_ok)

    # Do not rescue unrelated package/profile/integrity failures. Only replace
    # the historical memory prerequisite, or the explicit optional attach
    # failure class handled above.
    result_was_structurally_usable = bool(
        getattr(result, "ok", False)
        or optional_attach_failure
        or state in {
            "reused_degraded",
            "reused_installed_inactive",
            "activated_degraded",
            "installed_inactive",
            "active",
            "reused",
        }
    )
    if not result_was_structurally_usable:
        return result

    report["installation_ok"] = installation_ok
    report["activation_ok"] = core_activation_ok
    report["core_runtime_activation_ok"] = core_activation_ok
    report["memory_capability_degraded"] = bool(
        not memory.persistent_memory_enabled or optional_attach_failure
    )
    report["recovery_convergence"] = {
        "schema_version": SCHEMA_VERSION,
        "optional_memory_contract_applied": True,
    }

    result.ok = core_install_ok
    result.exit_code = 0 if core_install_ok else getattr(result, "exit_code", 7)
    if start_runtime_daemon and core_activation_ok:
        if optional_attach_failure or not memory.persistent_memory_enabled:
            result.state = "active_memory_degraded"
        else:
            result.state = "active"
    elif not start_runtime_daemon and installation_ok and memory_policy_ok:
        result.state = "installed_inactive"
    elif memory.persistent_memory_required and not memory.required_satisfied:
        result.state = "required_memory_missing"
    result.truth_boundary = (
        "A verified SYSTEM can be installed and activated without private MEMORY in optional/off modes. "
        "MEMORY validation remains fail-closed for recall and persistence. Required mode makes the explicit "
        "memory policy an activation prerequisite; daemon/process evidence remains independently required."
    )
    return result


def install(module: ModuleType) -> None:
    if getattr(module, _INSTALL_MARKER, False):
        return
    original = getattr(module, "recover_chatgpt_runtime")
    if not callable(original):
        raise TypeError("recover_chatgpt_runtime_missing")

    @wraps(original)
    def converged(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        destination = Path(
            kwargs.get("destination")
            or getattr(module, "DEFAULT_CHATGPT_ROOT")
        )
        return converge_recovery_result(
            module,
            result,
            destination=destination,
            start_runtime_daemon=bool(kwargs.get("start_runtime_daemon", True)),
            daemon_host=str(kwargs.get("daemon_host", getattr(module, "DEFAULT_DAEMON_HOST"))),
            daemon_port=int(kwargs.get("daemon_port", getattr(module, "DEFAULT_DAEMON_PORT"))),
            heartbeat_interval=float(
                kwargs.get("heartbeat_interval", getattr(module, "DEFAULT_HEARTBEAT_INTERVAL_SECONDS"))
            ),
            startup_timeout=float(
                kwargs.get("startup_timeout", getattr(module, "DEFAULT_START_TIMEOUT_SECONDS"))
            ),
        )

    setattr(module, "recover_chatgpt_runtime", converged)
    setattr(module, _INSTALL_MARKER, True)
    setattr(module, "_recover_chatgpt_runtime_before_optional_memory_convergence", original)


__all__ = ["converge_recovery_result", "install"]
