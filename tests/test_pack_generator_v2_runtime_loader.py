from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from latka_jazn.bootstrap.runtime_bootstrap_v50 import (
    _discover_generator_sidecar,
    _materialize_v2_compat,
)
from latka_jazn.packaging.split_zip_package import (
    join_split_package_to_zip,
    load_package_expectations,
    load_package_set_metadata,
    test_joined_zip as verify_joined_zip,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_package(
    tmp_path: Path,
    *,
    name: str = "jazn_latka_vX.system.zip",
    content: str = "system",
    split: bool = False,
    renamed_sidecar: bool = False,
) -> tuple[Path, Path, dict]:
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("run.py", "print('ok')\n")
        zf.writestr("latka_jazn/version.py", "PACKAGE_VERSION='X'\n")
    digest = _sha(archive)
    manifest = {
        "schema_version": "jazn_pack_generator_package/v2",
        "package_version": "X",
        "content": content,
        "archive": {
            "logical_filename": name,
            "logical_sha256": digest,
            "logical_size_bytes": archive.stat().st_size,
            "compression": "ZIP_DEFLATED",
            "compression_level": 6,
            "zip64": True,
        },
        "split": {"enabled": False, "requested": False, "part_size_bytes": 0, "parts": []},
        "source": {"byte_exact": True, "entries": []},
    }
    if split:
        raw = archive.read_bytes(); cut = max(1, len(raw) // 2); parts = []
        for no, chunk in enumerate((raw[:cut], raw[cut:]), start=1):
            part = tmp_path / f"{name}.{no:03d}"
            part.write_bytes(chunk)
            parts.append({"part_no": no, "filename": part.name, "size_bytes": len(chunk), "sha256": _sha(part)})
        archive.unlink()
        manifest["split"] = {"enabled": True, "requested": True, "part_size_bytes": cut, "parts": parts}
    sidecar = tmp_path / (f"{name}.package(1).json" if renamed_sidecar else f"{name}.package.json")
    sidecar.write_text(json.dumps(manifest), encoding="utf-8")
    return archive, sidecar, manifest


def _adapt(source: Path, manifest: dict, output: Path) -> str:
    output.mkdir()
    return _materialize_v2_compat(source, manifest, output)


def test_generator_v2_direct_zip_adapts_to_verified_single_transport_volume(tmp_path: Path) -> None:
    archive, _sidecar, manifest = _write_package(tmp_path)
    compat = tmp_path / "compat"
    name = _adapt(tmp_path, manifest, compat)
    metadata = load_package_set_metadata(compat, name)
    assert metadata["profile"] == "system"
    expected, full_sha, source = load_package_expectations(compat, name)
    assert source == "package.json"
    assert len(expected) == 1 and expected[0].filename == name
    assert expected[0].size_bytes == archive.stat().st_size
    assert expected[0].sha256 == _sha(archive) == full_sha
    joined = join_split_package_to_zip(compat, name, zip_out=tmp_path / "joined.zip", force=True)
    assert _sha(joined) == full_sha
    assert verify_joined_zip(joined)["ok"] is True


def test_generator_v2_split_zip_adapts_and_rejoins_exactly(tmp_path: Path) -> None:
    archive, _sidecar, manifest = _write_package(tmp_path, split=True)
    assert not archive.exists()
    compat = tmp_path / "compat"
    name = _adapt(tmp_path, manifest, compat)
    expected, full_sha, source = load_package_expectations(compat, name)
    assert source == "package.json"
    assert [item.filename for item in expected] == [f"{name}.001", f"{name}.002"]
    joined = join_split_package_to_zip(compat, name, zip_out=tmp_path / "joined.zip", force=True)
    assert _sha(joined) == full_sha == manifest["archive"]["logical_sha256"]
    assert verify_joined_zip(joined)["ok"] is True


def test_generator_v2_host_renamed_sidecar_keeps_declared_archive_identity(tmp_path: Path) -> None:
    _archive, sidecar, manifest = _write_package(tmp_path, renamed_sidecar=True)
    found = _discover_generator_sidecar(tmp_path, None)
    assert found is not None and found[0] == sidecar
    compat = tmp_path / "compat"
    name = _adapt(tmp_path, found[1], compat)
    assert name == manifest["archive"]["logical_filename"]
    assert load_package_set_metadata(compat, name)["schema_version"] == "jazn_package_set/v3"


def test_generator_v2_content_maps_to_runtime_profiles(tmp_path: Path) -> None:
    for content, expected_profile in (("memory", "memory"), ("system+memory", "combined")):
        case = tmp_path / content.replace("+", "-"); case.mkdir()
        _archive, _sidecar, manifest = _write_package(case, name=f"{content}.zip", content=content)
        compat = case / "compat"
        name = _adapt(case, manifest, compat)
        assert load_package_set_metadata(compat, name)["profile"] == expected_profile
