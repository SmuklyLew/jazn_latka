"""Controller completion clears raw output; public events must remain useful evidence."""
import queue
from types import SimpleNamespace
from typing import cast
import pytest
from tools.jazn_run_studio.core import Controller, Redactor
from tools.jazn_run_studio.tpa_live import capture_action


@pytest.mark.parametrize("success", [True, False])
def test_action_collects_public_logs_including_failure_before_raw_capture_is_cleared(success, capsys):
    events = queue.Queue()
    events.put(("start", "log", '{"reason":"synthetic start refusal","secret":"synthetic-private"}'))
    events.put(("start", "evidence", {"root_matches": True}))
    class CompletedJob:
        key = "start"
        state = "succeeded" if success else "failed"
        returncode = 0 if success else 1
        error = None if success else "process_exit:1"
        done = SimpleNamespace(wait=lambda timeout: True)
        @property
        def output(self):
            raise AssertionError("Raw capture is private and has already been cleared")
    core = cast(Controller, SimpleNamespace(events=events, critical_events=queue.Queue(), redactor=Redactor({}),
                           start_action=lambda key: CompletedJob()))
    records = []
    if success:
        assert capture_action(core, "start", lambda: None, records)["root_matches"]
    else:
        with pytest.raises(ValueError, match="synthetic start refusal"):
            capture_action(core, "start", lambda: None, records)
    assert records[0]["observed"]["reason"] == "synthetic start refusal"
    assert records[0]["observed"]["secret"] == "[UKRYTO]"
    assert "synthetic-private" not in capsys.readouterr().out
