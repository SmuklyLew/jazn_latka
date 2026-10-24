"""Every canonical Studio receives a distinct operator-only acceptance gate."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.jazn_run_studio import local_acceptance as acceptance


def test_all_twelve_studios_have_unique_nonexecuting_acceptance_cases() -> None:
    checks = acceptance.STUDIO_CATALOG
    assert len(checks) == 12
    ids = [t["id"] for t in checks]
    assert len(set(ids)) == len(ids)
    assert all(x.startswith("studio-") for x in ids)
    assert {"studio-version-rebuild", "studio-chat-import", "studio-memory-restore"} <= set(ids)
    assert all(t["expected"] and t["steps"] and "Qt" in t["expected"] for t in checks)


def test_one_studio_pass_does_not_mark_others_passed_or_automatically_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    (root / "latka_jazn").mkdir()
    (root / "latka_jazn/version.py").write_text(
        'PACKAGE_VERSION="1.2.3"\nDISTRIBUTION_VERSION=PACKAGE_VERSION\n'
        'PACKAGE_RELEASE_NAME="acceptance"\n', encoding="utf-8"
    )
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    data, digest = acceptance.load(root)
    assert all(acceptance.outcome(data, x["id"], acceptance.scope_version(root)) is None
               for x in acceptance.STUDIO_CATALOG)
    digest = acceptance.save_result(
        root, digest, "studio-python-runtime", "passed",
        "Ręczny wynik lokalny; wszystkie przypadki zaliczone", "raport-operatora-01"
    )
    data, _ = acceptance.load(root)
    accepted = acceptance.outcome(data, "studio-python-runtime", acceptance.scope_version(root))
    assert accepted is not None and accepted["status"] == "passed"
    assert not accepted["archived"]
    assert all(acceptance.outcome(data, x["id"], acceptance.scope_version(root)) is None
               for x in acceptance.STUDIO_CATALOG if x["id"] != "studio-python-runtime")
    assert data["archive"] == []
    acceptance.archive_result(root, digest, "studio-python-runtime")
    history, _ = acceptance.load(root)
    assert len(history["archive"]) == 1
