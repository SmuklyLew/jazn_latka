from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.bootstrap.chatgpt_recovery import runtime_preflight
from latka_jazn.core.package_integrity_manifest import package_integrity_manifest_status
from latka_jazn.core.runtime_activation_cascade import RuntimeActivationCascade
from latka_jazn.tools.active_extraction_cache import (
    build_active_runtime_status,
    write_active_runtime_marker,
)
from latka_jazn.tools.package_integrity import write_package_integrity_manifest
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


def _verified_runtime(root: Path) -> Path:
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        f"PACKAGE_VERSION = {PACKAGE_VERSION!r}\n"
        f"PACKAGE_RELEASE_NAME = {PACKAGE_RELEASE_NAME!r}\n"
        "PACKAGE_VERSION_FULL = f'{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}'\n",
        encoding="utf-8",
    )
    (root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (root / "main.py").write_text("print('main')\n", encoding="utf-8")
    (root / "SOURCE_PROVENANCE.json").write_text(
        json.dumps(
            {
                "repository": "local/test",
                "base_branch": "master",
                "base_version": f"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}",
                "base_merge_commit": "a" * 40,
                "runtime_version": f"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}",
                "git_tree_sha": "b" * 40,
                "dirty": False,
                "generation_mode": "release",
            }
        ),
        encoding="utf-8",
    )
    write_package_integrity_manifest(root)
    return root


def test_runtime_preflight_rejects_file_hash_mismatch_in_package_manifest(tmp_path: Path) -> None:
    root = _verified_runtime(tmp_path / "runtime")
    (root / "main.py").write_text("print('tampered')\n", encoding="utf-8")

    report = runtime_preflight(root)

    assert report.manifest_ok is False
    assert any(error.startswith("package_integrity_verification_failed:") for error in report.errors)


def test_active_marker_status_cannot_trust_hash_mismatched_runtime(tmp_path: Path) -> None:
    root = _verified_runtime(tmp_path / "runtime")
    (root / "main.py").write_text("print('tampered')\n", encoding="utf-8")

    status = build_active_runtime_status(root)

    assert status["runtime_root_valid"] is False
    assert status["active_marker_valid"] is False
    assert status["package_integrity_verification"]["ok"] is False
    assert "package_integrity_verification_failed" in status["cache_miss_reasons"]


def test_written_marker_never_marks_hash_mismatched_tree_as_reusable(tmp_path: Path) -> None:
    root = _verified_runtime(tmp_path / "runtime")
    (root / "main.py").write_text("print('tampered')\n", encoding="utf-8")

    marker = write_active_runtime_marker(root)

    assert marker["runtime_root_valid"] is False
    assert marker["marker_trusted"] is False
    assert marker["should_reuse_existing_extraction"] is False


def test_runtime_preflight_rejects_unmanifested_static_code(tmp_path: Path) -> None:
    root = _verified_runtime(tmp_path / "runtime")
    (root / "latka_jazn" / "unmanifested.py").write_text(
        "raise RuntimeError('must never be loaded')\n",
        encoding="utf-8",
    )

    report = runtime_preflight(root)

    assert report.manifest_ok is False
    assert report.manifest_verification is not None
    assert {item["code"] for item in report.manifest_verification["errors"]} >= {
        "unexpected_static_file"
    }


def test_runtime_preflight_rejects_semantically_invalid_source_provenance(tmp_path: Path) -> None:
    root = _verified_runtime(tmp_path / "runtime")
    (root / "SOURCE_PROVENANCE.json").write_text("{}\n", encoding="utf-8")
    write_package_integrity_manifest(root)

    report = runtime_preflight(root)

    assert report.manifest_ok is True
    assert report.provenance_ok is False
    assert "source_provenance_not_verified:invalid" in report.errors


def test_activation_and_active_cache_reject_self_consistent_but_invalid_provenance(
    tmp_path: Path,
) -> None:
    root = _verified_runtime(tmp_path / "runtime")
    (root / "SOURCE_PROVENANCE.json").write_text("{}\n", encoding="utf-8")
    write_package_integrity_manifest(root)
    manifest_status = package_integrity_manifest_status(root)

    cache = build_active_runtime_status(root)
    activation = RuntimeActivationCascade(root).evaluate(
        marker_status={
            "active_root": str(root),
            "version": f"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}",
            "package_integrity_manifest_sha256": manifest_status.sha256,
        },
        daemon_status={
            "pid": 123,
            "endpoint_reachable": True,
            "heartbeat_fresh": True,
        },
        time_status={"trusted": True},
        voice_status={"voice_allowed": True},
    )

    assert cache["runtime_root_valid"] is False
    assert cache["source_provenance_verified"] is False
    assert cache["should_reuse_existing_extraction"] is False
    assert activation.ok is False
    assert activation.active_state == "inactive"
    assert activation.manifest["source_provenance_verified"] is False
    assert "source_provenance_not_verified" in activation.errors


def test_activation_cascade_blocks_hash_mismatched_runtime(tmp_path: Path) -> None:
    root = _verified_runtime(tmp_path / "runtime")
    (root / "main.py").write_text("print('tampered')\n", encoding="utf-8")

    status = RuntimeActivationCascade(root).evaluate(
        marker_status={"active_root": str(root)},
        daemon_status={
            "pid": 123,
            "endpoint_reachable": True,
            "heartbeat_fresh": True,
        },
        time_status={"trusted": True},
        voice_status={"voice_allowed": True},
    )

    assert status.ok is False
    assert status.active_state == "inactive"
    assert status.manifest["runtime_start_blocking"] is True
    assert status.manifest["verification"]["ok"] is False
    assert "package_integrity_not_verified" in status.errors


def test_activation_cascade_rejects_stale_marker_manifest_hash(tmp_path: Path) -> None:
    root = _verified_runtime(tmp_path / "runtime")
    manifest_status = package_integrity_manifest_status(root)

    status = RuntimeActivationCascade(root).evaluate(
        marker_status={
            "active_root": str(root),
            "version": f"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}",
            "package_integrity_manifest_sha256": "0" * 64,
        },
        daemon_status={
            "pid": 123,
            "endpoint_reachable": True,
            "heartbeat_fresh": True,
        },
        time_status={"trusted": True},
        voice_status={"voice_allowed": True},
    )

    assert manifest_status.sha256 is not None
    assert status.ok is False
    assert status.marker["trusted"] is False
    assert status.marker["package_integrity_manifest_sha256_matches"] is False
    assert "marker_not_trusted" in status.errors
