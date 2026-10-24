"""Synthetic immutable-file inventory checks; never run or unquarantine an EXE."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools.jazn_run_studio.p5_artifact_evidence import (
    inspect_frozen_artifact, write_frozen_bundle_manifest, verify_frozen_bundle_manifest,
)

COMMIT = "c" * 40


def _bundle(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "JaznRunStudio"
    root.mkdir()
    (root / "_internal").mkdir()
    exe = root / "JaznRunStudio.exe"
    exe.write_bytes(b"synthetic exe fixture")
    (root / "_internal" / "lib.dll").write_bytes(b"synthetic dependency")
    info = root / "BUILD_INFO.json"
    info.write_text(json.dumps({"source_commit": COMMIT, "layout": "onedir"}))
    return exe, info


def _inspect(exe: Path, info: Path) -> dict:
    return inspect_frozen_artifact(
        exe, info, expected_sha256=sha256(exe.read_bytes()).hexdigest(),
        expected_source_commit=COMMIT,
    )


def test_full_onedir_inventory_matches_and_does_not_promote_security(tmp_path: Path) -> None:
    exe, info = _bundle(tmp_path)
    write_frozen_bundle_manifest(exe.parent)
    outcome = _inspect(exe, info)
    assert outcome["current_integrity_match"]
    assert outcome["whole_bundle_integrity_match"]
    assert outcome["bundle_file_count"] == 3
    assert outcome["security_review"] == "HOLD"
    assert outcome["offline_acceptance"] == "NOT_RUN"
    assert str(tmp_path) not in json.dumps(outcome)


def test_modified_dependency_or_missing_dependency_invalidates_full_bundle(tmp_path: Path) -> None:
    exe, info = _bundle(tmp_path)
    write_frozen_bundle_manifest(exe.parent)
    dep = exe.parent / "_internal" / "lib.dll"
    dep.write_bytes(b"tampered library")
    assert not _inspect(exe, info)["whole_bundle_integrity_match"]
    dep.unlink()
    assert not _inspect(exe, info)["whole_bundle_integrity_match"]


def test_untracked_additions_and_missing_manifest_fail_closed(tmp_path: Path) -> None:
    exe, info = _bundle(tmp_path)
    assert not _inspect(exe, info)["whole_bundle_integrity_match"]
    write_frozen_bundle_manifest(exe.parent)
    (exe.parent / "unexpected.dll").write_bytes(b"extra")
    assert not _inspect(exe, info)["whole_bundle_integrity_match"]


def test_bundle_links_are_not_accepted(tmp_path: Path) -> None:
    exe, _info = _bundle(tmp_path)
    try:
        (exe.parent / "_internal" / "alias.dll").symlink_to(exe.parent / "_internal" / "lib.dll")
    except (OSError, NotImplementedError):
        pytest.skip("symlink capability unavailable")
    with pytest.raises(ValueError, match="bundle_link_forbidden"):
        write_frozen_bundle_manifest(exe.parent)
    assert verify_frozen_bundle_manifest(exe.parent) == (False, 0)
