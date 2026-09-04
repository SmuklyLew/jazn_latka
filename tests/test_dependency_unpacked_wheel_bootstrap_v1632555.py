from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import importlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

import latka_jazn.dependencies.wheelhouse_bootstrap as bootstrap
from latka_jazn.dependencies.wheelhouse import (
    LOCK_NAME,
    MANIFEST_NAME,
    WHEELHOUSE_SCHEMA,
    render_hash_lock,
    sha256_file,
    target_spec,
    verify_bundle,
    wheel_metadata,
)


def _record_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"sha256={encoded}"


def _write_wheel(
    directory: Path,
    *,
    name: str,
    version: str,
    package_members: dict[str, bytes],
    extra_members: dict[str, bytes] | None = None,
) -> Path:
    normalized = name.replace("-", "_")
    wheel = directory / f"{normalized}-{version}-py3-none-any.whl"
    dist_info = f"{normalized}-{version}.dist-info"
    members = dict(package_members)
    members.update(extra_members or {})
    members[f"{dist_info}/METADATA"] = (
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n"
        "License-Expression: MIT\n\n"
    ).encode("utf-8")
    members[f"{dist_info}/WHEEL"] = (
        "Wheel-Version: 1.0\n"
        "Generator: jazn-test\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    ).encode("utf-8")
    record_name = f"{dist_info}/RECORD"
    rows = [f"{path},{_record_hash(data)},{len(data)}" for path, data in members.items()]
    rows.append(f"{record_name},,")
    members[record_name] = ("\n".join(rows) + "\n").encode("utf-8")
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in members.items():
            archive.writestr(path, data)
    return wheel


def _fake_packaging_wheel(directory: Path, *, unsafe_member: bool = False) -> Path:
    package_members = {
        "packaging/__init__.py": b"__version__ = '99.0'\n",
        "packaging/version.py": b"""
class Version:
    def __init__(self, value):
        self.value = str(value)
    def __str__(self):
        return self.value
    def _parts(self):
        return tuple(int(part) for part in self.value.split('.') if part.isdigit())
    def __lt__(self, other):
        return self._parts() < Version(other)._parts()
    def __ge__(self, other):
        return not self < other
""",
        "packaging/specifiers.py": b"""
from .version import Version
class SpecifierSet:
    def __init__(self, value):
        self.value = str(value or '')
    def __contains__(self, version):
        value = Version(str(version))
        for item in [part.strip() for part in self.value.split(',') if part.strip()]:
            if item.startswith('>=') and value < Version(item[2:]):
                return False
        return True
""",
        "packaging/utils.py": b"""
from .version import Version
class _Tag:
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return self.value
    def __hash__(self):
        return hash(self.value)
    def __eq__(self, other):
        return str(self) == str(other)
def parse_wheel_filename(filename):
    stem = filename[:-4] if filename.endswith('.whl') else filename
    name, version, py, abi, platform = stem.rsplit('-', 4)
    return name.replace('_', '-'), Version(version), (), frozenset({_Tag(f'{py}-{abi}-{platform}')})
""",
    }
    extras = {"../escape.py": b"raise SystemExit('must never be extracted')\n"} if unsafe_member else None
    return _write_wheel(
        directory,
        name="packaging",
        version="99.0",
        package_members=package_members,
        extra_members=extras,
    )


def _demo_wheel(directory: Path) -> Path:
    return _write_wheel(
        directory,
        name="demo",
        version="1.0",
        package_members={"demo/__init__.py": b"__version__ = '1.0'\n"},
    )


def _bundle(tmp_path: Path, *, unsafe_packaging_member: bool = False) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    packaging_wheel = _fake_packaging_wheel(bundle, unsafe_member=unsafe_packaging_member)
    demo_wheel = _demo_wheel(bundle)

    files: list[dict[str, object]] = []
    resolved: list[dict[str, object]] = []
    for wheel in (packaging_wheel, demo_wheel):
        metadata = wheel_metadata(wheel)
        row = {
            "filename": wheel.name,
            "size_bytes": wheel.stat().st_size,
            "sha256": sha256_file(wheel),
            "metadata": metadata,
        }
        files.append(row)
        filename_metadata = metadata["filename"]
        resolved.append({
            "name": str(filename_metadata["distribution"]),
            "version": str(filename_metadata["version"]),
            "filename": wheel.name,
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
            "requires_python": metadata.get("requires_python"),
            "license_expression": metadata.get("license_expression"),
            "license": metadata.get("license"),
            "license_files": list(metadata.get("license_files") or []),
            "tags": list(filename_metadata.get("tags") or []),
            "record_verified": True,
        })

    resolved.sort(key=lambda item: str(item["name"]))
    lock_path = bundle / LOCK_NAME
    lock_path.write_bytes(render_hash_lock(resolved).encode("utf-8"))
    target = target_spec("current", f"{sys.version_info.major}.{sys.version_info.minor}")
    manifest = {
        "schema_version": WHEELHOUSE_SCHEMA,
        "runtime_version": "fixture",
        "created_at_utc": "2026-09-03T00:00:00+00:00",
        "profiles": ["core"],
        "resolved_profiles": ["core"],
        "requirements": ["demo==1.0", "packaging==99.0"],
        "direct_requirements": ["demo==1.0", "packaging==99.0"],
        "dependency_contract_fingerprint": "fixture",
        "target": target.to_dict(),
        "resolved_distributions": resolved,
        "files": files,
        "wheel_count": len(files),
        "total_size_bytes": sum(int(item["size_bytes"]) for item in files),
        "hash_lock_sha256": sha256_file(lock_path),
    }
    (bundle / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def test_clean_room_verifier_bootstraps_only_from_unpacked_packaging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle(tmp_path)
    real_context = bootstrap.unpacked_packaging_bootstrap
    observed: dict[str, str] = {}

    monkeypatch.setattr(bootstrap, "packaging_runtime_available", lambda: False)

    @contextmanager
    def observing_context(*args, **kwargs):
        with real_context(*args, **kwargs) as state:
            module = importlib.import_module("packaging")
            origin = str(module.__file__).replace("\\", "/")
            extracted_root = str(state["extracted_root"]).replace("\\", "/")
            bootstrap_wheel = str(bundle / "packaging-99.0-py3-none-any.whl")
            assert origin.startswith(extracted_root + "/")
            assert ".whl/" not in origin.lower()
            assert ".zip/" not in origin.lower()
            assert Path(sys.path[0]).resolve() == Path(state["extracted_root"]).resolve()
            assert all(str(item) != bootstrap_wheel for item in sys.path)
            observed["origin"] = origin
            observed["root"] = extracted_root
            yield state

    monkeypatch.setattr(bootstrap, "unpacked_packaging_bootstrap", observing_context)
    verified = verify_bundle(bundle)

    assert verified["ok"] is True
    assert verified["verified_wheel_count"] == 2
    assert verified["validator_dependency_source"] == "verified_unpacked_packaging_bootstrap"
    assert verified["validator_bootstrap_wheel"] == "packaging-99.0-py3-none-any.whl"
    assert observed["origin"].startswith(observed["root"] + "/")
    assert not Path(observed["root"]).exists()
    assert all(str(bundle / "packaging-99.0-py3-none-any.whl") != item for item in sys.path)


def test_clean_room_bootstrap_rejects_unsafe_wheel_member_before_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle(tmp_path, unsafe_packaging_member=True)
    monkeypatch.setattr(bootstrap, "packaging_runtime_available", lambda: False)

    result = verify_bundle(bundle)

    assert result["ok"] is False
    assert result["validator_dependency_source"] == "unavailable"
    assert result["errors"][0]["code"] == "validator_dependency_bootstrap_failed"
    assert "unsafe" in result["errors"][0]["detail"].lower() or "escape" in result["errors"][0]["detail"].lower()
    assert not (tmp_path / "escape.py").exists()


def test_packaging_runtime_available_rejects_archive_origins() -> None:
    class Spec:
        origin = "/tmp/example.whl/packaging/__init__.py"
        loader = None

    class Module:
        __spec__ = Spec()
        __file__ = Spec.origin

    assert bootstrap._module_is_unpacked(Module()) is False
    assert bootstrap._origin_is_archive_backed("C:\\cache\\packaging.whl\\packaging\\utils.py") is True
