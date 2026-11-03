"""Windows ownership adapters for the canonical supervisor; no daemon lifecycle.

Importable on other platforms. Native APIs are loaded only for an explicit SCM
invocation. Plans never install, start or stop an OS service or scheduled task.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess
import threading
from typing import Any, Protocol
import xml.etree.ElementTree as ET


STOPPED, START_PENDING, STOP_PENDING, RUNNING = 1, 2, 3, 4
CONTROL_STOP, CONTROL_INTERROGATE, CONTROL_SHUTDOWN = 1, 4, 5
ACCEPT_STOP_SHUTDOWN = 0x00000001 | 0x00000004
ERROR_CALL_NOT_IMPLEMENTED = 120
ERROR_SERVICE_SPECIFIC_ERROR = 1066
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def supervisor_service_name(root: Path) -> str:
    identity = os.path.normcase(str(root.expanduser().resolve()))
    return "JaznSupervisor-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def windows_supervisor_plan(root: Path, command: list[str]) -> dict[str, Any]:
    """Generate reviewable OS configuration without touching the machine."""
    name = supervisor_service_name(root)
    service_command = [*command, "--windows-service"]
    # Always quote the executable in ImagePath, including paths without spaces.
    # list2cmdline alone leaves a space-free executable unquoted.
    executable = command[0]
    if '"' in executable or any(c in executable for c in "\0\r\n"):
        raise ValueError("Invalid Windows supervisor executable")
    image_path = '"' + executable + '" ' + subprocess.list2cmdline(service_command[1:])

    def element(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
        child = ET.SubElement(parent, tag, attrs)
        child.text = text
        return child

    task = ET.Element("Task", {"xmlns": TASK_NAMESPACE, "version": "1.3"})
    registration = element(task, "RegistrationInfo")
    element(registration, "Description", "Jaźń supervisor for " + str(root))
    boot = element(element(task, "Triggers"), "BootTrigger")
    element(boot, "Enabled", "true")
    principal = element(element(task, "Principals"), "Principal", id="Supervisor")
    # Built-in LocalService, never the interactive user's token or a password.
    # TASK_LOGON_SERVICE_ACCOUNT is supplied by the registration API; the XML
    # schema does not accept the string ServiceAccount in LogonType.
    element(principal, "UserId", "S-1-5-19")
    element(principal, "RunLevel", "LeastPrivilege")
    settings = element(task, "Settings")
    for key, value in (
        ("MultipleInstancesPolicy", "IgnoreNew"),
        ("DisallowStartIfOnBatteries", "false"),
        ("StopIfGoingOnBatteries", "false"),
        ("AllowHardTerminate", "false"),
        ("StartWhenAvailable", "true"),
        ("RunOnlyIfNetworkAvailable", "false"),
        ("Enabled", "true"),
        ("ExecutionTimeLimit", "PT0S"),
    ):
        element(settings, key, value)
    restart = element(settings, "RestartOnFailure")
    element(restart, "Interval", "PT1M")
    element(restart, "Count", "3")
    action = element(element(task, "Actions", Context="Supervisor"), "Exec")
    element(action, "Command", executable)
    element(action, "Arguments", subprocess.list2cmdline(command[1:]))
    element(action, "WorkingDirectory", str(root))
    xml = ET.tostring(task, encoding="unicode", xml_declaration=False)
    return {
        "service_name": name,
        "service_command": service_command,
        "image_path": image_path,
        "create_service_argv": [
            "sc.exe", "create", name, "type=", "own", "start=", "delayed-auto",
            "binPath=", image_path, "obj=", r"NT AUTHORITY\LocalService",
            "DisplayName=", "Jaźń supervisor (" + name + ")",
        ],
        "query_service_argv": ["sc.exe", "queryex", name],
        "task_name": name,
        "task_xml": xml,
        "task_registration_logon_type": 5,
        "account": r"NT AUTHORITY\LocalService",
        "installation_performed": False,
        "boot_acceptance": "NOT_RUN",
        "prerequisites": [
            "Operator approval before registration, start, stop or removal",
            "Choose one ownership mechanism: SCM service OR scheduled task",
            "Absolute, verified Python with activation core dependencies already ready",
            "LocalService read/execute permissions on SYSTEM and Python",
            "Explicit LocalService write permissions on the intended runtime workspace",
            "Review canonical ROOT configuration and MEMORY selection under LocalService",
        ],
    }


@dataclass(frozen=True)
class ServiceStatus:
    state: int
    checkpoint: int = 0
    wait_hint_ms: int = 0
    exit_code: int = 0


class ServiceAPI(Protocol):
    def dispatch(self, name: str, main: Callable[[], None]) -> None: ...
    def register(self, name: str, handler: Callable[[int], int]) -> None: ...
    def report(self, status: ServiceStatus) -> None: ...


class _NativeServiceAPI:
    """Typed Win32 ABI and retained callbacks for a single own-process service."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Windows Service Control Manager is unavailable on this platform")
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.dll = ctypes.WinDLL("advapi32", use_last_error=True)
        self.handler_type = ctypes.WINFUNCTYPE(
            wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID
        )
        self.main_type = ctypes.WINFUNCTYPE(None, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR))

        class NativeStatus(ctypes.Structure):
            _fields_ = [(field, wintypes.DWORD) for field in (
                "service_type", "state", "controls", "win32_exit", "service_exit", "checkpoint", "wait_hint"
            )]

        class TableEntry(ctypes.Structure):
            _fields_ = [("name", wintypes.LPWSTR), ("main", self.main_type)]

        self.status_type = NativeStatus
        self.entry_type = TableEntry
        self.dll.StartServiceCtrlDispatcherW.argtypes = [ctypes.POINTER(TableEntry)]
        self.dll.StartServiceCtrlDispatcherW.restype = wintypes.BOOL
        self.dll.RegisterServiceCtrlHandlerExW.argtypes = [wintypes.LPCWSTR, self.handler_type, wintypes.LPVOID]
        self.dll.RegisterServiceCtrlHandlerExW.restype = wintypes.HANDLE
        self.dll.SetServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(NativeStatus)]
        self.dll.SetServiceStatus.restype = wintypes.BOOL
        self.handle: Any = None
        self.callbacks: list[Any] = []

    def dispatch(self, name: str, main: Callable[[], None]) -> None:
        callback = self.main_type(lambda _argc, _argv: main())
        self.callbacks.append(callback)
        table = (self.entry_type * 2)()
        table[0].name = name
        table[0].main = callback
        # The zero-initialized second entry terminates the SCM dispatch table.
        if not self.dll.StartServiceCtrlDispatcherW(table):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def register(self, name: str, handler: Callable[[int], int]) -> None:
        callback = self.handler_type(lambda code, _kind, _data, _ctx: handler(code))
        self.callbacks.append(callback)
        self.handle = self.dll.RegisterServiceCtrlHandlerExW(name, callback, None)
        if not self.handle:
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def report(self, status: ServiceStatus) -> None:
        native = self.status_type(
            0x10, status.state, ACCEPT_STOP_SHUTDOWN if status.state == RUNNING else 0,
            ERROR_SERVICE_SPECIFIC_ERROR if status.exit_code else 0, status.exit_code,
            status.checkpoint, status.wait_hint_ms,
        )
        if not self.dll.SetServiceStatus(self.handle, self.ctypes.byref(native)):
            raise self.ctypes.WinError(self.ctypes.get_last_error())


