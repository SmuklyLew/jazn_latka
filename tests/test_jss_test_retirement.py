"""Obsolete tests only retire after explicit review, replacement and green CI."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools.jazn_tests_studio import retirement


@pytest.fixture
def source(tmp_path, monkeypatch):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "archive").mkdir()
    old = tmp_path / "tests/test_old.py"
    old.write_bytes(b"def test_first(): assert True\r\ndef test_second(): assert True\r\n")
    (tmp_path / "tests/test_replacement.py").write_text("def test_current(): assert True\n")
    catalog = {
        "tests/test_old.py::test_first": {"status": "current"},
        "tests/test_old.py::test_second": {"status": "current"},
        "tests/test_replacement.py::test_current": {"status": "current"},
    }
    reviews = {
        name: {"status": "obsolete", "replacement_nodeid": "tests/test_replacement.py::test_current"}
        for name in catalog if name.startswith("tests/test_old.py::")
    }
    monkeypatch.setattr(retirement, "contracts", lambda _root: catalog)
    monkeypatch.setattr(retirement, "load_reviews", lambda _root: {"reviews": reviews})
    monkeypatch.setattr(retirement, "effective_contract",
                        lambda _root, name: {"status": catalog[name]["status"]})
    return tmp_path, old, catalog, reviews


def test_retirement_preview_requires_all_reviews_and_verified_replacements(source):
    root, old, catalog, reviews = source
    original = old.read_bytes()
    report = retirement.preview(root, "tests/test_old.py")
    assert report["status"] == "REVIEW_READY"
    assert report["contracts_in_file"] == 2
    assert report["reviewed_with_current_replacements"] == 2
    assert report["full_release_gate"] == "NOT_VERIFIED"
    assert report["source_sha256"] == sha256(original).hexdigest()
    assert old.read_bytes() == original

    reviews["tests/test_old.py::test_first"]["status"] = "current"
    assert retirement.preview(root, "tests/test_old.py")["status"] == "BLOCKED"
    reviews["tests/test_old.py::test_first"]["status"] = "obsolete"
    catalog["tests/test_replacement.py::test_current"]["status"] = "obsolete"
    assert retirement.preview(root, "tests/test_old.py")["status"] == "BLOCKED"


@pytest.mark.parametrize("invalid", [
    "../tests/test_old.py", "tests/archive/test_old.py",
    "memory/test_old.py", "tests/../test_old.py", "/tests/test_old.py",
    "tests/test_old.json",
])
def test_retirement_refuses_unsafe_source_paths(source, invalid):
    root, old, *_ = source
    with pytest.raises(ValueError):
        retirement.preview(root, invalid)
    assert old.is_file()


def test_retirement_requires_confirmation_exact_digest_branch_and_green_checks(source, monkeypatch):
    root, old, *_ = source
    digest = sha256(old.read_bytes()).hexdigest()
    head = "a" * 40
    with pytest.raises(ValueError, match="ARCHIWIZUJ"):
        retirement.archive_file(root, "tests/test_old.py", expected_sha256=digest,
                                expected_head=head, confirmation="yes")
    with pytest.raises(ValueError, match="Source file changed"):
        retirement.archive_file(root, "tests/test_old.py", expected_sha256="0" * 64,
                                expected_head=head, confirmation="ARCHIWIZUJ")
    monkeypatch.setattr(retirement, "_git", lambda _root, *args:
                        "" if args[0] == "status" else "master" if args[0] == "branch" else head)
    with pytest.raises(ValueError, match="feature branch"):
        retirement.archive_file(root, "tests/test_old.py", expected_sha256=digest,
                                expected_head=head, confirmation="ARCHIWIZUJ")
    monkeypatch.setattr(retirement, "_git", lambda _root, *args:
                        "" if args[0] == "status" else "fix/retirement" if args[0] == "branch" else head)
    monkeypatch.setattr(retirement, "_green_checks", lambda _head: (_ for _ in ()).throw(
        ValueError("CI unavailable")))
    with pytest.raises(ValueError, match="CI unavailable"):
        retirement.archive_file(root, "tests/test_old.py", expected_sha256=digest,
                                expected_head=head, confirmation="ARCHIWIZUJ")
    assert old.is_file()
    assert list((root / "tests/archive").rglob("test_old.py")) == []


def test_retirement_archives_byte_exact_original_and_leaves_new_ci_pending(source, monkeypatch):
    root, old, *_ = source
    original = old.read_bytes()
    digest = sha256(original).hexdigest()
    head = "a" * 40
    monkeypatch.setattr(retirement, "_git", lambda _root, *args:
                        "" if args[0] == "status" else "fix/retirement" if args[0] == "branch" else head)
    monkeypatch.setattr(retirement, "_green_checks", lambda _head: [
        "manifest_sync", "test (ubuntu-latest, 3.12)", "test (windows-latest, 3.12)"
    ])
    result = retirement.archive_file(root, "tests/test_old.py", expected_sha256=digest,
                                     expected_head=head, confirmation="ARCHIWIZUJ")
    archived = root / result["archived_path"]
    assert archived.read_bytes() == original
    assert not old.exists()
    assert archived.with_suffix(".retirement.json").is_file()
    payload = json.loads(archived.with_suffix(".retirement.json").read_text(encoding="utf-8"))
    assert payload["source_sha256"] == digest
    assert payload["source_head_sha"] == head
    assert payload["post_archival_ci"] == "PENDING"
    assert payload["full_tpa_acceptance"] == "NOT_IMPLIED"
    with pytest.raises(ValueError):
        retirement.archive_file(root, "tests/test_old.py", expected_sha256=digest,
                                expected_head=head, confirmation="ARCHIWIZUJ")
