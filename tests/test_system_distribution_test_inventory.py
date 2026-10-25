"""Every active Test Studio contract must point to a distributable test file."""
from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.tools.package_integrity import path_is_forbidden


def test_studio_contract_sources_are_present_and_allowed_in_system_package() -> None:
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "tools/jazn_tests_studio/test_contracts.json").read_text(encoding="utf-8"))
    paths = {entry["path"] for entry in catalog["contracts"].values()}
    assert paths
    for relative in sorted(paths):
        assert not path_is_forbidden(relative), f"Test Studio source excluded from SYSTEM: {relative}"
        assert (root / relative).is_file(), f"Test Studio contract source missing: {relative}"
