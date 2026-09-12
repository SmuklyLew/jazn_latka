from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import warnings
import zipfile

import pytest

import CHATGPT_BOOTSTRAP as bootstrap


ROOT = Path(__file__).resolve().parents[1]
_REQUIRED_FILES = {
    "run.py": "print('run')\n",
    "AGENTS.md": "# test router\n",
    "latka_jazn/version.py": "PACKAGE_VERSION = 'test'\n",
    "PACKAGE_INTEGRITY_MANIFEST.json": "{}\n",
    "SOURCE_PROVENANCE.json": "{}\n",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_valid_system_zip(path: Path, *, prefix: str = "") -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in _REQUIRED_FILES.items():
            zf.writestr(f"{prefix}{name}", content)


def test_explicit_sha_without_local_sidecar_materializes_operator(tmp_path: Path) -> None:
    archive = tmp_path / "system.zip"
    destination = tmp_path / "active" / "v54"
    _write_valid_system_zip(archive, prefix="jazn/")

    payload = bootstrap.bootstrap_system_zip(
        zip_path=archive,
        destination=destination,
        expected_sha256=_sha256(archive),
        expected_size_bytes=archive.stat().st_size,
    )

    assert payload["ok"] is True
    assert payload["state"] == "materialized_operator_ready"
    assert payload["operator_entrypoint"] == "run.py"
    assert payload["stable_during_hash"] is True
    assert payload["source_size_bytes"] == archive.stat().st_size
    assert (destination / "run.py").is_file()
    assert (destination / "AGENTS.md").is_file()


def test_expected_size_mismatch_fails_before_materialization(tmp_path: Path) -> None:
    archive = tmp_path / "system.zip"
    destination = tmp_path / "active" / "v54"
    _write_valid_system_zip(archive)

    with pytest.raises(bootstrap.BootstrapError) as exc_info:
        bootstrap.bootstrap_system_zip(
            zip_path=archive,
            destination=destination,
            expected_sha256=_sha256(archive),
            expected_size_bytes=archive.stat().st_size + 1,
        )

    assert exc_info.value.code == "source_size_mismatch"
    assert not destination.exists()


def test_path_traversal_member_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "system.zip"
    destination = tmp_path / "active" / "v54"
    _write_valid_system_zip(archive)
    with zipfile.ZipFile(archive, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../escape.txt", "nope")

    with pytest.raises(bootstrap.BootstrapError) as exc_info:
        bootstrap.bootstrap_system_zip(
            zip_path=archive,
            destination=destination,
            expected_sha256=_sha256(archive),
            expected_size_bytes=archive.stat().st_size,
        )

    assert exc_info.value.code == "unsafe_zip_member"
    assert not destination.exists()
    assert not (tmp_path / "escape.txt").exists()


def test_unix_symlink_member_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "system.zip"
    destination = tmp_path / "active" / "v54"
    _write_valid_system_zip(archive)

    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as zf:
        zf.writestr(link, "run.py")

    with pytest.raises(bootstrap.BootstrapError) as exc_info:
        bootstrap.bootstrap_system_zip(
            zip_path=archive,
            destination=destination,
            expected_sha256=_sha256(archive),
            expected_size_bytes=archive.stat().st_size,
        )

    assert exc_info.value.code == "zip_symlink_rejected"
    assert not destination.exists()


def test_duplicate_member_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "system.zip"
    destination = tmp_path / "active" / "v54"
    _write_valid_system_zip(archive)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "a") as zf:
            zf.writestr("run.py", "print('duplicate')\n")

    with pytest.raises(bootstrap.BootstrapError) as exc_info:
        bootstrap.bootstrap_system_zip(
            zip_path=archive,
            destination=destination,
            expected_sha256=_sha256(archive),
            expected_size_bytes=archive.stat().st_size,
        )

    assert exc_info.value.code == "duplicate_zip_member"
    assert not destination.exists()


def test_standalone_bootstrap_does_not_call_extractall() -> None:
    source = (ROOT / "CHATGPT_BOOTSTRAP.py").read_text(encoding="utf-8")
    assert ".extractall(" not in source


def test_chatgpt_loader_supports_transport_truth_and_single_zip_recovery() -> None:
    loader = (ROOT / "docs" / "runtime" / "CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(
        encoding="utf-8"
    )

    assert len(loader) <= 5000
    assert "TransportTimeoutError" in loader
    assert "--expected-sha256" in loader
    assert "--expected-size-bytes" in loader
    assert "Lokalny sidecar nie jest wymagany" in loader
    assert "materialized_operator_ready" in loader
    assert "run.py host-preflight --json" in loader


def test_chatgpt_runbook_does_not_blame_zip_for_host_transport_failure() -> None:
    runbook = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")

    assert "TransportTimeoutError" in runbook
    assert "nie jest dowodem uszkodzenia ZIP-a" in runbook
    assert "--expected-sha256" in runbook
    assert "--expected-size-bytes" in runbook
    assert "kod Jaźni nie może naprawić samej awarii platformy" in runbook
