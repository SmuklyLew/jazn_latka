from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import pytest

from tools import jazn_pack_generator as generator
from tools.jazn_pack_generator_app.errors import PackIntegrityError, PackValidationError


def _system_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        'PACKAGE_VERSION = "16.3.25.5.26"\n'
        'PACKAGE_RELEASE_NAME = "package-generator-v10.1.86.0.112-byte-exact-eol-staging"\n',
        encoding="utf-8",
        newline="\n",
    )
    (root / ".gitattributes").write_text(
        "* text=auto eol=lf\n"
        ".gitattributes text eol=lf\n"
        "*.py text eol=lf\n"
        "*.txt text eol=lf\n"
        "*.ps1 text eol=crlf\n"
        "*.zip binary\n"
        ".archives/** -text -diff\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8", newline="\n")
    return root


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v101860112_system_fails_closed_on_crlf_drift_for_lf_policy(tmp_path: Path) -> None:
    root = _system_root(tmp_path)
    (root / "drift.py").write_bytes(b"print('drift')\r\n")

    with pytest.raises(PackIntegrityError, match="EOL drift.*drift.py.*wymaga LF"):
        generator.run_pack_request(
            source=root,
            out_dir=tmp_path / "out",
            content="system",
        )


def test_v101860112_windows_crlf_is_allowed_but_lf_is_rejected(tmp_path: Path) -> None:
    root = _system_root(tmp_path)
    script = root / "tool.ps1"
    script.write_bytes(b"Write-Host 'ok'\r\n")

    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "out-ok",
        content="system",
    )
    assert result["ok"] is True

    script.write_bytes(b"Write-Host 'bad'\n")
    with pytest.raises(PackIntegrityError, match="EOL drift.*tool.ps1.*wymaga CRLF"):
        generator.run_pack_request(
            source=root,
            out_dir=tmp_path / "out-bad",
            content="system",
        )


def test_v101860112_manifest_v2_and_verify_are_byte_exact_per_member(tmp_path: Path) -> None:
    root = _system_root(tmp_path)
    source = root / "system.txt"
    source.write_text("Jaźń byte exact\n", encoding="utf-8", newline="\n")

    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "out",
        content="system",
    )
    archive = Path(result["logical_archive"])
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "jazn_pack_generator_package/v2"
    assert manifest["source"]["byte_exact"] is True
    assert manifest["source"]["staging_mode"] == "canonical-byte-copy"
    file_rows = {
        item["path"]: item
        for item in manifest["source"]["entries"]
        if item["kind"] == "file"
    }
    assert file_rows["system.txt"]["sha256"] == _sha(source)
    assert manifest["verification"]["byte_exact"] is True
    assert manifest["verification"]["member_sha256"] == "ok"
    assert manifest["verification"]["eol_policy"] == "ok"

    report = generator.verify_package(archive)
    assert report["ok"] is True
    assert report["manifest_schema"] == "jazn_pack_generator_package/v2"
    assert report["member_integrity"]["byte_exact"] is True
    assert report["member_integrity"]["member_sha256"] == "ok"


def test_v101860112_member_hash_detects_content_change_even_with_valid_zip_crc(tmp_path: Path) -> None:
    root = _system_root(tmp_path)
    (root / "system.txt").write_text("original\n", encoding="utf-8", newline="\n")
    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "out",
        content="system",
    )
    original = Path(result["logical_archive"])
    original_manifest = Path(result["manifest_path"])
    tampered = tmp_path / "tampered.zip"

    with zipfile.ZipFile(original, "r") as src, zipfile.ZipFile(
        tampered, "w", compression=zipfile.ZIP_DEFLATED
    ) as dst:
        for info in src.infolist():
            data = src.read(info.filename) if not info.is_dir() else b""
            if info.filename == "system.txt":
                data = b"tampered\n"
            dst.writestr(info, data)

    shutil.copyfile(original_manifest, tampered.with_name("tampered.zip.package.json"))
    with zipfile.ZipFile(tampered, "r") as handle:
        assert handle.testzip() is None

    with pytest.raises(PackIntegrityError, match="SHA-256 wpisu ZIP nie zgadza się.*system.txt"):
        generator.verify_package(tampered)


def test_v101860112_system_requires_gitattributes_but_memory_does_not(tmp_path: Path) -> None:
    root = _system_root(tmp_path)
    (root / ".gitattributes").unlink()

    with pytest.raises(PackValidationError, match=r"Brak \.gitattributes"):
        generator.run_pack_request(
            source=root,
            out_dir=tmp_path / "system-out",
            content="system",
        )

    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "raw.bin").write_bytes(b"\x00\r\n\xff")
    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "memory-out",
        content="memory",
        memory_root=memory,
    )
    assert result["ok"] is True


def test_v101860112_repository_eol_and_gitignore_contracts() -> None:
    root = Path(__file__).resolve().parents[1]
    attributes = (root / ".gitattributes").read_text(encoding="utf-8-sig")
    ignore_lines = {
        line.strip()
        for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "* text=auto eol=lf" in attributes
    assert "*.ps1    text eol=crlf" in attributes
    assert "*.psm1   text eol=crlf" in attributes
    assert "*.psd1   text eol=crlf" in attributes
    assert ".archives/** -text -diff" in attributes
    assert "*.ps1" not in ignore_lines
    assert "*.join.ps1" in ignore_lines


def test_v101860112_verify_keeps_legacy_unrelated_sidecars_crc_compatible(tmp_path: Path) -> None:
    archive = tmp_path / "legacy.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("legacy.txt", b"legacy\n")
    archive.with_name("legacy.zip.package.json").write_text(
        json.dumps(
            {
                "schema_version": "jazn_package_set/v2",
                "package_name": "legacy.zip",
                "profile": "system",
                "outputs": [],
            }
        ),
        encoding="utf-8",
    )

    report = generator.verify_package(archive)
    assert report["ok"] is True
    assert report["manifest_schema"] == "jazn_package_set/v2"
    assert report["member_integrity"]["member_sha256"] == "not_available"
    assert report["member_integrity"]["byte_exact"] is False


def test_v101860112_manifest_v2_requires_hash_for_every_file(tmp_path: Path) -> None:
    archive = tmp_path / "broken.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("a.txt", b"a\n")
    archive.with_name("broken.zip.package.json").write_text(
        json.dumps(
            {
                "schema_version": "jazn_pack_generator_package/v2",
                "source": {
                    "entries": [
                        {"path": "a.txt", "size_bytes": 2, "kind": "file"},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PackIntegrityError, match="SHA-256 dla wszystkich plików"):
        generator.verify_package(archive)
