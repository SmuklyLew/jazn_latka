from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from latka_jazn.tools.package_integrity import (
    _git_crlf_normalized_file_identity,
    verify_package_integrity_manifest,
)
from latka_jazn.version import PACKAGE_VERSION


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
    )
    return bytes(completed.stdout)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".vscode").mkdir(parents=True)
    (root / "latka_jazn").mkdir()
    (root / "tools").mkdir()
    files = {
        ".gitattributes": (
            "*.json text eol=lf\n"
            "*.py text eol=lf\n"
            "*.ps1 text eol=crlf\n"
            "*.cmd text eol=crlf\n"
            "tools/StrictLF.ps1 text eol=lf\n"
        ),
        ".vscode/settings.json": '{"manager": "default"}\n',
        "JAZN.cmd": "@echo canonical\n",
        "setup.ps1": "Write-Output 'canonical'\n",
        "tools/StrictLF.ps1": "Write-Output 'strict LF'\n",
        "run.py": "print('run')\n",
        "main.py": "print('main')\n",
        "SOURCE_PROVENANCE.json": "{}\n",
        "latka_jazn/version.py": (
            f"PACKAGE_VERSION = {PACKAGE_VERSION!r}\n"
            "PACKAGE_RELEASE_NAME = ''\n"
        ),
    }
    for name, text in files.items():
        (root / name).write_bytes(text.encode("utf-8"))

    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Integrity Test")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "source")

    entries = []
    for name in sorted(files):
        canonical = _git(root, "show", f"HEAD:{name}")
        entries.append({
            "path": name,
            "size_bytes": len(canonical),
            "sha256": hashlib.sha256(canonical).hexdigest(),
        })
    manifest = {
        "runtime_version": PACKAGE_VERSION,
        "version": PACKAGE_VERSION,
        "file_count": len(entries),
        "files": entries,
    }
    (root / "PACKAGE_INTEGRITY_MANIFEST.json").write_text(
        json.dumps(manifest) + "\n", encoding="utf-8", newline="\n"
    )
    _git(root, "add", "PACKAGE_INTEGRITY_MANIFEST.json")
    _git(root, "commit", "-qm", "manifest")

    for name in ("JAZN.cmd", "setup.ps1", "tools/StrictLF.ps1"):
        path = root / name
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    return root


def _dirty_workspace(root: Path) -> None:
    (root / ".vscode" / "settings.json").write_text(
        '{"manager": "system"}\n', encoding="utf-8", newline="\n"
    )


def test_dirty_workspace_reports_real_change_not_legitimate_crlf(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _dirty_workspace(root)

    report = verify_package_integrity_manifest(root)

    assert report["ok"] is False
    assert report["verification_basis"] == "filesystem_bytes"
    assert report["worktree_state"] == "dirty"
    assert {item.get("path") for item in report["errors"]} == {".vscode/settings.json"}
    assert {item["code"] for item in report["errors"]} == {"sha256_mismatch", "size_mismatch"}


def test_dirty_workspace_rejects_changed_crlf_script_content(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _dirty_workspace(root)
    (root / "JAZN.cmd").write_bytes(b"@echo tampered\r\n")

    report = verify_package_integrity_manifest(root)

    assert report["ok"] is False
    assert any(
        item["path"] == "JAZN.cmd" and item["code"] == "sha256_mismatch"
        for item in report["errors"]
    )


def test_dirty_workspace_rejects_crlf_when_index_requires_lf(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _dirty_workspace(root)

    report = verify_package_integrity_manifest(root)

    assert report["ok"] is False
    assert any(
        item["path"] == "tools/StrictLF.ps1" and item["code"] == "sha256_mismatch"
        for item in report["errors"]
    )


def test_unpacked_package_remains_strict_on_raw_bytes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    exported = tmp_path / "exported"
    shutil.copytree(root, exported, ignore=shutil.ignore_patterns(".git"))

    report = verify_package_integrity_manifest(exported)

    assert report["ok"] is False
    assert report["verification_basis"] == "filesystem_bytes"
    assert report["worktree_state"] == "not_a_git_checkout"
    assert any(
        item["path"] == "JAZN.cmd" and item["code"] == "sha256_mismatch"
        for item in report["errors"]
    )


def test_crlf_at_streaming_chunk_boundary_is_normalized_once(tmp_path: Path) -> None:
    path = tmp_path / "boundary.cmd"
    canonical = b"a" * (1024 * 1024 - 1) + b"\nlast\n"
    path.write_bytes(canonical.replace(b"\n", b"\r\n"))

    assert _git_crlf_normalized_file_identity(path) == (
        len(canonical),
        hashlib.sha256(canonical).hexdigest(),
    )
