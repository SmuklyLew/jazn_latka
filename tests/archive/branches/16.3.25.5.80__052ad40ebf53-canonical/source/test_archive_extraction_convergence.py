from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

import latka_jazn.archive.capabilities as capabilities
import latka_jazn.archive.rar_backend as rar_backend
import latka_jazn.archive.backend_convergence as convergence
from latka_jazn.archive import (
    ArchiveEntry,
    ArchiveError,
    ArchiveExtractionService,
    ArchiveInspection,
    ArchiveSecurityLimits,
    ArchiveWriteEntry,
    normalize_archive_format,
)


def _service() -> ArchiveExtractionService:
    return ArchiveExtractionService(ArchiveSecurityLimits(require_free_space=False))


def _package_set_hash(outputs: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for item in outputs:
        digest.update(
            f"{item['part_no']}\0{item['filename']}\0{item['size_bytes']}\0{item['sha256']}\n".encode("utf-8")
        )
    return digest.hexdigest()


def _build_split_fixture(tmp_path: Path) -> tuple[ArchiveExtractionService, Path, Path, bytes, dict[str, object]]:
    service = _service()
    payload = ("Jaźń transport alias regression\n" * 120).encode("utf-8")
    logical = tmp_path / "payload.zip"
    service.create_archive(
        [ArchiveWriteEntry("data/payload.txt", data=payload)],
        logical,
        archive_format="zip",
    )
    logical_sha = hashlib.sha256(logical.read_bytes()).hexdigest()
    outputs, split_sha = service.split_file(logical, tmp_path, logical.name, 512)
    assert split_sha == logical_sha
    logical.unlink()
    sidecar: dict[str, object] = {
        "schema_version": "jazn_package_set/v2",
        "package_name": "payload.zip",
        "profile": "memory",
        "archive_format": "binary",
        "container_format": "zip",
        "logical_zip_sha256": logical_sha,
        "logical_archive_sha256": logical_sha,
        "outputs": outputs,
        "package_set_sha256": _package_set_hash(outputs),
        "entries": [
            {
                "path": "data/payload.txt",
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "classification": "fixture",
            }
        ],
    }
    sidecar_path = tmp_path / "payload.zip.package.json"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    return service, Path(str(tmp_path / outputs[0]["filename"])), sidecar_path, payload, sidecar


def _transport_rename_parts(tmp_path: Path, sidecar: dict[str, object]) -> list[Path]:
    renamed: list[Path] = []
    rows = sidecar["outputs"]
    assert isinstance(rows, list)
    for raw in rows:
        assert isinstance(raw, dict)
        logical_name = str(raw["filename"])
        source = tmp_path / logical_name
        suffix = source.suffix
        target = source.with_name(source.name[: -len(suffix)] + "(1)" + suffix)
        source.rename(target)
        renamed.append(target)
    return renamed


def test_transport_renamed_split_parts_and_sidecar_roundtrip(tmp_path: Path) -> None:
    service, _first, sidecar_path, payload, sidecar = _build_split_fixture(tmp_path)
    renamed = _transport_rename_parts(tmp_path, sidecar)
    renamed_sidecar = sidecar_path.with_name("payload.zip.package(1).json")
    sidecar_path.rename(renamed_sidecar)

    verified = service._verified_outputs(tmp_path, sidecar)
    assert len(verified) == len(renamed)
    assert all(row["transport_alias_used"] is True for row in verified)
    output_rows = sidecar["outputs"]
    assert isinstance(output_rows, list)
    logical_filenames: list[object] = []
    for raw_output in output_rows:
        assert isinstance(raw_output, dict)
        logical_filenames.append(raw_output["filename"])
    assert [row["logical_filename"] for row in verified] == logical_filenames

    destination = tmp_path / "out"
    result = service.extract_source(renamed[0], destination)

    assert result["ok"] is True
    assert (destination / "data/payload.txt").read_bytes() == payload
    assert Path(result["sidecar"]).name == renamed_sidecar.name


def test_direct_transport_renamed_sidecar_is_recognized_by_schema(tmp_path: Path) -> None:
    service, _first, sidecar_path, payload, sidecar = _build_split_fixture(tmp_path)
    _transport_rename_parts(tmp_path, sidecar)
    renamed_sidecar = sidecar_path.with_name("payload.zip.package(7).json")
    sidecar_path.rename(renamed_sidecar)

    destination = tmp_path / "direct-sidecar-out"
    result = service.extract_source(renamed_sidecar, destination)
    assert result["ok"] is True
    assert (destination / "data/payload.txt").read_bytes() == payload


def test_transport_alias_ambiguity_fails_closed(tmp_path: Path) -> None:
    service, _first, sidecar_path, _payload, sidecar = _build_split_fixture(tmp_path)
    renamed = _transport_rename_parts(tmp_path, sidecar)
    first = renamed[0]
    duplicate = first.with_name(first.name.replace("(1)", "(2)"))
    duplicate.write_bytes(first.read_bytes())

    with pytest.raises(ArchiveError, match="package_output_transport_alias_ambiguous"):
        service.extract_package_sidecar(sidecar_path, tmp_path / "out")


def test_wrong_exact_logical_output_is_not_bypassed_by_valid_alias(tmp_path: Path) -> None:
    service, first, sidecar_path, _payload, sidecar = _build_split_fixture(tmp_path)
    rows = sidecar["outputs"]
    assert isinstance(rows, list) and rows
    original = tmp_path / str(rows[0]["filename"])
    alias = original.with_name(original.name[:-4] + "(1)" + original.suffix)
    original.rename(alias)
    original.write_bytes(b"x" * int(rows[0]["size_bytes"]))

    with pytest.raises(ArchiveError, match="package_output_sha256_mismatch"):
        service.extract_package_sidecar(sidecar_path, tmp_path / "out")


def test_rar_aliases_and_signature_detection(tmp_path: Path) -> None:
    assert normalize_archive_format("rar3") == "rar"
    assert normalize_archive_format("rar5") == "rar"
    fake = tmp_path / "fixture.bin"
    fake.write_bytes(convergence.RAR5_SIGNATURE + b"fixture")
    assert fake.read_bytes().startswith(convergence.RAR5_SIGNATURE)


def test_archive_service_routes_rar_through_canonical_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "fixture.rar"
    source.write_bytes(convergence.RAR5_SIGNATURE + b"fixture")
    entry = ArchiveEntry(
        name="nested/value.txt",
        size_bytes=5,
        compressed_size_bytes=5,
        is_dir=False,
        is_symlink=False,
        is_regular_file=True,
        encrypted=False,
    )
    inspection = ArchiveInspection(
        archive_format="rar",
        entries=(entry,),
        total_uncompressed_bytes=5,
        encrypted=False,
        crc_verified=True,
    )

    monkeypatch.setattr(rar_backend, "inspect_rar", lambda *args, **kwargs: inspection)

    def _fake_extract(_source: Path, destination: Path, **kwargs: object) -> ArchiveInspection:
        target = Path(destination) / "nested/value.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"value")
        return inspection

    monkeypatch.setattr(rar_backend, "extract_rar_to_directory", _fake_extract)
    destination = tmp_path / "rar-out"
    result = _service().extract_source(source, destination)
    assert result["container_format"] == "rar"
    assert (destination / "nested/value.txt").read_bytes() == b"value"


def test_py7zr_below_security_floor_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("py7zr")
    monkeypatch.setitem(sys.modules, "py7zr", fake)
    original_version = convergence.metadata.version
    monkeypatch.setattr(
        convergence.metadata,
        "version",
        lambda name: "1.1.2" if name == "py7zr" else original_version(name),
    )
    with pytest.raises(ArchiveError, match=r"py7zr_version_unsafe:1\.1\.2:requires>=1\.1\.3"):
        convergence.import_safe_py7zr()


def test_rarfile_below_security_floor_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("rarfile")
    monkeypatch.setitem(sys.modules, "rarfile", fake)
    original_version = rar_backend.metadata.version
    monkeypatch.setattr(
        rar_backend.metadata,
        "version",
        lambda name: "4.2" if name == "rarfile" else original_version(name),
    )
    with pytest.raises(ArchiveError, match=r"rarfile_version_unsafe:4\.2:requires>=4\.5\.0"):
        rar_backend._rarfile_module()


def test_capability_report_exposes_transport_and_backend_security_contract() -> None:
    report = capabilities.archive_capability_report().to_dict()
    transport = report["transport_capabilities"]
    policy = report["safety_policy"]
    assert transport["transport_renamed_output_resolution"] == "logical-name-hint + stable-size + sha256"
    assert transport["transport_renamed_sidecar_discovery"] is True
    assert transport["stable_input_identity_during_hash_and_join"] is True
    assert policy["minimum_safe_py7zr_enforced"] == "1.1.3"
    assert policy["minimum_safe_rarfile_enforced"] == "4.5.0"
