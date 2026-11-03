from __future__ import annotations

from pathlib import Path
import os
import subprocess
import threading
import xml.etree.ElementTree as ET

import pytest

from latka_jazn.core import windows_supervisor as windows


class RecordingAPI:
    def __init__(self) -> None:
        self.reports: list[windows.ServiceStatus] = []
        self.handler = None

    def dispatch(self, name, main):
        main()

    def register(self, name, handler):
        self.handler = handler

    def report(self, status):
        self.reports.append(status)


def test_plan_binds_one_root_to_a_noninteractive_boot_task_and_native_service(tmp_path: Path) -> None:
    root = tmp_path / "Jaźń & operator's SYSTEM"
    root.mkdir()
    python = str(tmp_path / "Python with spaces" / "python.exe")
    command = [python, "-X", "utf8", str(root / "run.py"), "supervisor-run", "--root", str(root)]
    plan = windows.windows_supervisor_plan(root, command)
    assert plan["installation_performed"] is False
    assert plan["boot_acceptance"] == "NOT_RUN"
    assert plan["service_name"] != windows.supervisor_service_name(tmp_path / "other-root")
    assert plan["service_command"] == command + ["--windows-service"]
    assert plan["create_service_argv"][3:7] == ["type=", "own", "start=", "delayed-auto"]
    assert plan["image_path"].startswith('"' + python + '" ')
    assert plan["create_service_argv"][8] == plan["image_path"]
    document = ET.fromstring(plan["task_xml"])
    namespace = {"t": windows.TASK_NAMESPACE}
    assert document.findtext("t:Triggers/t:BootTrigger/t:Enabled", namespaces=namespace) == "true"
    assert document.findtext("t:Principals/t:Principal/t:UserId", namespaces=namespace) == "S-1-5-19"
    assert document.find("t:Principals/t:Principal/t:LogonType", namespace) is None
    assert plan["task_registration_logon_type"] == 5
    for key, expected in {
        "ExecutionTimeLimit": "PT0S", "MultipleInstancesPolicy": "IgnoreNew",
        "StartWhenAvailable": "true", "DisallowStartIfOnBatteries": "false",
        "StopIfGoingOnBatteries": "false", "AllowHardTerminate": "false",
        "RestartOnFailure/Interval": "PT1M", "RestartOnFailure/Count": "3",
    }.items():
        xpath = "t:Settings/" + "/".join("t:" + item for item in key.split("/"))
        assert document.findtext(xpath, namespaces=namespace) == expected
    assert document.findtext("t:Actions/t:Exec/t:Command", namespaces=namespace) == python
    assert document.findtext("t:Actions/t:Exec/t:WorkingDirectory", namespaces=namespace) == str(root)
    assert document.findtext("t:Actions/t:Exec/t:Arguments", namespaces=namespace) == subprocess.list2cmdline(command[1:])
    assert list(root.iterdir()) == []


def test_service_control_stops_only_the_supervisor_and_waits_for_its_completion() -> None:
    api = RecordingAPI()
    entered, release = threading.Event(), threading.Event()
    observed: list[bool] = []

    def work(event):
        entered.set()
        observed.append(event.wait(5))
        assert release.wait(5)
        return 0

    host = windows._ServiceHost(api, "test-owned-service", work)
    thread = threading.Thread(target=host.main)
    thread.start()
    try:
        assert entered.wait(5)
        assert host.control(windows.CONTROL_STOP) == 0
        assert api.reports[-1].state == windows.STOP_PENDING
        assert thread.is_alive()
        assert all(row.state != windows.STOPPED for row in api.reports)
        assert host.control(windows.CONTROL_INTERROGATE) == 0
        assert host.control(999) == windows.ERROR_CALL_NOT_IMPLEMENTED
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert observed == [True]
    assert api.reports[-1] == windows.ServiceStatus(windows.STOPPED)
    assert host.error is None
    count = len(api.reports)
    host.control(windows.CONTROL_INTERROGATE)
    host.control(windows.CONTROL_SHUTDOWN)
    assert len(api.reports) == count


@pytest.mark.parametrize("code", [0, 41])
def test_service_preserves_canonical_supervisor_return_code(code: int) -> None:
    api = RecordingAPI()
    host = windows._ServiceHost(api, "test", lambda event: code)
    api.dispatch("test", host.main)
    assert host.result == code
    assert api.reports[-1] == windows.ServiceStatus(windows.STOPPED, exit_code=code)


def test_worker_failure_is_reported_to_scm_without_becoming_success() -> None:
    def work(event):
        raise ValueError("synthetic supervisor failure")

    api = RecordingAPI()
    host = windows._ServiceHost(api, "test", work)
    host.main()
    assert isinstance(host.error, ValueError)
    assert host.result == 1
    assert api.reports[-1] == windows.ServiceStatus(windows.STOPPED, exit_code=1)


def test_registration_failure_never_starts_the_canonical_supervisor() -> None:
    class RefusedAPI(RecordingAPI):
        def register(self, name, handler):
            raise PermissionError("synthetic registration refusal")

    calls = []
    host = windows._ServiceHost(RefusedAPI(), "test", lambda event: calls.append(event) or 0)
    host.main()
    assert calls == []
    assert host.result == 1
    assert isinstance(host.error, PermissionError)


@pytest.mark.skipif(os.name != "nt", reason="native Windows SCM ABI")
def test_real_scm_dispatcher_refuses_a_console_process_without_fallback(tmp_path: Path) -> None:
    calls = []
    with pytest.raises(OSError) as raised:
        windows.run_windows_supervisor_service(tmp_path, lambda event: calls.append(event) or 0)
    assert getattr(raised.value, "winerror", None) == 1063
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_canonical_cli_routes_explicit_service_flag_without_plain_supervisor_fallback(tmp_path, monkeypatch, capsys):
    from latka_jazn import cli
    from latka_jazn.core import runtime_supervisor

    seen = []

    def service(root, work):
        seen.append(root)
        return work(threading.Event())

    monkeypatch.setattr(windows, "run_windows_supervisor_service", service)
    monkeypatch.setattr(runtime_supervisor, "run_supervisor",
                        lambda root, **kwargs: 41 if isinstance(kwargs.get("stop_event"), threading.Event) else 99)
    assert cli.main(["supervisor-run", "--root", str(tmp_path), "--windows-service"]) == 41
    assert seen == [tmp_path]

    def refused(root, work):
        raise OSError("synthetic SCM refusal")

    monkeypatch.setattr(windows, "run_windows_supervisor_service", refused)
    assert cli.main(["supervisor-run", "--root", str(tmp_path), "--windows-service"]) == 2
    assert '"console_fallback_performed": false' in capsys.readouterr().out
