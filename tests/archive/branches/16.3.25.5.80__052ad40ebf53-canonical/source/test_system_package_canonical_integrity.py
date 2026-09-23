from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from latka_jazn.tools.package_export import export_package
from latka_jazn.tools.package_integrity import verify_package_integrity_manifest
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION, PACKAGE_VERSION_FULL


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    return bytes(completed.stdout)


def test_system_export_uses_canonical_manifest_bytes_and_exact_inventory(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "latka_jazn").mkdir(parents=True)
    (root / ".gitattributes").write_text("*.cmd text eol=crlf\n", encoding="utf-8")
    (root / "JAZN.cmd").write_bytes(b"echo canonical\n")
    (root / "run.py").write_text('print("run")\n', encoding="utf-8")
    (root / "main.py").write_text('print("main")\n', encoding="utf-8")
    (root / "SOURCE_PROVENANCE.json").write_text('{"ok": true}\n', encoding="utf-8")
    (root / "latka_jazn" / "version.py").write_text(
        f'PACKAGE_VERSION = "{PACKAGE_VERSION}"\n'
        f'PACKAGE_RELEASE_NAME = "{PACKAGE_RELEASE_NAME}"\n'
        'PACKAGE_VERSION_FULL = f"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}"\n',
        encoding="utf-8",
    )

    subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=30)
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Jaźń test")
    _git(root, "add", ".gitattributes", "JAZN.cmd", "run.py", "main.py", "SOURCE_PROVENANCE.json", "latka_jazn/version.py")
    _git(root, "commit", "-qm", "fixture")

    protected_paths = [
        ".gitattributes",
        "JAZN.cmd",
        "SOURCE_PROVENANCE.json",
        "latka_jazn/version.py",
        "main.py",
        "run.py",
    ]
    entries: list[dict[str, object]] = []
    for relative in protected_paths:
        raw = _git(root, "show", f"HEAD:{relative}")
        entries.append({
            "path": relative,
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "mutable_runtime": False,
            "classification": "static_project_file",
            "archive": False,
            "hash_policy": "sha256_file_bytes",
        })
    manifest = {
        "schema_version": "package_integrity_manifest/v2",
        "version": PACKAGE_VERSION_FULL,
        "runtime_version": PACKAGE_VERSION_FULL,
        "package_version": PACKAGE_VERSION_FULL,
        "release_version": PACKAGE_VERSION_FULL,
        "file_count": len(entries),
        "static_file_count": len(entries),
        "files": entries,
        "truth_boundary": "fixture canonical Git bytes",
    }
    (root / "PACKAGE_INTEGRITY_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Simulate a clean Windows checkout representation plus untracked builder residue.
    (root / "JAZN.cmd").write_bytes(b"echo canonical\r\n")
    egg_info = root / "latka_jazn.egg-info" / "PKG-INFO"
    egg_info.parent.mkdir()
    egg_info.write_text("generated build residue", encoding="utf-8")
    wheel = root / "latka_jazn" / "local_resources" / "python" / "wheelhouse" / "demo" / "demo.whl"
    wheel.parent.mkdir(parents=True)
    wheel.write_bytes(b"generated wheelhouse residue")

    dependency_set = b'{"schema_version":"jazn_dependency_set/v3","artifacts":[]}\n'
    output = tmp_path / "system.zip"
    report = export_package(
        root,
        "system",
        output,
        virtual_files={"JAZN_DEPENDENCY_SET.json": dependency_set},
    )
    assert report.crc_ok is True
    assert report.extract_smoke_ok is True

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        archive.extractall(extracted)
    assert "JAZN_DEPENDENCY_SET.json" in names
    assert not any(".egg-info/" in name for name in names)
    assert not any("latka_jazn/local_resources/python/wheelhouse/" in name for name in names)
    assert (extracted / "JAZN.cmd").read_bytes() == b"echo canonical\n"

    transported_manifest = json.loads(
        (extracted / "PACKAGE_INTEGRITY_MANIFEST.json").read_text(encoding="utf-8")
    )
    virtual_entry = next(
        entry for entry in transported_manifest["files"]
        if entry["path"] == "JAZN_DEPENDENCY_SET.json"
    )
    assert virtual_entry["size_bytes"] == len(dependency_set)
    assert virtual_entry["sha256"] == hashlib.sha256(dependency_set).hexdigest()
    assert virtual_entry["classification"] == "package_virtual_file"

    verification = verify_package_integrity_manifest(extracted)
    assert verification["verification_basis"] == "filesystem_bytes"
    assert verification["ok"] is True, verification["errors"]
