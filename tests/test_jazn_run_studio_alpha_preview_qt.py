"""Qt operation preview is bound to current values and invalidated by edits."""
import pytest
pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window
from tools.jazn_run_studio.studio_worker import preview_fingerprint


def test_preview_is_invalidated_on_field_changes(window):
    key = str(window.studio_choice.currentData())
    command = {"path": ["save"], "description": "test", "fields": [
        {"id": "0", "dest": "target", "required": True, "nargs": None,
         "flag": False, "choices": [], "append": False, "help": "Target", "depth": 1}]}
    window.core.emit("helper:schema:" + key, "helper", [command])
    window.poll()
    spec = window.operation_payload()
    window.core.emit("helper:preview:" + key, "helper", {
        "schema": "jazn_studio_command_preview/v1", "path": ["save"],
        "fingerprint": preview_fingerprint(spec), "argument_count": 1,
        "requires_confirmation": True, "execution_performed": False})
    window.poll()
    assert window.preview_approved == preview_fingerprint(spec)
    window.operation_widgets["0"].setText("new path")
    assert not window.preview_approved
