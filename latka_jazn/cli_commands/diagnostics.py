from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from latka_jazn.bridge.secure_host_runtime_gateway import GatewayConfig, GatewayError
from latka_jazn.config import JaznConfig
from latka_jazn.core.bridge_discovery import discover_runtime_bridges
from latka_jazn.core.chatgpt_host_pending_store import host_request_store_status
from latka_jazn.core.package_integrity_manifest import package_integrity_manifest_status
from latka_jazn.core.readiness import evaluate_runtime_readiness
from latka_jazn.core.runtime_daemon import DEFAULT_DAEMON_HOST, DEFAULT_DAEMON_PORT, status_daemon
from latka_jazn.core.source_provenance import read_source_provenance
from latka_jazn.core.startup_contract import build_startup_status
from latka_jazn.core.tool_execution_controller import ToolExecutionController
from latka_jazn.memory.memory_tier_status import inspect_memory_tier_store
from latka_jazn.memory.runtime_memory_install import resolve_memory_tier_database_path
from latka_jazn.tools.package_integrity import verify_package_integrity_manifest
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version


DoctorProgressCallback = Callable[[int, int, str], None]


def _report_progress(
    callback: DoctorProgressCallback | None,
    completed: int,
    total: int,
    label: str,
) -> None:
    if callback is not None:
        callback(completed, total, label)


def _transactional_memory_status(cfg: JaznConfig) -> dict[str, Any]:
    try:
        path = resolve_memory_tier_database_path(
            cfg.root,
            configured=getattr(cfg, "memory_tier_db_path", None),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "path": None,
            "exists": False,
            "ready": False,
            "read_only": True,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "truth_boundary": (
                "Nie udało się rozwiązać kanonicznej ścieżki L1/L2/L3. "
                "Nie jest to dowód pustej ani uszkodzonej pamięci."
            ),
        }
    return inspect_memory_tier_store(path, full=False).to_dict()


def _daemon_runtime_write_ready(daemon: dict[str, Any]) -> tuple[bool, str]:
    """Read readiness from the live response without treating a missing top-level alias as false."""
    direct = daemon.get("runtime_write_ready")
    if isinstance(direct, bool):
        return direct, "daemon.runtime_write_ready"

    ping_value = daemon.get("ping")
    ping: dict[str, Any] = ping_value if isinstance(ping_value, dict) else {}
    nested = ping.get("runtime_write_ready")
    if isinstance(nested, bool):
        return nested, "daemon.ping.runtime_write_ready"

    for source, payload in (
        ("daemon.runtime_write_access_status.ok", daemon.get("runtime_write_access_status")),
        ("daemon.ping.runtime_write_access_status.ok", ping.get("runtime_write_access_status")),
    ):
        if isinstance(payload, dict) and isinstance(payload.get("ok"), bool):
            return bool(payload["ok"]), source
    return False, "unavailable"


