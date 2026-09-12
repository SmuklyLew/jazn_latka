from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import importlib
import zipfile

import pytest


def generator():
    return importlib.import_module("tools.jazn_pack_generator")


def _root(tmp_path: Path, version: str, release: str) -> Path:
    root = tmp_path / "root"
    version_py = root / "latka_jazn" / "version.py"
    version_py.parent.mkdir(parents=True)
    version_py.write_text(
        "DISTRIBUTION_VERSION = %r\nPACKAGE_VERSION = %r\nPACKAGE_RELEASE_NAME = %r\n"
        "PACKAGE_VERSION_FULL = f\"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}\" if PACKAGE_RELEASE_NAME else PACKAGE_VERSION\n"
        % (version, version, release),
        encoding="utf-8",
    )
    return root


def test_v89_keeps_v88_portability_api_exposed() -> None:
    module = generator()
    assert module.GENERATOR_VERSION == "8.9"
    assert module.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.9"
    assert callable(module.run_studio)
    assert callable(module.refresh_archive_basename_for_current_release)


def test_v88_startup_refreshes_stale_generator_owned_name(tmp_path: Path) -> None:
    module = generator()
    root = _root(tmp_path, "16.3.25.3.4", "jazn-pack-generator-v87-studio-portable-zip")
    state = module.InteractiveState(
        source=root,
        out_dir=tmp_path / "out",
        archive_basename="jazn_latka_v16.3.25.3.3-chatgpt-package-discovery-bootstrap",
    )
    assert module.refresh_archive_basename_for_current_release(state) is True
    assert state.archive_basename == "jazn_latka_v16.3.25.3.4-jazn-pack-generator-v87-studio-portable-zip"


def test_v88_preserves_explicit_custom_current_name(tmp_path: Path) -> None:
    module = generator()
    root = _root(tmp_path, "16.3.25.3.4", "jazn-pack-generator-v87-studio-portable-zip")
    custom = "backup_K_v16.3.25.3.4-jazn-pack-generator-v87-studio-portable-zip"
    state = module.InteractiveState(source=root, out_dir=tmp_path / "out", archive_basename=custom)
    assert module.refresh_archive_basename_for_current_release(state) is False
    assert state.archive_basename == custom


def test_v88_rejects_windows_reserved_member_name() -> None:
    module = generator()
    plan = SimpleNamespace(entries=[SimpleNamespace(relative="docs/CON.txt")])
    with pytest.raises(module.PackError, match="zarezerwowana"):
        module.validate_portable_member_names(plan)


def test_v88_rejects_windows_casefold_collision() -> None:
    module = generator()
    plan = SimpleNamespace(entries=[
        SimpleNamespace(relative="Latka/File.txt"),
        SimpleNamespace(relative="latka/file.TXT"),
    ])
    with pytest.raises(module.PackError, match="Kolizja nazw"):
        module.validate_portable_member_names(plan)


def test_v88_binary_transport_is_not_claimed_as_direct_windows_zip() -> None:
    module = generator()
    profile = module.interoperability_profile("zip", "binary")
    assert profile["portable_standard_zip"] is False
    assert profile["requires_join"] is True
    assert profile["targets"]["windows_11_file_explorer"] == "join_required"


def test_v88_independent_deflate_profile_is_portable_standard_zip() -> None:
    module = generator()
    profile = module.interoperability_profile("zip", "independent")
    assert profile["portable_standard_zip"] is True
    assert profile["requires_join"] is False
    assert profile["targets"]["windows_11_file_explorer"] == "direct"


def test_v88_standard_writer_uses_deflate_and_unicode_names(tmp_path: Path) -> None:
    module = generator()
    raw = "zażółć gęślą jaźń".encode("utf-8")
    entry = module.PlanEntry(
        relative="docs/zażółć.txt",
        source=None,
        size_bytes=len(raw),
        sha256=module.sha256_bytes(raw),
        classification="test",
        virtual_bytes=raw,
    )
    target = tmp_path / "portable.zip"
    module.write_zip_file(target, [entry], 6)
    with zipfile.ZipFile(target, "r") as archive:
        info = archive.getinfo("docs/zażółć.txt")
        assert info.compress_type == zipfile.ZIP_DEFLATED
        assert archive.read(info) == raw
        assert archive.testzip() is None
