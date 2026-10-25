#!/usr/bin/env python3
"""Jaźń — Studio Startu: local operator process console, never the Jaźń runtime.

Standalone stdlib Python 3.11+ tool. Two UIs share the same conservative core.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STUDIO_VERSION = "0.3.0"

def mcp_request_meta() -> dict:
    """Required 2026-07-28 per-request metadata; no client credentials."""
    return {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {
            "name": "jazn-start-studio-probe", "version": STUDIO_VERSION,
        },
    }

OLLAMA_URL = "http://127.0.0.1:11434"
DAEMON_PORT = 8787
MAX_LOG_LINES = 2500
MAX_HTTP_BYTES = 256 * 1024
WINDOWS = os.name == "nt"
NEW_PROCESS_GROUP = 0x00000200  # Windows CREATE_NEW_PROCESS_GROUP

# Never accept arbitrary shell snippets: every command has an argv contract.
@dataclass(frozen=True)
class Task:
    key: str
    group: str
    title: str
    operation: str
    args: tuple[str, ...] = ()


TASKS = (
    Task("jazn_status", "Jaźń", "Status / tożsamość daemona", "jazn", ("status", "--json")),
    Task("jazn_preflight", "Jaźń", "Host preflight", "jazn", ("host-preflight", "--json")),
    Task("jazn_start", "Jaźń", "Start daemona (nie restart)", "jazn_start", ("start",)),
    Task("jazn_adapter", "Jaźń", "Status adaptera językowego", "jazn", ("--model-adapter-status",)),
    Task("jazn_memory", "Pamięć", "Status normalizacji", "jazn", ("--memory-normalization-status",)),
    Task("jazn_wake", "Pamięć", "Status wake-state", "jazn", ("--wake-state-status",)),
    Task("jazn_archive", "Pamięć", "Status archiwum rozmów", "jazn", ("--conversation-archive-status",)),
    Task("jazn_route", "Jaźń", "Status wyboru LLM", "jazn", ("--llm-route-status",)),
    Task("ollama_api", "Ollama", "Sprawdź API / modele", "http_tags"),
    Task("ollama_generate", "Ollama", "Test odpowiedzi modelu", "http_generate"),
    Task("ollama_models", "Ollama", "Lista modeli CLI", "ollama", ("list",)),
    Task("ollama_serve", "Ollama", "Uruchom serwer CLI", "ollama_serve", ("serve",)),
    Task("ollama_app", "Ollama", "Uruchom aplikację Windows", "ollama_app"),
    Task("ollama_log", "Logi", "Log serwera Ollama", "tail", ("server.log",)),
    Task("ollama_app_log", "Logi", "Log aplikacji Ollama", "tail", ("app.log",)),
    Task("mcp_help", "MCP", "Pomoc bootstrapu MCP", "mcp_help"),
    Task("mcp_probe", "MCP", "Probe initialize i tools/list (bez rozmowy)", "mcp_probe"),
)
TASK_INDEX = {task.key: task for task in TASKS}

REDACTIONS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    # Credential fields may be short or quoted JSON values with spaces. Redact
    # before writing to the bounded GUI/event history; preserve boolean flags.
    re.compile(
        r'''(?i)(\b[\w-]*(?:api[_-]?key|password|secret|token|credential)(?:[_-](?:file|path))?\b["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}"']+)'''
    ),
)
_URL_USERINFO = re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")


def safe_line(text: str) -> str:
    """Redact operator output before the GUI/event log may retain it."""
    text = str(text).replace("\x00", "")
    text = REDACTIONS[0].sub(r"\1[UKRYTO]", text)

    def mask_value(match: re.Match[str]) -> str:
        raw = match.group(0)[len(match.group(1)):].strip(chr(34) + chr(39))
        # Legitimate diagnostic booleans such as requires_api_key=false are not secrets.
        if raw.lower() in {"true", "false", "null"}:
            return match.group(0)
        return match.group(1) + "[UKRYTO]"

    text = REDACTIONS[1].sub(mask_value, text)
    text = _URL_USERINFO.sub(r"\1[UKRYTO]@", text)
    return text[:4000]


def is_local_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def http_json(path: str, payload: dict | None = None, timeout: float = 8) -> dict:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        OLLAMA_URL + path, data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method="POST" if body else "GET",
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Ollama HTTP status {response.status}")
        data = response.read(MAX_HTTP_BYTES + 1)
    if len(data) > MAX_HTTP_BYTES:
        raise RuntimeError("Ollama response too large")
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise RuntimeError("Invalid Ollama response shape")
    return obj


@dataclass
class JobState:
    task: Task
    proc: subprocess.Popen[str] | None = None
    generation: int = 0
    status: str = "nieuruchomiony"
    owned: bool = False
    cancel: threading.Event | None = None


class StudioCore:
    """Owns only subprocesses that this Studio created, never adopted daemons."""

    def __init__(self, root: Path, python: str, ollama: str, model: str):
        self.root = root.expanduser().resolve()
        self.python = python
        self.ollama = ollama
        self.model = model
        self.lock = threading.RLock()
        self.events: queue.Queue[tuple[str, str, str]] = queue.Queue(maxsize=12000)
        self.states = {task.key: JobState(task) for task in TASKS}
        self.logs: dict[str, deque[str]] = {
            task.key: deque(maxlen=MAX_LOG_LINES) for task in TASKS
        }

    def emit(self, key: str, channel: str, message: str) -> None:
        for line in str(message).splitlines() or [""]:
            entry = f"[{time.strftime('%H:%M:%S')}] [{channel}] {safe_line(line)}"
            with self.lock:
                self.logs[key].append(entry)
            try:
                self.events.put_nowait((key, channel, entry))
            except queue.Full:
                # Bounded queue: the on-disk runtime must never be stalled by GUI logs.
                pass

    def _set(self, key: str, status: str) -> None:
        with self.lock:
            self.states[key].status = status
        self.emit(key, "STATE", status)

    def command(self, task: Task) -> list[str]:
        if task.operation in ("jazn", "jazn_start"):
            if not (self.root / "run.py").is_file():
                raise FileNotFoundError(self.root / "run.py")
            return [self.python, "-X", "utf8", str(self.root / "run.py"), *task.args]
        if task.operation in ("ollama", "ollama_serve"):
            return [self.ollama, *task.args]
        if task.operation == "mcp_help":
            path = self.root / "latka_jazn" / "mcp" / "tunnel_bootstrap.py"
            if not path.is_file():
                raise FileNotFoundError(path)
            return [self.python, "-X", "utf8", str(path), "--help"]
        raise ValueError("Task does not own a shell command")

    def start(self, key: str) -> None:
        task = TASK_INDEX[key]
        with self.lock:
            state = self.states[key]
            if state.status in ("uruchamianie", "działa", "zatrzymywanie") or (
                state.proc is not None and state.proc.poll() is None
            ) or state.status.startswith(("działa PID", "probe PID", "śledzenie")):
                raise RuntimeError("To zadanie już działa")
            if not self.root.is_dir():
                raise FileNotFoundError(f"Brak katalogu Jaźni: {self.root}")
            if task.operation == "jazn_start" and is_local_port_open(DAEMON_PORT):
                self._set(key, "pominięto: port 8787 zajęty")
                self.emit(key, "INFO", "Port daemona jest zajęty. Uruchom jazn_status, aby potwierdzić jego tożsamość; nie tworzę drugiej kopii.")
                return
            if task.operation in ("ollama_serve", "ollama_app") and is_local_port_open(11434):
                self._set(key, "pominięto: port 11434 zajęty")
                self.emit(key, "INFO", "Ollama/inna usługa korzysta z portu 11434. Sprawdź ollama_api; nie uruchamiam drugiej kopii.")
                return
            state.generation += 1
            gen = state.generation
            state.cancel = threading.Event()
            state.status = "uruchamianie"
        self.emit(key, "STATE", "uruchamianie")
        threading.Thread(target=self._run, args=(task, gen), daemon=True).start()

    def _current(self, key: str, gen: int) -> bool:
        with self.lock:
            return self.states[key].generation == gen

    def _run(self, task: Task, gen: int) -> None:
        key = task.key
        try:
            if task.operation in ("http_tags", "http_generate"):
                self._set(key, "działa")
                if task.operation == "http_tags":
                    data = http_json("/api/tags", timeout=8)
                    names = [str(x.get("name", "")) for x in data.get("models", [])
                             if isinstance(x, dict)]
                    self.emit(key, "INFO", f"Ollama API 200; modele: {names}")
                else:
                    data = http_json("/api/generate", {
                        "model": self.model,
                        "prompt": "Napisz jedno zdanie po polsku: czy możesz odpowiadać?",
                        "stream": False,
                    }, timeout=180)
                    if data.get("done") is not True:
                        raise RuntimeError("Ollama nie potwierdziła zakończenia odpowiedzi")
                    self.emit(key, "INFO", f"Model: {data.get('model')}; done=true")
                    self.emit(key, "ANSWER", str(data.get("response", "")))
                self._set(key, "zakończono: OK")
            elif task.operation == "tail":
                self._tail(task, gen)
            elif task.operation == "mcp_probe":
                self._mcp_probe(task, gen)
            elif task.operation == "ollama_app":
                if not WINDOWS:
                    raise RuntimeError("Ten profil GUI jest przeznaczony tylko dla Windows")
                app = Path(self.ollama).with_name("ollama app.exe")
                if not app.is_file():
                    raise FileNotFoundError(app)
                # A launcher may detach. We never claim it is supervised afterwards.
                subprocess.Popen([str(app)], cwd=str(app.parent),
                                 stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 creationflags=NEW_PROCESS_GROUP)
                self.emit(key, "INFO", "Przekazano uruchomienie aplikacji; sprawdź API osobno")
                self._set(key, "przekazano start (niezweryfikowany)")
            else:
                self._process(task, gen)
        except (OSError, ValueError, RuntimeError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            self.emit(key, "ERROR", f"{type(exc).__name__}: {exc}")
            if self._current(key, gen):
                self._set(key, "błąd")
        finally:
            if self._current(key, gen):
                with self.lock:
                    state = self.states[key]
                    if state.proc is None or state.proc.poll() is not None:
                        state.owned = False
                        state.proc = None
                    else:
                        state.status = "wymaga ręcznego zatrzymania"
                        self.emit(key, "WARN", "Własny proces nadal działa; nie utracono właściciela PID")

    def _process(self, task: Task, gen: int) -> None:
        key = task.key
        command = self.command(task)
        proc = subprocess.Popen(
            command, cwd=str(self.root),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", bufsize=1, shell=False,
            creationflags=NEW_PROCESS_GROUP if WINDOWS else 0,
            start_new_session=not WINDOWS,
        )
        with self.lock:
            state = self.states[key]
            if state.generation != gen:
                proc.terminate()
                return
            state.proc = proc
            state.owned = True
        self._set(key, f"działa PID={proc.pid}")
        self.emit(key, "INFO", "Uruchomiono zaufany profil argv (bez shell=True)")
        readers = []
        for channel, stream in (("OUT", proc.stdout), ("ERR", proc.stderr)):
            t = threading.Thread(target=self._read_stream,
                                 args=(key, channel, stream), daemon=True)
            t.start()
            readers.append(t)
        code = proc.wait()
        for t in readers:
            t.join(timeout=2)
        if task.operation == "jazn_start":
            self.emit(key, "INFO", "Zakończenie startera nie oznacza wyłączenia ani gotowości daemona; sprawdź status")
        self._set(key, "zakończono: OK" if code == 0 else f"zakończono: kod {code}")

    def _read_stream(self, key: str, channel: str, stream) -> None:
        try:
            if stream is not None:
                for line in stream:
                    self.emit(key, channel, line.rstrip("\r\n"))
        finally:
            if stream is not None:
                stream.close()

    def _tail(self, task: Task, gen: int) -> None:
        if WINDOWS:
            folder = Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama"
        else:
            folder = Path.home() / ".ollama" / "logs"
        path = folder / task.args[0]
        if not path.is_file():
            raise FileNotFoundError(path)
        self._set(task.key, f"śledzenie: {path.name}")
        stop = self.states[task.key].cancel
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in deque(handle, maxlen=60):
                self.emit(task.key, "FILE", line.rstrip("\n"))
            while stop is not None and not stop.wait(0.4):
                where = handle.tell()
                line = handle.readline()
                if line:
                    self.emit(task.key, "FILE", line.rstrip("\n"))
                else:
                    handle.seek(where)
        self._set(task.key, "zatrzymano śledzenie")

    def _mcp_probe(self, task: Task, gen: int) -> None:
        """Local read-only JSON-RPC handshake; never call conversation tools.

        This is not a ChatGPT connection, not OAuth, and not finalization.
        """
        key = task.key
        path = self.root / "latka_jazn" / "mcp" / "tunnel_bootstrap.py"
        if not path.is_file():
            raise FileNotFoundError(path)
        cmd = [self.python, "-X", "utf8", str(path), "--root", str(self.root),
               "--daemon-url", "http://127.0.0.1:8787"]
        self.emit(key, "INFO", "Test lokalny MCP stdio: server/discover (2026) lub initialize (legacy), tools/list. Bez tools/call.")
        proc = subprocess.Popen(
            cmd, cwd=str(self.root),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", bufsize=1, shell=False,
            creationflags=NEW_PROCESS_GROUP if WINDOWS else 0,
            start_new_session=not WINDOWS,
        )
        inbox: queue.Queue[str] = queue.Queue(maxsize=1000)
        with self.lock:
            self.states[key].proc = proc
            self.states[key].owned = True
        rpc_stdout = proc.stdout
        if rpc_stdout is None:
            raise RuntimeError("MCP stdout unavailable")
        def read_rpc() -> None:
            try:
                for line in rpc_stdout:
                    try:
                        inbox.put_nowait(line)
                    except queue.Full:
                        break
            finally:
                rpc_stdout.close()
        reader = threading.Thread(target=read_rpc, daemon=True)
        reader.start()
        stderr_thread = threading.Thread(
            target=self._read_stream, args=(key, "MCP-ERR", proc.stderr), daemon=True
        )
        stderr_thread.start()
        self._set(key, f"probe PID={proc.pid}")
        stop = self.states[key].cancel
        try:
            # MCP 2026-07-28 uses per-request metadata, not initialize.
            # A legacy server may reject or ignore server/discover.
            meta = mcp_request_meta()
            self._mcp_send(proc, {"jsonrpc": "2.0", "id": 10,
                                  "method": "server/discover", "params": {"_meta": meta}})
            modern = False
            try:
                discovered = self._mcp_receive(inbox, 10, stop, timeout=7)
            except TimeoutError:
                self.emit(key, "MCP", "Brak server/discover w terminie — próba legacy")
            else:
                result = discovered.get("result", {})
                versions = result.get("supportedVersions", []) if isinstance(result, dict) else []
                if isinstance(versions, list) and "2026-07-28" in versions:
                    modern = True
                    self.emit(key, "MCP", "server/discover OK • protokół 2026-07-28 (stateless)")
                elif discovered.get("error", {}).get("code") == -32022:
                    raise RuntimeError("Nowoczesny serwer MCP zgłosił nieobsługiwaną wersję protokołu")
                else:
                    self.emit(key, "MCP", "Brak modern discovery • przejście do legacy initialize")

            if not modern:
                self._mcp_send(proc, {
                    "jsonrpc": "2.0", "id": 11, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "jazn-start-studio-probe",
                                              "version": STUDIO_VERSION}},
                })
                init = self._mcp_receive(inbox, 11, stop, timeout=25)
                if "error" in init:
                    raise RuntimeError(f"MCP initialize error: {init['error']}")
                result = init.get("result", {})
                server = result.get("serverInfo", {}) if isinstance(result, dict) else {}
                self.emit(key, "MCP", f"initialize OK • legacy • serwer: {server.get('name', '<brak>')}")
                self._mcp_send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

            names: set[str] = set()
            cursor: str | None = None
            for index in range(8):
                request_id = 100 + index
                params: dict = {"_meta": meta} if modern else {}
                if cursor:
                    params["cursor"] = cursor
                self._mcp_send(proc, {"jsonrpc": "2.0", "id": request_id,
                                      "method": "tools/list", "params": params})
                catalog = self._mcp_receive(inbox, request_id, stop, timeout=20)
                if "error" in catalog:
                    raise RuntimeError(f"MCP tools/list error: {catalog['error']}")
                result = catalog.get("result", {})
                if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
                    raise RuntimeError("MCP tools/list malformed")
                for item in result["tools"]:
                    if isinstance(item, dict) and isinstance(item.get("name"), str):
                        names.add(item["name"])
                next_cursor = result.get("nextCursor")
                if not isinstance(next_cursor, str) or not next_cursor:
                    break
                if next_cursor == cursor:
                    raise RuntimeError("MCP tools/list pagination did not advance")
                cursor = next_cursor
            else:
                raise RuntimeError("MCP tools/list exceeded pagination limit")
            self.emit(key, "MCP", f"tools/list OK • {len(names)} narzędzi • "
                      + ("2026-07-28" if modern else "legacy 2025-06-18"))
            self.emit(key, "MCP", ", ".join(sorted(names)[:80]))
            required = {"jazn_status", "jazn_generate_visible_reply",
                        "jazn_resume_visible_reply", "jazn_finalize_reply"}
            missing = sorted(required.difference(names))
            if missing:
                self.emit(key, "MCP", f"Brak narzędzi: {missing}")
                self._set(key, "lokalne MCP: niekompletne")
            else:
                self._set(key, "lokalne MCP: katalog gotowy (bez testu ChatGPT)")
        finally:
            # stdio's portable graceful shutdown: close stdin before termination.
            if proc.stdin is not None and not proc.stdin.closed:
                proc.stdin.close()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.emit(key, "WARN", "Własny MCP probe nadal działa; wymagane ręczne zatrzymanie")
            reader.join(timeout=1)
            stderr_thread.join(timeout=1)

    @staticmethod
    def _mcp_send(proc: subprocess.Popen[str], message: dict) -> None:
        if proc.stdin is None:
            raise RuntimeError("MCP stdin not available")
        proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    @staticmethod
    def _mcp_receive(inbox: queue.Queue[str], request_id: int,
                     stop: threading.Event | None, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if stop is not None and stop.is_set():
                raise RuntimeError("Probe cancelled")
            try:
                raw = inbox.get(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if len(raw) > MAX_HTTP_BYTES:
                raise RuntimeError("MCP message too large")
            try:
                obj = json.loads(raw)
            except ValueError:
                raise RuntimeError("Non-JSON message on MCP stdout")
            if isinstance(obj, dict) and obj.get("id") == request_id:
                return obj
        raise TimeoutError("MCP response timed out")

    def stop(self, key: str) -> None:
        with self.lock:
            state = self.states[key]
            if state.cancel:
                state.cancel.set()
            proc = state.proc
            owned = state.owned
            if not owned and state.status not in ("działa", "uruchamianie") and not state.status.startswith("śledzenie"):
                return
        if proc is not None and owned and proc.poll() is None:
            # No taskkill /T /F, no adoption of existing services.
            if WINDOWS:
                proc.terminate()  # Windows ends only this process, not the detached daemon.
            else:
                os.killpg(proc.pid, signal.SIGTERM)
        self.emit(key, "STOP", "Zażądano zatrzymania zadania Studio (bez wymuszania)")

    def active(self) -> list[str]:
        with self.lock:
            return [key for key, st in self.states.items()
                    if st.status in ("uruchamianie", "działa", "zatrzymywanie", "wymaga ręcznego zatrzymania")
                    or st.status.startswith(("działa PID", "probe PID", "śledzenie"))]


def read_only_check(core: StudioCore) -> dict:
    return {
        "schema_version": "jazn_start_studio_check/v1",
        "studio_version": STUDIO_VERSION,
        "root": str(core.root),
        "run_py_present": (core.root / "run.py").is_file(),
        "main_py_present": (core.root / "main.py").is_file(),
        "mcp_bootstrap_present": (
            core.root / "latka_jazn" / "mcp" / "tunnel_bootstrap.py"
        ).is_file(),
        "python": core.python,
        "ollama_executable": core.ollama,
        "daemon_loopback_port_open_not_identity_proof": is_local_port_open(DAEMON_PORT),
        "ollama_loopback_port_open_not_model_proof": is_local_port_open(11434),
        "does_not_validate_runtime_turn": True,
    }


def run_text(core: StudioCore) -> int:
    print("JAŹŃ — Studio Startu", STUDIO_VERSION)
    print("Polecenia: list, start <id>, stop <id>, log <id>, check, quit")
    done = threading.Event()

    def consume() -> None:
        while not done.wait(0.12):
            try:
                _, _, line = core.events.get_nowait()
            except queue.Empty:
                continue
            print("\n" + line, flush=True)

    listener = threading.Thread(target=consume, daemon=True)
    listener.start()
    while True:
        try:
            line = input("studio> ").strip()
        except (EOFError, KeyboardInterrupt):
            line = "quit"
        cmd, _, argument = line.partition(" ")
        if cmd == "list":
            for task in TASKS:
                print(f"{task.key:20s} {task.group:8s} {core.states[task.key].status}")
        elif cmd == "start" and argument in TASK_INDEX:
            try:
                core.start(argument)
            except (RuntimeError, KeyError, OSError) as exc:
                print("BŁĄD:", safe_line(str(exc)))
        elif cmd == "stop" and argument in TASK_INDEX:
            core.stop(argument)
        elif cmd == "log" and argument in TASK_INDEX:
            for row in core.logs[argument]:
                print(row)
        elif cmd == "check":
            print(json.dumps(read_only_check(core), ensure_ascii=False, indent=2))
        elif cmd in ("quit", "exit"):
            running = core.active()
            if running:
                print("Wciąż aktywne zadania:", ", ".join(running))
                print("Zatrzymaj je poleceniem stop <id>; Studio nie zamknie ich automatycznie.")
                continue
            done.set()
            return 0
        else:
            print("Nieznane polecenie lub ID. Wpisz list.")


def run_studio(core: StudioCore) -> int:
    # GUI lives in a separate module: terminal/headless operation imports no Tk.
    try:
        from tools.jazn_start_studio_dashboard import launch
    except ModuleNotFoundError:
        from jazn_start_studio_dashboard import launch
    return launch(core)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Operator Jaźni: tekst / Tk Studio / diagnostyka",
        allow_abbrev=False,
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--text", action="store_true")
    modes.add_argument("--studio", action="store_true")
    modes.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path,
                        default=Path(os.environ.get("JAZN_ROOT", Path(__file__).resolve().parents[1])))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--ollama", default=shutil.which("ollama") or (
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe")
        if WINDOWS else "ollama"
    ))
    parser.add_argument("--model", default=os.environ.get("JAZN_OLLAMA_MODEL", "gemma3:latest"))
    args = parser.parse_args(argv)
    core = StudioCore(args.root, args.python, args.ollama, args.model)
    if args.check:
        print(json.dumps(read_only_check(core), ensure_ascii=False, indent=2))
        return 0
    if args.text:
        return run_text(core)
    return run_studio(core)


if __name__ == "__main__":
    raise SystemExit(main())
