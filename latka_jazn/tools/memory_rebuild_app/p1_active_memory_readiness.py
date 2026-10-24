"""P1 operator readiness: codes only, never activation or raw daemon evidence.

The verified configured database is not independent recall, continuity,
ancestry, or authority to switch a production MEMORY database.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from latka_jazn.core.active_memory_evidence import CHECKS, collect_active_memory_evidence
from .p1_provenance_chain import PinnedMemoryArtifact, verify_provenance_chain

SCHEMA = "jazn_active_memory_readiness_preflight/v1"
_REQUIRED = ("runtime_root", "version_integrity", "process", "endpoint", "heartbeat",
             "memory_root", "memory_schema", "database_identity")
_VALID_STATES = frozenset({"verified", "unverified", "conflict", "different", "blocked", "incompatible"})


def _issue_code(value: Any) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{2,90}", value) else "evidence_issue_unavailable"


def assess_active_memory_readiness(
    system_root: str | Path, *,
    pinned_reference: PinnedMemoryArtifact | None = None,
    pinned_parent: PinnedMemoryArtifact | None = None,
) -> dict[str, Any]:
    """Never start/restart daemon, write SQLite, or authorize MEMORY activation."""
    internal = collect_active_memory_evidence(Path(system_root))
    raw_checks = internal.get("checks")
    if not isinstance(raw_checks, dict):
        raw_checks = {}
    checks: dict[str, dict[str, str]] = {}
    for key in CHECKS:
        row = raw_checks.get(key)
        state = row.get("state") if isinstance(row, dict) else None
        if state not in _VALID_STATES:
            state = "unverified"
        checks[key] = {"state": state, "issue": _issue_code(row.get("issue") if isinstance(row, dict) else None)}

    runtime_ready = all(checks[key]["state"] == "verified" for key in _REQUIRED)
    provenance: dict[str, Any] = {"state": "unverified", "issue": (
        "runtime_not_ready_for_pinned_provenance" if pinned_reference is not None else "operator_pins_not_supplied"
    )}
    if pinned_reference is not None and runtime_ready:
        database = internal.get("observed_memory_path")
        if isinstance(database, str) and database:
            provenance = verify_provenance_chain(
                Path(database), reference=pinned_reference, parent=pinned_parent,
            )
    provenance_state = provenance.get("state", "unverified")
    checks["provenance"] = {"state": provenance_state if provenance_state in _VALID_STATES else "unverified",
                            "issue": _issue_code(provenance.get("issue"))}
    return {
        "schema": SCHEMA,
        "checks": checks,
        "runtime_ready": runtime_ready,
        "memory_schema_ready": checks["memory_schema"]["state"] == "verified",
        "memory_identity_verified": checks["database_identity"]["state"] == "verified",
        "memory_provenance_verified": provenance_state == "verified",
        "memory_recall_ready": None,
        "memory_continuity_ready": None,
        "activation_preflight_passed": False,
        "activation_authorized": False,
        "independent_recall_verified": False,
        "independent_continuity_verified": False,
        "truth_boundary": "Read-only configured database observation is not recall, continuity, or activation authority.",
    }


__all__ = ["SCHEMA", "assess_active_memory_readiness"]
