from __future__ import annotations

import json
from pathlib import Path
import zipfile

from latka_jazn.tools.package_integrity import (
    MANIFEST_NAME,
    build_package_integrity_manifest,
    serialize_package_integrity_manifest,
    verify_package_integrity_manifest_in_zips,
)


def _runtime_fixture(root: Path) -> Path:
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        "DISTRIBUTION_VERSION = '15.0.3.4'\n"
        "PACKAGE_VERSION = 'v15.0.3.4'\n"
        "PACKAGE_RELEASE_NAME = ''\n",
        encoding="utf-8",
    )
    (root / "SOURCE_PROVENANCE.json").write_text("{}\n", encoding="utf-8")
    (root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (root / "main.py").write_text("print('main')\n", encoding="utf-8")
    (root / "payload.txt").write_text("current payload\n", encoding="utf-8")
    return root


def _build_zip(root: Path, output: Path, *, extra: dict[str, bytes] | None = None) -> Path:
    relative_paths = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    ]
    manifest = build_package_integrity_manifest(root, relative_paths=relative_paths)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in relative_paths:
            if relative == MANIFEST_NAME:
                continue
            archive.write(root / relative, relative)
        archive.writestr(MANIFEST_NAME, serialize_package_integrity_manifest(manifest))
        for relative, content in (extra or {}).items():
            archive.writestr(relative, content)
    return output


def test_plan_scoped_manifest_uses_current_version_and_excludes_generator_state(tmp_path: Path) -> None:
    root = _runtime_fixture(tmp_path / "runtime")
    transient = root / "tools" / "__jazn_pack_generator.lock.json"
    transient.parent.mkdir(parents=True)
    transient.write_text("{}\n", encoding="utf-8")
    backup = root / "tools" / "_jazn_pack_generator.before.py"
    backup.write_text("old\n", encoding="utf-8")

    relative_paths = [path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()]
    payload = build_package_integrity_manifest(root, relative_paths=relative_paths)

    assert payload["runtime_version"] == "v15.0.3.4"
    listed = {entry["path"] for entry in payload["files"]}
    assert MANIFEST_NAME not in listed
    assert "tools/__jazn_pack_generator.lock.json" not in listed
    assert "tools/_jazn_pack_generator.before.py" not in listed
    assert {"SOURCE_PROVENANCE.json", "run.py", "main.py", "latka_jazn/version.py", "payload.txt"} <= listed


def test_zip_verification_accepts_exact_current_manifest(tmp_path: Path) -> None:
    root = _runtime_fixture(tmp_path / "runtime")
    output = _build_zip(root, tmp_path / "system.zip")

    result = verify_package_integrity_manifest_in_zips(output)

    assert result["ok"] is True
    assert result["manifest_runtime_version"] == "v15.0.3.4"
    assert result["archive_runtime_version"] == "v15.0.3.4"
    assert result["checked_file_count"] == 5


def test_zip_verification_rejects_stale_manifest_and_unexpected_member(tmp_path: Path) -> None:
    root = _runtime_fixture(tmp_path / "runtime")
    relative_paths = [path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()]
    payload = build_package_integrity_manifest(root, relative_paths=relative_paths)
    payload["runtime_version"] = "v15.0.3.2"
    payload["version"] = "v15.0.3.2"
    output = tmp_path / "bad.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in relative_paths:
            archive.write(root / relative, relative)
        archive.writestr(MANIFEST_NAME, serialize_package_integrity_manifest(payload))
        archive.writestr("untracked.txt", b"not in manifest\n")

    result = verify_package_integrity_manifest_in_zips(output)
    codes = {error["code"] for error in result["errors"]}

    assert result["ok"] is False
    assert "version_mismatch" in codes
    assert "unexpected_zip_member" in codes


def test_zip_verification_allows_only_explicit_memory_prefix(tmp_path: Path) -> None:
    root = _runtime_fixture(tmp_path / "runtime")
    output = _build_zip(
        root,
        tmp_path / "full.zip",
        extra={"memory/notes/continuity.txt": b"memory\n"},
    )

    strict = verify_package_integrity_manifest_in_zips(output)
    full_profile = verify_package_integrity_manifest_in_zips(
        output,
        allowed_unprotected_prefixes=("memory/",),
    )

    assert strict["ok"] is False
    assert full_profile["ok"] is True
