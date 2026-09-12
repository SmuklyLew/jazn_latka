from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from latka_jazn.bootstrap import chatgpt_recovery as recovery_module
from latka_jazn.bootstrap.chatgpt_recovery import (
    RuntimePreflightReport,
    _discover_memory_package,
    recover_chatgpt_runtime,
)
from latka_jazn.packaging.split_zip_package import (
    infer_base_zip_name,
    load_package_expectations,
    validate_package_parts,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_memory_sidecar_renamed_by_host(parts_dir: Path) -> str:
    parts_dir.mkdir(parents=True, exist_ok=True)
    package_name = "jazn_latka_v16.3.25.3.3-chatgpt-package-discovery-bootstrap_memory.zip"
    canonical_part = f"{package_name}.001"
    uploaded_part = parts_dir / f"{package_name}(1).001"
    uploaded_part.write_bytes(b"legacy-memory-part")
    payload = {
        "schema_version": "jazn_package_set/v2",
        "package_name": package_name,
        "profile": "memory",
        "archive_format": "binary",
        "package_version": "v16.3.25.3.3-chatgpt-package-discovery-bootstrap",
        "outputs": [{
            "part_no": 1,
            "filename": canonical_part,
            "size_bytes": uploaded_part.stat().st_size,
            "sha256": _sha256(uploaded_part),
            "is_complete_zip": False,
        }],
    }
    (parts_dir / f"{package_name}.package(1).json").write_text(json.dumps(payload), encoding="utf-8")
    (parts_dir / f"{package_name}.parts(1).sha256").write_text(
        f"{_sha256(uploaded_part)}  {canonical_part}\n", encoding="utf-8"
    )
    return package_name


def _write_complete_system_zip_with_parts_sha(parts_dir: Path) -> str:
    parts_dir.mkdir(parents=True, exist_ok=True)
    package_name = "jazn_latka_v16.3.25.3.3-chatgpt-package-discovery-bootstrap.zip"
    archive = parts_dir / package_name
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("run.py", "print('system runtime')\n")
        zf.writestr(
            "latka_jazn/version.py",
            "PACKAGE_VERSION_FULL = '16.3.25.3.3-chatgpt-package-discovery-bootstrap'\n",
        )
    (parts_dir / f"{package_name}.parts.sha256").write_text(
        f"{_sha256(archive)}  {package_name}\n", encoding="utf-8"
    )
    return package_name


def test_runtime_discovery_ignores_memory_profile_and_finds_checksum_only_system_zip(tmp_path: Path) -> None:
    memory_name = _write_memory_sidecar_renamed_by_host(tmp_path)
    system_name = _write_complete_system_zip_with_parts_sha(tmp_path)
    selected = infer_base_zip_name(
        tmp_path,
        allowed_profiles=frozenset({"system", "combined", "unknown"}),
    )
    assert selected == system_name
    assert selected != memory_name


def test_memory_autodiscovery_accepts_chatgpt_renamed_package_sidecar(tmp_path: Path) -> None:
    package_name = _write_memory_sidecar_renamed_by_host(tmp_path)
    result = _discover_memory_package(tmp_path)
    assert result["ok"] is True
    assert result["state"] == "memory_package_discovered"
    assert result["package_name"] == package_name
    assert str(result["sidecar_path"]).endswith(".package(1).json")


def test_single_complete_zip_listed_by_parts_sha_is_a_valid_package_part(tmp_path: Path) -> None:
    package_name = _write_complete_system_zip_with_parts_sha(tmp_path)
    expected, _, source = load_package_expectations(tmp_path, package_name)
    validated, _, validated_source = validate_package_parts(tmp_path, package_name)
    assert source == "parts.sha256"
    assert validated_source == "parts.sha256"
    assert [item.filename for item in expected] == [package_name]
    assert [item.filename for item in validated] == [package_name]


def test_verified_old_destination_does_not_silently_ignore_new_system_package(tmp_path: Path, monkeypatch) -> None:
    parts_dir = tmp_path / "parts"
    system_name = _write_complete_system_zip_with_parts_sha(parts_dir)
    destination = tmp_path / "active-old"
    destination.mkdir()
    preflight = RuntimePreflightReport(
        ok=True,
        active_root=str(destination),
        structure_ok=True,
        manifest_ok=True,
        provenance_ok=True,
        marker_ok=True,
        start_file="run.py",
        version="16.3.25.3.2-chatgpt-loader-capability-bootstrap",
        manifest_version="16.3.25.3.2-chatgpt-loader-capability-bootstrap",
        marker_path=str(tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json"),
    )
    monkeypatch.setattr(recovery_module, "runtime_preflight", lambda *_args, **_kwargs: preflight)
    result = recover_chatgpt_runtime(
        parts_dir=parts_dir,
        destination=destination,
        start_runtime_daemon=False,
        auto_attach_memory=False,
    )
    assert result.ok is False
    assert result.state == "incoming_package_requires_new_destination"
    assert result.exit_code == 9
    assert result.report["replacement_blocked"]["incoming_base_zip_name"] == system_name
    assert result.report["replacement_blocked"]["reason"] == "incoming_system_package_requires_new_destination"
