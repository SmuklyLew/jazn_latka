from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import zipfile

import pytest

from latka_jazn.bootstrap import chatgpt_recovery as recovery_module
from latka_jazn.bootstrap.chatgpt_recovery import (
    _verify_memory_package_manifest,
    _zip_verification_cache_valid,
    recover_chatgpt_runtime,
)
from latka_jazn.tools.package_integrity import write_package_integrity_manifest
from latka_jazn.cli import build_parser, main as cli_main
from latka_jazn.packaging.split_zip_package import (
    extract_independent_zip_set_resumable,
    extract_joined_zip_resumable,
    infer_base_zip_name,
    load_package_expectations,
    load_package_set_metadata,
    resolve_renamed_package_parts,
    test_joined_zip as inspect_joined_zip,
    unsafe_zip_member_name,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_current_package_set(
    parts_dir: Path,
    *,
    profile: str = "system",
    schema_version: str = "jazn_package_set/v1",
) -> list[Path]:
    first = parts_dir / "jazn-current.zip"
    second = parts_dir / "jazn-current.part002.zip"
    with zipfile.ZipFile(first, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("run.py", "print('start')\n")
    with zipfile.ZipFile(second, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("latka_jazn/version.py", "PACKAGE_VERSION_FULL = 'v1'\n")
    outputs = []
    for number, path in enumerate((first, second), start=1):
        outputs.append(
            {
                "part_no": number,
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "is_complete_zip": True,
            }
        )
    (parts_dir / "jazn-current.zip.package.json").write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "package_name": "jazn-current.zip",
                "profile": profile,
                "archive_format": "independent",
                "package_version": "v1",
                "outputs": outputs,
            }
        ),
        encoding="utf-8",
    )
    return [first, second]


def _write_installable_source(source: Path) -> Path:
    (source / "latka_jazn").mkdir(parents=True)
    (source / "run.py").write_text("print('run')\n", encoding="utf-8")
    (source / "main.py").write_text("print('main')\n", encoding="utf-8")
    (source / "latka_jazn" / "version.py").write_text(
        "DISTRIBUTION_VERSION = '1'\nPACKAGE_VERSION = 'v1'\nPACKAGE_RELEASE_NAME = ''\n",
        encoding="utf-8",
    )
    (source / "SOURCE_PROVENANCE.json").write_text(
        json.dumps(
            {
                "repository": "local/test",
                "base_branch": "main",
                "base_version": "v1",
                "base_merge_commit": "a" * 40,
                "runtime_version": "v1",
                "git_tree_sha": "b" * 40,
                "dirty": False,
                "generation_mode": "release",
            }
        ),
        encoding="utf-8",
    )
    write_package_integrity_manifest(source)
    return source


