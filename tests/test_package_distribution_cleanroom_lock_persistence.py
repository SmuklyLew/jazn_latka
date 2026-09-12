from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "package-distribution-cleanroom.yml"


def _persist_step() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: Persist native locks then synchronize canonical release metadata")
    return text[start:]


def test_persist_release_locks_stages_untracked_locks_before_diffing() -> None:
    step = _persist_step()
    stage_index = step.index('git add "$destination"')
    cached_diff_index = step.index('git diff --cached --quiet -- "$destination"')
    metadata_index = step.index("python -X utf8 -m latka_jazn.tools.release_metadata_sync")

    assert stage_index < cached_diff_index < metadata_index
    assert 'if ! git diff --quiet -- "$destination"; then' not in step


def test_persist_release_locks_checks_clean_tree_before_metadata_and_push() -> None:
    step = _persist_step()
    metadata_guard_index = step.index(
        "Working tree is dirty before release metadata synchronization:"
    )
    metadata_index = step.index("python -X utf8 -m latka_jazn.tools.release_metadata_sync")
    push_guard_index = step.index("Working tree is dirty before release push:")
    push_index = step.index('git push origin "HEAD:${GITHUB_REF#refs/heads/}"')

    assert step.count("git status --porcelain --untracked-files=all") >= 2
    assert metadata_guard_index < metadata_index < push_guard_index < push_index
