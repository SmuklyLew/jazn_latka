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
        'PACKAGE_VERSION = "16.3.25.5.34"\n'
        'PACKAGE_RELEASE_NAME = "package-runtime-plugin-convergence"\n',
        encoding="utf-8",
        newline="\n",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8", newline="\n")
    if attributes is not None:
        (root / ".gitattributes").write_bytes(attributes)
    return root


def test_v101860114_memory_crlf_drift_is_diagnostic_and_source_bytes_are_preserved(tmp_path: Path) -> None:
    root = _root(tmp_path)
    memory = tmp_path / "memory"
    memory.mkdir()
    source = memory / "drift.py"
    source_bytes = b"print('memory snapshot')\r\n"
    source.write_bytes(source_bytes)

    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "out",
        content="memory",
        memory_root=memory,
    )

    archive = Path(result["logical_archive"])
    with zipfile.ZipFile(archive, "r") as handle:
        assert handle.read("memory/drift.py") == source_bytes
        assert handle.testzip() is None

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    rows = {item["path"]: item for item in manifest["source"]["entries"] if item["kind"] == "file"}
    assert rows["memory/drift.py"]["sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert manifest["source"]["staging_mode"] == "source-folder-byte-copy"
    assert manifest["source"]["source_basis"] == "selected_folder"
    assert manifest["verification"]["byte_exact"] is True
    assert manifest["verification"]["member_sha256"] == "ok"
    assert manifest["verification"]["eol_policy"] == "diagnostic_only"
    assert manifest["verification"]["system_extract_reverify"] == "not_applicable"


def test_v101860114_memory_snapshot_does_not_require_gitattributes(tmp_path: Path) -> None:
    root = _root(tmp_path)
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "snapshot.txt").write_bytes(b"folder snapshot\r\n")
    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "out",
        content="memory",
        memory_root=memory,
    )
    assert result["ok"] is True


def test_v101860114_system_plan_excludes_archive_local_settings_and_secrets(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / ".archives").mkdir()
    (root / ".archives" / "historical.py").write_text("OLD = True\n", encoding="utf-8")
    (root / "memory_rebuild_settings.json").write_text("{}\n", encoding="utf-8")
    (root / ".env").write_text("TOKEN=private\n", encoding="utf-8")
    (root / "client_secret.json").write_text("{}\n", encoding="utf-8")
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
    assert ".env" not in names
    assert "client_secret.json" not in names
    assert not any(name.startswith(".archives/") for name in names)


def test_v101860114_memory_split_is_one_logical_zip_cut_into_binary_transport_parts(tmp_path: Path) -> None:
    root = _root(tmp_path)
    memory = tmp_path / "memory"
    memory.mkdir()
    payload = os.urandom(2 * 1024 * 1024 + 131)
    (memory / "payload.bin").write_bytes(payload)

    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "out",
        content="memory",
        memory_root=memory,
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
        assert handle.read("memory/payload.bin") == payload
        assert handle.testzip() is None


def test_v101860114_verify_rehashes_memory_members_from_zip(tmp_path: Path) -> None:
    root = _root(tmp_path)
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "snapshot.txt").write_bytes(b"actual memory bytes\r\n")
    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "out",
        content="memory",
        memory_root=memory,
    )

    report = generator.verify_package(Path(result["logical_archive"]))
    assert report["ok"] is True
    assert report["manifest_schema"] == "jazn_pack_generator_package/v2"
    assert report["member_integrity"]["member_sha256"] == "ok"
    assert report["member_integrity"]["byte_exact"] is True
