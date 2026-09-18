from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "package-distribution-cleanroom.yml"


def test_cleanroom_accepts_release_ready_doctor_before_live_daemon() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'test "$doctor_rc" -eq 0' in text
    assert 'assert p.get("ok") is True' in text
    assert 'assert p.get("installation_ok") is True' in text
    assert 'assert p.get("activation_ready") is True' in text
    assert 'assert p.get("release_ready") is True' in text
    assert 'assert p.get("live_runtime_ready") is False' in text
