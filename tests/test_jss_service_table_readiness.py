"""The service table caption must require the same evidence as its indicator."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget, QTableWidgetItem
from tools.jazn_run_studio.view_services import ServiceViewMixin


def runtime_sample():
    return dict(active_state="active_trusted", root_matches=True,
                version_matches=True, endpoint_reachable=True,
                process_identity_confirmed=True, endpoint_identity_matches=True,
                heartbeat_fresh=True, conversation_ready=True)


def caption(evidence):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    table = QTableWidget(1, 6)
    for column in (0, 2, 3, 4):
        table.setItem(0, column, QTableWidgetItem())
    host = SimpleNamespace(
        core=SimpleNamespace(settings=SimpleNamespace(daemon_url="http://127.0.0.1:54321", mcp_port="0"),
                             lock=nullcontext(), jobs={}),
        service_rows={"runtime": 0}, services_table=table,
        workspace=SimpleNamespace(observations={"runtime": evidence}),
        statuses={"runtime": QLabel()}, models_summary=QLabel(),
    )
    ServiceViewMixin.refresh_service_table(host)
    readiness = table.item(0, 4)
    assert readiness is not None
    return readiness.text()


@pytest.mark.parametrize("key", ["root_matches", "version_matches", "endpoint_reachable",
                                "process_identity_confirmed", "endpoint_identity_matches",
                                "heartbeat_fresh", "conversation_ready"])
@pytest.mark.parametrize("value", [False, None])
def test_table_does_not_confirm_incomplete_identity(key, value):
    assert caption({**runtime_sample(), key: value}) == "niezweryfikowana"


@pytest.mark.parametrize("state", ["inactive", "stopped", "dead", "unknown", None])
def test_table_does_not_confirm_inactive_state(state):
    assert caption({**runtime_sample(), "active_state": state}) == "niezweryfikowana"


def test_table_confirms_complete_runtime_identity():
    assert caption(runtime_sample()) == "potwierdzona"