def status_payload(
    root: Path,
    *,
    probe_endpoint: bool = True,
    daemon_host: str = DEFAULT_DAEMON_HOST,
    daemon_port: int = DEFAULT_DAEMON_PORT,
    marker_output: Path | None = None,
) -> dict[str, Any]:
    cfg = JaznConfig(root=root)
    startup = build_startup_status(cfg, mode="fast", infer_host_environment=True).to_dict()
    transactional_memory = _transactional_memory_status(cfg)
    daemon = status_daemon(
        cfg,
        host=daemon_host,
        port=daemon_port,
        marker_output=marker_output,
        probe_endpoint=probe_endpoint,
    )
    active_state = str(daemon.get("active_state") or daemon.get("runtime_active_state") or "inactive")
    process_ok = active_state in {"active_trusted", "active_degraded"}
    runtime_write_ready, runtime_write_ready_source = _daemon_runtime_write_ready(daemon)
    transactional_memory_ready = bool(transactional_memory.get("ready"))
    fully_ready = bool(process_ok and runtime_write_ready and transactional_memory_ready)
    conversation_memory = startup.get("conversation_archive_status") or {}
    continuity = startup.get("memory_continuity_status") or {}
    rest_status = daemon.get("rest_cycle_status") or {}
    try:
        from latka_jazn.memory.memory_sync_runtime import MemorySyncRuntime

        memory_sync = MemorySyncRuntime(cfg).status(probe_remote=False)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        memory_sync = {
            "schema_version": "jazn_memory_sync_runtime_status/v1",
            "configuration": {"enabled": False},
            "cloud_sync_ready": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "truth_boundary": "Cloud sync diagnostics are non-blocking for local runtime readiness.",
        }
    capability_readiness = {
        "runtime_ready": bool(process_ok and runtime_write_ready and transactional_memory_ready),
        "memory_search_ready": bool(conversation_memory.get("ready_for_search")),
        "continuity_ready": bool(continuity.get("continuity_claim_allowed")),
        "rest_scheduler_ready": bool(rest_status.get("rest_scheduler_ready") or rest_status.get("running")),
        "rest_dream_ready": bool(rest_status.get("rest_dream_ready")),
        "cognitive_integration_ready": None,
        "cognitive_integration_status": "requires_cognitive_architecture_audit_or_live_effect_probe",
        "truth_boundary": "Process readiness does not imply memory, continuity, dream generation, or cognitive integration readiness.",
    }
    if not process_ok:
        operational_state = "inactive_or_untrusted"
    elif fully_ready and active_state == "active_trusted":
        operational_state = "active_ready"
    elif not runtime_write_ready or not transactional_memory_ready:
        operational_state = "active_memory_degraded"
    else:
        operational_state = "active_process_degraded"
    return {
        "schema_version": schema_version("runpy_status"),
        "runtime_version": PACKAGE_VERSION_FULL,
        "root": str(root),
        "ok": process_ok,
        "process_ok": process_ok,
        "fully_ready": fully_ready,
        "operational_state": operational_state,
        "operational_reasons": [
            reason
            for reason, failed in (
                ("daemon_not_confirmed", not process_ok),
                ("runtime_write_not_ready", not runtime_write_ready),
                ("transactional_memory_not_ready", not transactional_memory_ready),
            )
            if failed
        ],
        "runtime_write_ready": runtime_write_ready,
        "runtime_write_ready_source": runtime_write_ready_source,
        "capability_readiness": capability_readiness,
        "endpoint_probe_requested": bool(probe_endpoint),
        "status_scope": "live_endpoint" if probe_endpoint else "offline_snapshot",
        "activation_truth_gate_eligible": bool(probe_endpoint),
        "status_exit_contract": (
            "zero_only_for_confirmed_active_process; fully_ready is reported separately; "
            "offline_snapshot is never sufficient to prove a live runtime"
        ),
        "startup": startup,
        "transactional_memory": transactional_memory,
        "memory_sync": memory_sync,
        "daemon": daemon,
    }


def _read_manifest(root: Path) -> tuple[dict[str, Any], str | None]:
    status = package_integrity_manifest_status(root)
    if not status.present or not status.path:
        return {}, "package_integrity_manifest_missing"
    path = Path(status.path)
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"
    if not isinstance(value, dict):
        return {}, "manifest_not_object"
    return value, None


def _live_evidence(
    *,
    marker: dict[str, Any],
    daemon: dict[str, Any],
    timestamp: dict[str, Any],
    transactional_memory: dict[str, Any],
) -> dict[str, Any]:
    runtime_write_ready, runtime_write_ready_source = _daemon_runtime_write_ready(daemon)
    return {
        "marker_found": bool(marker.get("existing_marker_found") or daemon.get("marker_found")),
        "marker_valid": bool(marker.get("active_marker_valid") or daemon.get("marker_valid")),
        "daemon_active_state": daemon.get("active_state") or daemon.get("runtime_active_state") or "inactive",
        "daemon_pid_alive": bool(daemon.get("pid_alive")),
        "endpoint_probe_performed": bool(daemon.get("endpoint_probe_performed")),
        "endpoint_reachable": bool(daemon.get("endpoint_reachable")),
        "heartbeat_fresh": bool(daemon.get("heartbeat_fresh")),
        "timestamp_status_available": bool(timestamp),
        "timestamp_trusted": timestamp.get("trusted"),
        "time_trust_state": timestamp.get("time_trust_state") or daemon.get("time_trust_state") or "unknown",
        "runtime_write_ready": runtime_write_ready,
        "runtime_write_ready_source": runtime_write_ready_source,
        "transactional_memory_ready": bool(transactional_memory.get("ready")),
    }


