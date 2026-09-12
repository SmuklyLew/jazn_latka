from __future__ import annotations

import json
import sys
from typing import Any

_MARKER = "JAZN_TEST_STUDIO_EVENT "
_reports: dict[str, dict[str, Any]] = {}


def _emit(payload: dict[str, Any]) -> None:
    stream = sys.__stdout__ or sys.stdout
    stream.write("\n" + _MARKER + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    stream.flush()


def pytest_collection_finish(session) -> None:
    _emit({"type": "collection", "total": len(session.items)})


def pytest_runtest_logstart(nodeid: str, location) -> None:
    _emit({"type": "start", "nodeid": nodeid})


def pytest_runtest_logreport(report) -> None:
    _reports.setdefault(report.nodeid, {})[report.when] = report


def pytest_runtest_logfinish(nodeid: str, location) -> None:
    reports = _reports.pop(nodeid, {})
    setup = reports.get("setup")
    call = reports.get("call")
    teardown = reports.get("teardown")

    status = "ERROR"
    if (setup is not None and setup.failed) or (teardown is not None and teardown.failed):
        status = "ERROR"
    elif call is not None:
        wasxfail = getattr(call, "wasxfail", None)
        if call.skipped:
            status = "XFAIL" if wasxfail else "SKIPPED"
        elif call.passed:
            status = "XPASS" if wasxfail else "PASSED"
        elif call.failed:
            status = "FAILED"
    elif setup is not None and setup.skipped:
        status = "SKIPPED"

    duration = 0.0
    for report in reports.values():
        duration += float(getattr(report, "duration", 0.0) or 0.0)
    _emit({"type": "result", "nodeid": nodeid, "status": status, "duration": round(duration, 6)})


def pytest_sessionfinish(session, exitstatus: int) -> None:
    _emit({"type": "session_finish", "exitstatus": int(exitstatus)})
