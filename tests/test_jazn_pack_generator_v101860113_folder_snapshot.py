from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import zipfile

from tools import jazn_pack_generator as generator


def _root(tmp_path: Path, *, attributes: bytes | None = None) -> Path:
    root = tmp_path / "root"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        'PACKAGE_VERSION = "16.3.25.5.27"\n'
        'PACKAGE_RELEASE_NAME = "package-generator-v10.1.86.0.113-folder-snapshot"\n',
        encoding="utf-8",
        newline="\n",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8", newline="\n")
    if attributes is not None:
        (root / ".gitattributes").write_bytes(attributes)
    return root


def test_v101860113_crlf_drift_is_diagnostic_and_source_bytes_are_preserved(tmp_path: Path) -> None:
    root = _root(
        tmp_path,
        attributes=b"* text=auto eol=lf\n*.py text eol=lf\n",
    )
    source = root / "drift.py"
    source_bytes = b"print('windows working tree')\r\n"
    source.write_bytes(source_bytes)

    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "out",
        content="system",
    )

    archive = Path(result["logical_archive"])
    with zipfile.ZipFile(archive, "r") as handle:
        assert handle.read("drift.py") == source_bytes
        assert handle.testzip() is None

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    rows = {
        item["path"]: item
        for item in manifest["source"]["entries"]
        if item["kind"] == "file"
    }
    assert rows["drift.py"]["sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert manifest["source"]["staging_mode"] == "source-folder-byte-copy"
    assert manifest["verification"]["byte_exact"] is True
    assert manifest["verification"]["member_sha256"] == "ok"
    assert manifest["verification"]["eol_policy"] == "diagnostic_only"
    assert manifest["verification"]["eol_warning_count"] >= 1
    assert "drift.py" in manifest["verification"]["eol_warning_sample"]


def test_v101860113_missing_or_unreadable_gitattributes_does_not_block_snapshot(tmp_path: Path) -> None:
    missing = _root(tmp_path / "missing")
    (missing / "system.txt").write_bytes(b"folder snapshot\r\n")
    result = generator.run_pack_request(
        source=missing,
        out_dir=tmp_path / "out-missing",
        content="system",
    )
    assert result["ok"] is True

    unreadable = _root(tmp_path / "invalid", attributes=b"\xff\xfe\x00\x00")
    (unreadable / "system.txt").write_bytes(b"still packageable\r\n")
    result = generator.run_pack_request(
        source=unreadable,
        out_dir=tmp_path / "out-invalid",
        content="system",
    )
    assert result["ok"] is True


def test_v101860113_system_excludes_archive_and_local_operator_settings(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / ".archives").mkdir()
    (root / ".archives" / "historical.py").write_text("OLD = True\n", encoding="utf-8")
    (root / "memory_rebuild_settings.json").write_text("{}\n", encoding="utf-8")
    (root / "system.txt").write_text("system\n", encoding="utf-8")

    plan = generator.plan_pack(
        generator.PackRequest(
            source_root=root,
            output_root=tmp_path / "out",
            content=generator.ContentMode.SYSTEM,
        )
    )
    names = {entry.archive_path for entry in plan.entries}
    assert "system.txt" in names
    assert "memory_rebuild_settings.json" not in names
    assert not any(name.startswith(".archives/") for name in names)


def test_v101860113_split_is_one_logical_zip_cut_into_binary_transport_parts(tmp_path: Path) -> None:
    root = _root(tmp_path)
    payload = os.urandom(2 * 1024 * 1024 + 131)
    (root / "payload.bin").write_bytes(payload)

    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "out",
        content="system",
        split=True,
        split_size_mib=1,
        compression_level=0,
        force_split=True,
    )

    parts = [Path(item) for item in result["parts"]]
    assert result["logical_archive"] is None
    assert len(parts) >= 2
    assert all(part.name.endswith(f".{index:03d}") for index, part in enumerate(parts, start=1))

    joined = generator.join_parts(parts[0], tmp_path / "joined.zip")
    assert hashlib.sha256(joined.read_bytes()).hexdigest() == result["logical_sha256"]
    with zipfile.ZipFile(joined, "r") as handle:
        assert handle.read("payload.bin") == payload
        assert handle.testzip() is None


def test_v101860113_verify_rehashes_members_from_zip(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / "system.txt").write_bytes(b"actual folder bytes\r\n")
    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "out",
        content="system",
    )

    report = generator.verify_package(Path(result["logical_archive"]))
    assert report["ok"] is True
    assert report["manifest_schema"] == "jazn_pack_generator_package/v2"
    assert report["member_integrity"]["member_sha256"] == "ok"
    assert report["member_integrity"]["byte_exact"] is True
