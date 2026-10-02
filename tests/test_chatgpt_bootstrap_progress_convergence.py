from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

import CHATGPT_BOOTSTRAP as bootstrap

from latka_jazn.bootstrap.chatgpt_bootstrap_progress import (
    build_chatgpt_bootstrap_progress,
)


_REQUIRED_MEMBERS = {
    "run.py": "print('ok')\n",
    "AGENTS.md": "# test\n",
    "latka_jazn/version.py": "PACKAGE_VERSION='test'\n",
    "PACKAGE_INTEGRITY_MANIFEST.json": "{}\n",
    "SOURCE_PROVENANCE.json": "{}\n",
}


def _package(tmp_path: Path) -> tuple[Path, Path]:
    package = tmp_path / "system.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in _REQUIRED_MEMBERS.items():
            zf.writestr(name, content)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    sidecar = tmp_path / "system.zip.sha256"
    sidecar.write_text(f"{digest}  system.zip\n", encoding="ascii")
    return package, sidecar


def test_progress_accepts_generator_without_consuming_it() -> None:
    progress = build_chatgpt_bootstrap_progress(
        phase="host_preflight",
        completed_gates=(gate for gate in ("executor_probe", "system_package_verified", "zip_validated")),
    )

    assert progress.core_wake_percent == 30
    assert progress.completed_gates == (
        "executor_probe",
        "system_package_verified",
        "zip_validated",
    )
    assert progress.next_gate == "operator_materialized"


def test_optional_memory_never_holds_ready_core_below_100() -> None:
    progress = build_chatgpt_bootstrap_progress(
        phase="turn_channel_bound",
        completed_gates=(
            "executor_probe",
            "system_package_verified",
            "zip_validated",
            "operator_materialized",
            "host_preflight",
            "contracts_loaded",
            "daemon_started",
            "live_readiness",
            "turn_channel_bound",
        ),
        memory_mode="optional",
        memory_state="not_attached",
    )

    assert progress.core_wake_percent == 100
    assert progress.configured_ready_percent == 100
    assert progress.memory_percent is None


def test_required_memory_is_separate_readiness_dimension() -> None:
    completed = (
        "executor_probe",
        "system_package_verified",
        "zip_validated",
        "operator_materialized",
        "host_preflight",
        "contracts_loaded",
        "daemon_started",
        "live_readiness",
        "turn_channel_bound",
    )
    without_memory = build_chatgpt_bootstrap_progress(
        phase="memory_required",
        completed_gates=completed,
        memory_mode="required",
        memory_state="not_attached",
        memory_percent=0,
    )
    with_memory = build_chatgpt_bootstrap_progress(
        phase="ready",
        completed_gates=completed,
        memory_mode="required",
        memory_state="ready",
        memory_percent=100,
    )

    assert without_memory.core_wake_percent == 100
    assert without_memory.configured_ready_percent == 85
    assert with_memory.configured_ready_percent == 100


def test_bootstrap_emits_evidence_backed_progress_events(tmp_path: Path) -> None:
    package, sidecar = _package(tmp_path)
    events: list[dict[str, object]] = []

    result = bootstrap.bootstrap_system_zip(
        zip_path=package,
        sha256_file_path=sidecar,
        destination=tmp_path / "runtime",
        progress_callback=events.append,
    )

    phases = [str(event["phase"]) for event in events]
    assert phases[0] == "executor_probe"
    assert "system_package_verified" in phases
    assert "zip_validated" in phases
    assert phases[-1] == "operator_materialized"
    assert int(events[-1]["wake_percent"]) == 55
    assert result["progress"] == events[-1]
    assert result["progress_contract"]["optional_memory_blocks_core_wake"] is False


def test_activation_contract_uses_live_status_as_readiness_authority(tmp_path: Path) -> None:
    activation = bootstrap.build_post_materialization_activation_contract(tmp_path / "active")
    local = activation["local"]
    assert isinstance(local, dict)

    assert local["runtime_status_argv"] == ["status", "--json"]
    assert local["runtime_snapshot_diagnostic_argv"] == ["status", "--snapshot", "--json"]
    assert local["activation_readiness_source"] == "live_status"
    assert local["snapshot_is_activation_authority"] is False
