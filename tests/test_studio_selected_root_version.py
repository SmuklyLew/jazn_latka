"""An operator client binds version identity to its selected SYSTEM, not itself."""
import pytest

from latka_jazn.version import PACKAGE_VERSION_FULL
from tools.jazn_run_studio.core import daemon_evidence


def root_version(root, version):
    (root / "latka_jazn").mkdir(exist_ok=True)
    (root / "latka_jazn/version.py").write_text(
        f"PACKAGE_VERSION={version!r}\nraise AssertionError('Version inspection must not execute source')\n",
        encoding="utf-8")


def status(root, system_version, daemon_version):
    return {"resolved_active_root": str(root), "runtime_version": system_version,
            "daemon": {"ping": {"runtime_version": daemon_version}}}


def test_external_system_version_can_match_without_matching_operator_package(tmp_path):
    selected = "99.88.77-external-system-fixture"
    assert selected != PACKAGE_VERSION_FULL
    root_version(tmp_path, selected)
    evidence = daemon_evidence(status(tmp_path, selected, selected), expected_root=tmp_path)
    assert evidence["root_matches"] is True
    assert evidence["version_matches"] is True
    assert evidence["expected_system_version"] == selected
    assert evidence["accepted_visible_turn"] is False


@pytest.mark.parametrize("mismatch", ["system", "daemon"])
def test_live_identity_must_match_the_selected_source_version(tmp_path, mismatch):
    selected = "99.88.77-external-system-fixture"
    root_version(tmp_path, selected)
    evidence = daemon_evidence(status(tmp_path,
        PACKAGE_VERSION_FULL if mismatch == "system" else selected,
        PACKAGE_VERSION_FULL if mismatch == "daemon" else selected), expected_root=tmp_path)
    assert evidence["version_matches"] is False


@pytest.mark.parametrize("source", [None, "", "PACKAGE_VERSION = choose_version()", "def invalid(:"])
def test_unreadable_or_nonliteral_source_cannot_fall_back_to_operator_identity(tmp_path, source):
    if source is not None:
        (tmp_path / "latka_jazn").mkdir()
        (tmp_path / "latka_jazn/version.py").write_text(source, encoding="utf-8")
    evidence = daemon_evidence(status(tmp_path, PACKAGE_VERSION_FULL, PACKAGE_VERSION_FULL), expected_root=tmp_path)
    assert evidence["expected_system_version"] is None
    assert evidence["version_matches"] is False


def test_a_changed_selected_version_invalidates_an_older_endpoint(tmp_path):
    root_version(tmp_path, "99.88.77-before")
    observed = status(tmp_path, "99.88.77-before", "99.88.77-before")
    assert daemon_evidence(observed, expected_root=tmp_path)["version_matches"] is True
    root_version(tmp_path, "99.88.78-after")
    evidence = daemon_evidence(observed, expected_root=tmp_path)
    assert evidence["expected_system_version"] == "99.88.78-after"
    assert evidence["version_matches"] is False
