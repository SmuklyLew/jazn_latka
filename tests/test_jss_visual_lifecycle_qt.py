"""Qt teardown regression: queued reflow may not outlive its workbench."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from tests.test_jazn_run_studio_layout import window


def test_close_cancels_pending_reflow_and_detaches_global_event_filter(window) -> None:
    visual = window.visual_system
    window.resize(940, 640)
    assert not visual._closed
    # Close before a pending resize event is processed; this path crashed
    # with an unowned QTimer.singleShot callback during pytest teardown.
    assert window.close()
    assert visual._closed
    assert not visual._reflow_timer.isActive()
    visual.reflow()  # deliberate late call must remain a no-op
    QTest.qWait(30)
    assert not visual._reflow_timer.isActive()
    visual.shutdown()  # idempotent, including fixture cleanup
