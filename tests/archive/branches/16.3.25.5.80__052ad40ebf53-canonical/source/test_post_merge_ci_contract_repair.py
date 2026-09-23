from __future__ import annotations

from latka_jazn.tools.current_line_archive_audit import _is_active_path


def test_only_to_check_is_non_authoritative_for_active_line_audit() -> None:
    assert _is_active_path(
        "docs/plans/only_to_check/2026-09-07-pr231-pre-memory-affect-rewrite/old.md"
    ) is False
    assert _is_active_path("docs/plans/CURRENT_STEP.md") is True
    assert _is_active_path("docs/project/current-contract.md") is True