def _write_installable_package(
    parts_dir: Path,
    source: Path,
    *,
    profile: str,
    package_version: str = "v1",
    schema_version: str = "jazn_package_set/v1",
) -> Path:
    parts_dir.mkdir(parents=True, exist_ok=True)
    archive_path = parts_dir / f"jazn-{profile}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    (parts_dir / f"{archive_path.name}.package.json").write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "package_name": archive_path.name,
                "profile": profile,
                "archive_format": "independent",
                "package_version": package_version,
                "outputs": [
                    {
                        "part_no": 1,
                        "filename": archive_path.name,
                        "size_bytes": archive_path.stat().st_size,
                        "sha256": _sha256(archive_path),
                        "is_complete_zip": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return archive_path


def test_current_package_sidecar_is_discovered_and_independent_volumes_extract(
    tmp_path: Path,
) -> None:
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    _write_current_package_set(parts_dir)

    base_name = infer_base_zip_name(parts_dir)
    metadata = load_package_set_metadata(parts_dir, base_name)
    expected, full_sha, source = load_package_expectations(parts_dir, base_name)
    canonical = tmp_path / "canonical"
    resolved = resolve_renamed_package_parts(parts_dir, expected, canonical_dir=canonical)
    destination = tmp_path / "active"
    extraction = extract_independent_zip_set_resumable(
        [canonical / item.filename for item in expected],
        destination,
        time_budget_seconds=None,
    )

    assert base_name == "jazn-current.zip"
    assert metadata["archive_format"] == "independent"
    assert metadata["profile"] == "system"
    assert source == "package.json"
    assert full_sha is None
    assert resolved["parts_count"] == 2
    assert extraction["ok"] is True
    assert (destination / "run.py").is_file()
    assert (destination / "latka_jazn" / "version.py").is_file()


def test_generator_v84_package_set_v2_is_accepted_by_runtime_loader(
    tmp_path: Path,
) -> None:
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    _write_current_package_set(parts_dir, schema_version="jazn_package_set/v2")

    metadata = load_package_set_metadata(parts_dir, "jazn-current.zip")
    expected, full_sha, source = load_package_expectations(parts_dir, "jazn-current.zip")

    assert metadata["schema_version"] == "jazn_package_set/v2"
    assert metadata["archive_format"] == "independent"
    assert source == "package.json"
    assert full_sha is None
    assert len(expected) == 2


def test_package_sidecar_rejects_traversal_in_volume_filename(tmp_path: Path) -> None:
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    (parts_dir / "jazn-current.zip.package.json").write_text(
        json.dumps(
            {
                "package_name": "jazn-current.zip",
                "profile": "system",
                "archive_format": "independent",
                "outputs": [
                    {
                        "part_no": 1,
                        "filename": "../outside.zip",
                        "size_bytes": 1,
                        "sha256": "0" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Niebezpieczna nazwa części"):
        load_package_expectations(parts_dir, "jazn-current.zip")


@pytest.mark.parametrize("kind", ["duplicate", "symlink"])
def test_runtime_loader_rejects_unsafe_zip_member_contracts(
    tmp_path: Path,
    kind: str,
) -> None:
    archive_path = tmp_path / f"unsafe-{kind}.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        if kind == "duplicate":
            archive.writestr("same.txt", "first")
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr("same.txt", "second")
        elif kind == "symlink":
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            archive.writestr(info, "target")

    with pytest.raises(ValueError, match="niebezpieczne ścieżki"):
        inspect_joined_zip(archive_path)


def test_runtime_loader_rejects_noncanonical_backslash_member_name() -> None:
    assert unsafe_zip_member_name("nested\\file.txt") == "backslash separator"


def test_joined_zip_cache_rehashes_bytes_instead_of_trusting_size_and_mtime(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "joined.zip"
    archive.write_bytes(b"trusted-bytes")
    original_stat = archive.stat()
    expected_sha = _sha256(archive)
    cache = {
        "ok": True,
        "size_bytes": original_stat.st_size,
        "mtime_ns": original_stat.st_mtime_ns,
        "sha256": expected_sha,
        "crc_tested": True,
    }
    assert _zip_verification_cache_valid(cache, archive, expected_sha, True) is True

    archive.write_bytes(b"tampered-byte")
    assert archive.stat().st_size == original_stat.st_size
    archive.touch()
    os.utime(archive, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert _zip_verification_cache_valid(cache, archive, expected_sha, True) is False


def test_resumable_extraction_rechecks_completed_file_crc_before_skip(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("state.bin", b"good")
    with zipfile.ZipFile(archive_path, "r") as archive:
        info = archive.getinfo("state.bin")
    destination = tmp_path / "staging"
    destination.mkdir()
    target = destination / "state.bin"
    target.write_bytes(b"evil")
    progress = tmp_path / "progress.json"
    progress.write_text(
        json.dumps(
            {
                "completed": {
                    "state.bin": {"size_bytes": info.file_size, "crc32": info.CRC}
                }
            }
        ),
        encoding="utf-8",
    )

    result = extract_joined_zip_resumable(
        archive_path,
        destination,
        progress_path=progress,
        time_budget_seconds=None,
    )

    assert result["ok"] is True
    assert result["extracted_now"] == 1
    assert result["skipped_completed"] == 0
    assert target.read_bytes() == b"good"


def test_memory_profile_is_rejected_before_runtime_activation(tmp_path: Path) -> None:
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    _write_current_package_set(parts_dir, profile="memory")

    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=tmp_path / "active",
        start_runtime_daemon=False,
    )

    assert result.ok is False
    assert result.state == "memory_profile_rejected"
    assert result.exit_code == 8
    assert result.report["profile_gate"]["reason"] == "memory_profile_is_not_a_runtime_root"


def test_unverified_existing_destination_is_not_replaced_implicitly(tmp_path: Path) -> None:
    destination = tmp_path / "active"
    destination.mkdir()
    sentinel = destination / "do-not-overwrite.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    result = recover_chatgpt_runtime(
        parts_dir=tmp_path / "missing-parts",
        destination=destination,
        start_runtime_daemon=False,
    )
    forced = recover_chatgpt_runtime(
        parts_dir=tmp_path / "missing-parts",
        destination=destination,
        force_reextract=True,
        start_runtime_daemon=False,
    )

    assert result.ok is False
    assert result.state == "destination_replacement_blocked"
    assert forced.state == "destination_replacement_blocked"
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_runtime_bootstrap_is_a_canonical_cli_command() -> None:
    parsed = build_parser().parse_args(
        [
            "runtime-bootstrap",
            "--parts-dir",
            "parts",
            "--destination",
            "active-v1",
            "--no-start-daemon",
        ]
    )

    assert parsed.command == "runtime-bootstrap"
    assert parsed.parts_dir == Path("parts")
    assert parsed.destination == Path("active-v1")
    assert parsed.no_start_daemon is True


def test_current_system_package_materializes_end_to_end_without_claiming_activation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source"
    _write_installable_source(source)
    parts_dir = tmp_path / "parts"
    _write_installable_package(parts_dir, source, profile="system")
    monkeypatch.setattr(
        recovery_module,
        "status_daemon",
        lambda *_args, **_kwargs: {"ok": False, "active_state": "inactive"},
    )
    destination = tmp_path / "active-v1"

    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=destination,
        start_runtime_daemon=False,
        time_budget_seconds=None,
    )

    assert result.ok is True
    assert result.exit_code == 0
    assert result.state == "installed_inactive"
    assert result.report["installation_ok"] is True
    assert result.report["activation_ok"] is False
    assert result.report["sqlite"]["reason"] == "active_database_missing"
    assert (destination / "run.py").is_file()
    assert (destination / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json").is_file()


def test_combined_package_loads_verified_memory_but_no_start_stays_inactive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = _write_installable_source(tmp_path / "source")
    database = source / "memory" / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE memory_records (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        connection.execute("INSERT INTO memory_records(body) VALUES ('verified memory')")
    memory_manifest = source / "memory" / "MEMORY_PACKAGE_MANIFEST.json"
    memory_manifest.write_text(
        json.dumps(
            {
                "schema_version": "jazn_memory_package_manifest/v1",
                "runtime_version": "v1",
                "file_count": 1,
                "files": [
                    {
                        "path": "memory/sqlite/runtime_write_v1/runtime_memory.sqlite3",
                        "size_bytes": database.stat().st_size,
                        "sha256": _sha256(database),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    parts_dir = tmp_path / "parts"
    _write_installable_package(parts_dir, source, profile="combined")
    monkeypatch.setattr(
        recovery_module,
        "status_daemon",
        lambda *_args, **_kwargs: {"ok": False, "active_state": "inactive"},
    )

    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=tmp_path / "active-combined",
        start_runtime_daemon=False,
        time_budget_seconds=None,
    )

    assert result.ok is True
    assert result.state == "installed_inactive"
    assert result.report["installation_ok"] is True
    assert result.report["activation_ok"] is False
    assert result.report["effective_profile"] == "combined"
    assert result.report["memory_manifest_verification"]["ok"] is True
    assert result.report["sqlite"]["ok"] is True


def test_current_package_with_unknown_profile_is_rejected(tmp_path: Path) -> None:
    source = _write_installable_source(tmp_path / "source")
    parts_dir = tmp_path / "parts"
    _write_installable_package(parts_dir, source, profile="unknown")

    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=tmp_path / "active",
        start_runtime_daemon=False,
    )

    assert result.ok is False
    assert result.state == "package_profile_rejected"
    assert result.report["profile_gate"]["reason"] == "current_package_profile_missing_or_unsupported"


def test_current_package_with_v2_schema_installs_without_bootstrap_block(
    tmp_path: Path,
) -> None:
    source = _write_installable_source(tmp_path / "source")
    parts_dir = tmp_path / "parts"
    _write_installable_package(
        parts_dir,
        source,
        profile="system",
        schema_version="jazn_package_set/v2",
    )

    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=tmp_path / "active",
        start_runtime_daemon=False,
    )

    assert result.ok is True
    assert result.state == "installed_inactive"
    assert result.report["package_set"]["schema_version"] == "jazn_package_set/v2"


def test_current_package_with_unsupported_schema_is_blocked_without_traceback(
    tmp_path: Path,
) -> None:
    source = _write_installable_source(tmp_path / "source")
    parts_dir = tmp_path / "parts"
    _write_installable_package(
        parts_dir,
        source,
        profile="system",
        schema_version="jazn_package_set/v999",
    )

    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=tmp_path / "active",
        start_runtime_daemon=False,
    )

    assert result.ok is False
    assert result.state == "bootstrap_blocked"
    assert result.report["error"]["code"] == "runtime_package_contract_invalid"


def test_package_sidecar_version_must_match_extracted_runtime(tmp_path: Path) -> None:
    source = _write_installable_source(tmp_path / "source")
    parts_dir = tmp_path / "parts"
    _write_installable_package(
        parts_dir,
        source,
        profile="system",
        package_version="v999",
    )

    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=tmp_path / "active",
        start_runtime_daemon=False,
        time_budget_seconds=None,
    )

    assert result.ok is False
    assert result.state == "package_profile_tree_mismatch"
    assert result.report["profile_gate"]["reason"] == "package_sidecar_runtime_version_mismatch"


def test_unmanifested_code_inside_package_is_rejected(tmp_path: Path) -> None:
    source = _write_installable_source(tmp_path / "source")
    (source / "latka_jazn" / "injected.py").write_text("print('injected')\n", encoding="utf-8")
    parts_dir = tmp_path / "parts"
    _write_installable_package(parts_dir, source, profile="system")

    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=tmp_path / "active",
        start_runtime_daemon=False,
        time_budget_seconds=None,
    )

    assert result.ok is False
    assert result.state == "staging_runtime_invalid"
    assert result.report["staging_preflight"]["manifest_verification"]["ok"] is False
    assert {item["code"] for item in result.report["staging_preflight"]["manifest_verification"]["errors"]} >= {
        "unexpected_static_file"
    }


def test_package_with_mutable_runtime_state_is_rejected(tmp_path: Path) -> None:
    source = _write_installable_source(tmp_path / "source")
    forged = source / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json"
    forged.parent.mkdir()
    forged.write_text('{"active_state":"active_trusted"}', encoding="utf-8")
    parts_dir = tmp_path / "parts"
    _write_installable_package(parts_dir, source, profile="system")

    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=tmp_path / "active",
        start_runtime_daemon=False,
        time_budget_seconds=None,
    )

    assert result.ok is False
    assert result.state == "package_profile_tree_mismatch"
    assert result.report["profile_gate"]["reason"] == "package_contains_mutable_runtime_state"


def test_loader_io_failure_returns_structured_block_without_traceback(
    tmp_path: Path,
    capsys,
) -> None:
    work_file = tmp_path / "not-a-directory"
    work_file.write_text("occupied", encoding="utf-8")

    exit_code = cli_main(
        [
            "runtime-bootstrap",
            "--parts-dir",
            str(tmp_path / "missing-parts"),
            "--destination",
            str(tmp_path / "active"),
            "--work-dir",
            str(work_file),
            "--no-start-daemon",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 11
    assert output["ok"] is False
    assert output["state"] == "bootstrap_blocked"
    assert output["report"]["error"]["code"] == "runtime_bootstrap_io_error"


def test_missing_package_source_returns_structured_block(tmp_path: Path) -> None:
    result = recover_chatgpt_runtime(
        parts_dir=tmp_path / "missing-parts",
        destination=tmp_path / "active",
        work_dir=tmp_path / "work",
        start_runtime_daemon=False,
    )

    assert result.ok is False
    assert result.state == "bootstrap_blocked"
    assert result.report["error"]["code"] == "runtime_package_source_missing"


def test_combined_package_memory_manifest_is_verified_and_tamper_is_rejected(
    tmp_path: Path,
) -> None:
    version_file = tmp_path / "latka_jazn" / "version.py"
    version_file.parent.mkdir()
    version_file.write_text(
        "DISTRIBUTION_VERSION = '1'\nPACKAGE_VERSION = 'v1'\nPACKAGE_RELEASE_NAME = ''\n",
        encoding="utf-8",
    )
    memory_file = tmp_path / "memory" / "raw" / "identity.txt"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text("verified memory", encoding="utf-8")
    manifest = tmp_path / "memory" / "MEMORY_PACKAGE_MANIFEST.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "jazn_memory_package_manifest/v1",
                "runtime_version": "v1",
                "file_count": 1,
                "files": [
                    {
                        "path": "memory/raw/identity.txt",
                        "size_bytes": memory_file.stat().st_size,
                        "sha256": _sha256(memory_file),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    verified = _verify_memory_package_manifest(tmp_path)
    memory_file.write_text("tampered memory with extra bytes", encoding="utf-8")
    tampered = _verify_memory_package_manifest(tmp_path)

    assert verified["ok"] is True
    assert verified["verified_file_count"] == 1
    assert tampered["ok"] is False
    assert {item["code"] for item in tampered["errors"]} >= {
        "memory_package_file_size_mismatch",
        "memory_package_file_sha256_mismatch",
    }