def doctor_payload(
    root: Path,
    *,
    daemon_host: str = DEFAULT_DAEMON_HOST,
    daemon_port: int = DEFAULT_DAEMON_PORT,
    marker_output: Path | None = None,
    progress: DoctorProgressCallback | None = None,
) -> dict[str, Any]:
    progress_total = 8
    _report_progress(progress, 0, progress_total, "Wczytywanie stanu runtime i pamięci")
    status = status_payload(
        root,
        daemon_host=daemon_host,
        daemon_port=daemon_port,
        marker_output=marker_output,
    )
    _report_progress(progress, 1, progress_total, "Wczytywanie stanu runtime i pamięci")
    startup = status.get("startup") or {}
    daemon = status.get("daemon") or {}
    transactional_memory = status.get("transactional_memory") or {}
    manifest, manifest_error = _read_manifest(root)
    marker = startup.get("active_cache_status") or {}
    model = startup.get("model_adapter_status") or {}
    conversation_memory = startup.get("conversation_archive_status") or {}
    runtime_memory = startup.get("runtime_write_access_status") or {}
    daemon_marker = daemon.get("marker") or {}
    timestamp = daemon.get("timestamp_contract") or daemon_marker.get("timestamp_contract") or {}
    package_integrity = package_integrity_manifest_status(root)
    _report_progress(progress, 2, progress_total, "Manifest i kontrakty podstawowe wczytane")

    controller = ToolExecutionController()
    read_plan = controller.plan(
        tool_name="doctor_probe",
        action="read_status",
        source_kind="generated_report",
        source_content="doctor self-test",
        source_origin="run.py doctor",
        actor="operator_cli",
        reason="read_only_gate_self_test",
        write_action=False,
    )
    denied_write_plan = controller.plan(
        tool_name="doctor_probe",
        action="write_status",
        source_kind="generated_report",
        source_content="doctor self-test",
        source_origin="run.py doctor",
        actor="operator_cli",
        reason="unconfirmed_write_gate_self_test",
        write_action=True,
        user_confirmed=False,
    )
    try:
        GatewayConfig(runtime_root=root).validate()
        mcp_policy_error = None
    except GatewayError as exc:  # pragma: no cover - defensive serialization path
        mcp_policy_error = f"{type(exc).__name__}: {exc}"
    _report_progress(progress, 3, progress_total, "Bramki narzędzi i polityka MCP sprawdzone")

    required_checks = {
        "root_exists": root.is_dir(),
        "main_exists": (root / "main.py").is_file(),
        "run_exists": (root / "run.py").is_file(),
        "version_py_exists": (root / "latka_jazn/version.py").is_file(),
        "package_exists": (root / "latka_jazn").is_dir(),
        "startup_status_available": bool(startup),
        "daemon_status_available": bool(daemon),
        "model_status_available": bool(model),
        "memory_status_available": bool(conversation_memory or runtime_memory or transactional_memory),
        "transactional_memory_status_available": bool(transactional_memory) or "transactional_memory" not in status,
        "tool_read_allowed": read_plan.allowed,
        "tool_unconfirmed_write_denied": not denied_write_plan.allowed,
        "mcp_loopback_policy_valid": mcp_policy_error is None,
        "privacy_gate_available": (root / "latka_jazn/core/private_data_export_gate.py").is_file(),
        "finalization_gate_available": (root / "latka_jazn/core/host_visible_finalization.py").is_file(),
    }
    _report_progress(progress, 4, progress_total, "Pliki i wymagane podsystemy sprawdzone")
    manifest_verification = verify_package_integrity_manifest(root)
    _report_progress(progress, 5, progress_total, "Integralność paczki zweryfikowana")
    provenance = read_source_provenance(root, profile="system_smoke").to_dict()
    package_integrity_checks = {
        "present": package_integrity.present,
        "parse_ok": manifest_error is None,
        "version_matches": str(manifest.get("runtime_version") or manifest.get("version") or "").lstrip("v")
        == PACKAGE_VERSION_FULL.lstrip("v"),
        "primary_present": package_integrity.primary_present,
        "legacy_alias_absent": not package_integrity.legacy_present,
        "canonical_source_name": package_integrity.source_name == "PACKAGE_INTEGRITY_MANIFEST.json",
        "verification_ok": bool(manifest_verification.get("ok")),
        "verification_errors": list(manifest_verification.get("errors") or []),
        "runtime_start_blocking": True,
    }
    readiness = evaluate_runtime_readiness(
        required_checks=required_checks,
        package_integrity_checks=package_integrity_checks,
        provenance=provenance,
        daemon=daemon,
        transactional_memory=transactional_memory,
    )
    _report_progress(progress, 6, progress_total, "Gotowość aktywacji i wydania obliczona")

    live_evidence = _live_evidence(
        marker=marker,
        daemon=daemon,
        timestamp=timestamp,
        transactional_memory=transactional_memory,
    )
    subsystem_status = {
        "package_integrity_manifest": {
            **package_integrity.to_dict(),
            "ok": bool(manifest_verification.get("ok")),
            "error": manifest_error,
            "version": manifest.get("version") or manifest.get("runtime_version"),
            "start_file": manifest.get("start_file"),
            "verification": manifest_verification,
            "runtime_start_blocking": True,
        },
        "source_provenance": provenance,
        "model": {
            "available": bool(model),
            "adapter_id": model.get("adapter_id") or model.get("selected_adapter"),
            "status": model.get("status"),
            "requires_api_key": model.get("requires_api_key"),
        },
        "memory": {
            "conversation_archive": conversation_memory,
            "runtime_write_legacy": runtime_memory,
            "transactional_tier": transactional_memory,
            "truth_boundary": (
                "Legacy runtime_write i transactional_tier są raportowane osobno. "
                "Gotowa baza L1/L2/L3 nie dowodzi poprawnego recall ani uruchomionej Jaźni."
            ),
        },
        "tool_gates": {
            "read_plan": read_plan.to_dict(),
            "unconfirmed_write_plan": denied_write_plan.to_dict(),
        },
        "mcp": {
            "server_file_exists": (root / "latka_jazn/mcp/server.py").is_file(),
            "loopback_policy_valid": mcp_policy_error is None,
            "policy_error": mcp_policy_error,
            "public_ingress_default": False,
            "transport": "authenticated local stdio/loopback; optional outbound tunnel",
            "host_request_store": host_request_store_status(root),
        },
        "privacy": {
            "gate_file_exists": (root / "latka_jazn/core/private_data_export_gate.py").is_file(),
            "private_profiles_require_second_confirmation": ["memory", "full"],
        },
        "time": timestamp,
    }
    _report_progress(progress, 7, progress_total, "Gotowość aktywacji i wydania obliczona")
    payload = {
        "schema_version": schema_version("runpy_doctor"),
        "ok": readiness.installation_ok,
        "installation_ok": readiness.installation_ok,
        "activation_ready": readiness.activation_ready,
        "activation_prerequisites_ready": readiness.activation_prerequisites_ready,
        "release_metadata_current": readiness.release_metadata_current,
        "release_ready": readiness.release_ready,
        "live_runtime_ready": readiness.live_runtime_ready,
        "readiness": readiness.to_dict(),
        "readiness_summary": readiness.summary(),
        "checks": required_checks,
        "package_integrity_checks": package_integrity_checks,
        "live_evidence": live_evidence,
        "subsystems": subsystem_status,
        "status": status,
        "read_only": True,
        "truth_boundary": (
            "Doctor reports structural installation health separately from activation prerequisites, release metadata, "
            "live runtime readiness and transactional_memory readiness. The legacy activation_ready field is retained as an alias "
            "for activation_prerequisites_ready; it does not mean that a daemon is running."
        ),
    }
    _report_progress(progress, 8, progress_total, "Gotowość aktywacji i wydania obliczona")
    return payload


def bridge_payload(root: Path) -> dict[str, Any]:
    payload = discover_runtime_bridges(JaznConfig(root=root))
    payload["v15_secure_mcp"] = {
        "server": "python -X utf8 -m latka_jazn.mcp.server",
        "transport": "authenticated stdio/local + optional outbound Secure MCP Tunnel",
        "public_ingress_default": False,
        "auth_required": True,
        "two_phase_continuation": True,
    }
    payload["finalization_gate"] = "latka_jazn.core.host_visible_finalization.HostVisibleFinalizationGate"
    payload["audit"] = "memory/sqlite/runtime_write_v1/runtime_audit.sqlite3"
    payload["fallback"] = "copy-paste helper using the same finalization gate"
    return payload