class _ServiceHost:
    """SCM status/stop adapter; all runtime decisions stay in run_supervisor."""

    def __init__(self, api: ServiceAPI, name: str, work: Callable[[threading.Event], int]):
        self.api, self.name, self.work = api, name, work
        self.stop = threading.Event()
        self.finished = threading.Event()
        self.lock = threading.RLock()
        self.status = ServiceStatus(START_PENDING, checkpoint=1, wait_hint_ms=30_000)
        self.result = 0
        self.error: BaseException | None = None

    def report(self, status: ServiceStatus) -> None:
        with self.lock:
            if self.status.state == STOPPED:
                return
            self.api.report(status)
            self.status = status

    def control(self, code: int) -> int:
        # ctypes callbacks must never let a Python exception disappear at the
        # native boundary. Record failure and terminate the supervisor orderly.
        try:
            with self.lock:
                if code in (CONTROL_STOP, CONTROL_SHUTDOWN):
                    self.stop.set()
                    self.report(ServiceStatus(STOP_PENDING, self.status.checkpoint + 1, 30_000))
                elif code == CONTROL_INTERROGATE:
                    if self.status.state != STOPPED:
                        self.api.report(self.status)
                else:
                    return ERROR_CALL_NOT_IMPLEMENTED
            return 0
        except BaseException as exc:
            self.error = exc
            self.stop.set()
            return 1

    def _work(self) -> None:
        try:
            self.result = int(self.work(self.stop))
        except BaseException as exc:
            self.error = exc
            self.result = 1
        finally:
            self.finished.set()

    def main(self) -> None:
        registered = False
        worker: threading.Thread | None = None
        try:
            self.api.register(self.name, self.control)
            registered = True
            self.report(self.status)
            worker = threading.Thread(target=self._work, name="jazn-supervisor-service")
            # RUNNING means this service host can accept stop controls. Daemon
            # liveness/readiness remain separate canonical observations.
            self.report(ServiceStatus(RUNNING))
            worker.start()
            while not self.finished.wait(1.0):
                if self.stop.is_set():
                    self.report(ServiceStatus(STOP_PENDING, self.status.checkpoint + 1, 30_000))
        except BaseException as exc:
            self.error = exc
            self.result = 1
        finally:
            self.stop.set()
            if worker is not None and worker.ident is not None:
                # Never announce STOPPED while the canonical supervisor still
                # runs. No terminate(), daemon stop, replay, or local fallback.
                worker.join()
            if registered:
                try:
                    self.report(ServiceStatus(STOPPED, exit_code=self.result or int(self.error is not None)))
                except BaseException as exc:
                    self.error = exc
                    self.result = 1


def run_windows_supervisor_service(root: Path, work: Callable[[threading.Event], int]) -> int:
    """Enter the actual SCM dispatcher; console invocation fails with WinError 1063."""
    host = _ServiceHost(_NativeServiceAPI(), supervisor_service_name(root), work)
    host.api.dispatch(host.name, host.main)
    if host.error is not None:
        raise RuntimeError("Windows supervisor service failed") from host.error
    return host.result
