from __future__ import annotations

from pathlib import Path
import json
import subprocess

import pytest

from latka_jazn.tools.release_metadata_sync import (
    ReleaseMetadataSyncError,
    build_release_provenance_document,
)


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        'DISTRIBUTION_VERSION = "1.2.3.4"\n'
        'PACKAGE_VERSION = "v1.2.3.4"\n'
        'PACKAGE_RELEASE_NAME = "test"\n',
        encoding="utf-8",
    )
    (root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (root / "main.py").write_text("print('main')\n", encoding="utf-8")
    (root / "SOURCE_PROVENANCE.json").write_text("{}\n", encoding="utf-8")
    (root / "PACKAGE_INTEGRITY_MANIFEST.json").write_text("{}\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "remote", "add", "origin", "https://github.com/SmuklyLew/jazn_latka.git")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "source")
    _git(root, "branch", "-M", "master")
    return root


def test_metadata_only_dirty_is_allowed_only_for_read_only_generator_path(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "SOURCE_PROVENANCE.json").write_text(
        json.dumps({"generated": True}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ReleaseMetadataSyncError, match="clean working tree"):
        build_release_provenance_document(root)

    payload = build_release_provenance_document(
        root,
        allow_metadata_only_dirty=True,
    )
    assert payload["runtime_version"] == "v1.2.3.4-test"


def test_non_metadata_dirty_remains_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "main.py").write_text("print('changed')\n", encoding="utf-8")

    with pytest.raises(ReleaseMetadataSyncError, match="clean working tree"):
        build_release_provenance_document(root, allow_metadata_only_dirty=True)
