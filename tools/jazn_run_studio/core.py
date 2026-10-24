"""UI-independent operator contracts shared by desktop and terminal modes.

Runtime lifecycle belongs to run.py -> main.py. External process ownership
is a live Popen handle created here, never a PID imported from a settings file.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from importlib.util import find_spec
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from latka_jazn.tools.jazn_studio.core import verified_root
from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.core.system_config import read_system_config, write_system_config
from .external import spawn, environment, run as run_external

MAX_OUTPUT = 2 * 1024 * 1024
MAX_LINE = 16384
SECRET_NAME = re.compile(r"token|secret|password|api.?key|credential|authorization", re.I)
SECRET_ASSIGNMENT = re.compile(
    r'''(?i)(["']?[\w-]*(?:token|secret|password|api[_-]?key|credential)[\w-]*["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}]+)'''
)


class StudioError(ValueError):
    """An operator action failed validation before execution."""


class Redactor:
    def __init__(self, environment: dict[str, str] | None = None):
        environment = dict(os.environ) if environment is None else environment
        self.values = sorted({v for k, v in environment.items() if SECRET_NAME.search(k) and v},
                             key=len, reverse=True)

    def text(self, value: str) -> str:
        text = value.replace("\x00", "")
        for secret in self.values:
            text = text.replace(secret, "[UKRYTO]")
        text = SECRET_ASSIGNMENT.sub(r'\1"[UKRYTO]"', text)
        text = re.sub(r"(?i)\bBearer\s+[^\s\"',;]+", "Bearer [UKRYTO]", text)
        text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[UKRYTO]", text)
        text = re.sub(r"(https?://)[^/\s:@]+:[^/\s@]+@", r"\1[UKRYTO]@", text)
        return text


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    args: tuple[str, ...]
    description: str
    timeout: int = 45
    mutates: bool = False


ACTIONS = (
    Action("version", "Wersja", ("--version",), "Wersja zainstalowanego systemu."),
    Action("preflight", "Sprawdź hosta", ("host-preflight", "--json"), "Możliwości hosta; bez aktywacji rozmowy."),
    Action("status", "Status runtime", ("status", "--json"), "Root, wersja, PID, endpoint, tożsamość i gotowość."),
    Action("doctor", "Pełna diagnostyka", ("doctor", "--json"), "Kanoniczna diagnoza systemu.", 120),
    Action("model", "Adapter i model", ("model-status", "--json"), "Konfiguracja adaptera językowego."),
    Action("memory", "Status pamięci", ("memory-status", "--json"), "Stan pamięci bez edycji danych."),
    Action("start", "Uruchom runtime", ("start",), "Start przez centralny control plane.", 90, True),
    Action("stop", "Zatrzymaj runtime", ("stop",), "Weryfikowany stop przez runtime; bez zabijania PID.", 45, True),
    Action("restart", "Restart runtime", ("restart", "--json"), "Kanoniczny restart z kontrolą tożsamości.", 120, True),
    Action("mcp", "Katalog MCP", ("mcp-probe", "--url", "http://127.0.0.1:8080/mcp",
           "--check-chatgpt-tool-catalog", "--timeout", "8"), "Probe osobnej sesji, bez wywołania rozmowy.", 30),
    Action("package", "Sprawdź paczkę", ("package-smoke", "--profile", "system", "--json"), "Walidacja paczki systemowej.", 180),
)
ACTION_BY_KEY = {a.key: a for a in ACTIONS}
DIAGNOSTIC_BATCH = ("version", "preflight", "status", "doctor", "model", "mcp")


@dataclass(frozen=True)
class Studio:
    key: str
    label: str
    entry: tuple[str, ...]
    description: str


STUDIOS = (
    Studio("operator", "Studio systemowe", ("tools/jazn_studio.py",), "Runtime, MCP i aktualizacje."),
    Studio("configuration", "Konfiguracja", ("tools/jazn_config_studio.py",), "Walidowane profile przyszłych uruchomień."),
    Studio("memory", "Pamięć", ("tools/jazn_memory_studio.py",), "Kanoniczne operacje i inspekcja pamięci."),
    Studio("rebuild", "Odbudowa pamięci", ("tools/rebuild_memory_app.py",), "Rekonstrukcja z kontrolą źródeł."),
    Studio("tests", "Testy", ("tools/jazn_tests_studio.py",), "Katalog, wykonanie i historia testów."),
    Studio("packages", "Generator paczek", ("tools/jazn_pack_generator.py",), "Budowanie i kontrola dystrybucji."),
    Studio("dependencies", "Zależności", ("-m", "latka_jazn.tools.dependency_studio", "--ui", "window"), "Profile i zweryfikowany wheelhouse."),
    Studio("python", "Python Runtime", ("-m", "latka_jazn.tools.python_runtime_studio", "--ui", "window"), "Zarządzanie interpreterami."),
    Studio("start", "Studio Startu (klasyczne)", ("tools/jazn_start_studio.py",), "Dotychczasowa konsola operatora."),
    Studio("versions", "Wersje i metadane", ("tools/jazn_version_rebuild.py",), "Wersjonowanie, backup i kanoniczne metadane."),
)


def _path_without_links(path: Path) -> Path:
    for component in (path, *path.parents):
        if component.is_symlink() or component.is_junction():
            raise StudioError("Dowiązania nie są dozwolone w ścieżce ustawień lub raportu")
    return path


@dataclass(frozen=True)
class Settings:
    python: str = ""
    mcp_python: str = ""
    ollama: str = ""
    cloudflared: str = ""
    tunnel_config: str = ""
    tunnel_id: str = ""
    model: str = ""
    theme: str = "system"
    accent: str = "#9876d4"
    cloudflare_url: str = ""
    mcp_port: str = "8080"
    daemon_url: str = "http://127.0.0.1:8787"
    secrets_file: str = ""
    runtime_profile: str = "off"

    @classmethod
    def validate(cls, data: dict[str, Any]) -> Settings:
        if not isinstance(data, dict) or set(data) - set(cls.__dataclass_fields__):
            raise StudioError("Nieznane pola ustawień")
        if any(not isinstance(v, str) or len(v) > 2048 or any(c in v for c in "\0\r\n") for v in data.values()):
            raise StudioError("Ustawienia muszą być krótkimi tekstami bez znaków sterujących")
        obj = cls(**data)
        if obj.theme not in {"system", "light", "dark", "purple", "custom"}:
            raise StudioError("Nieznany motyw")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", obj.accent):
            raise StudioError("Kolor wymaga formatu #RRGGBB")
        for path in (obj.python, obj.mcp_python, obj.ollama, obj.cloudflared, obj.tunnel_config, obj.secrets_file):
            if path and (not Path(path).is_absolute() or not Path(path).is_file()):
                raise StudioError("Wskaż istniejący plik przez ścieżkę absolutną")
        if obj.tunnel_id and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}", obj.tunnel_id):
            raise StudioError("Nieprawidłowa nazwa / UUID tunelu")
        if obj.model and (obj.model.startswith("-") or not re.fullmatch(r"[\w./:@-]{1,200}", obj.model)):
            raise StudioError("Nieprawidłowa nazwa modelu")
        if not re.fullmatch(r"[0-9]{4,5}", obj.mcp_port) or not 1024 <= int(obj.mcp_port) <= 65535:
            raise StudioError("Port MCP musi być liczbą od 1024 do 65535")
        try:
            daemon = urlsplit(obj.daemon_url)
            daemon_port = daemon.port
        except ValueError as exc:
            raise StudioError("Nieprawidłowy adres lokalnego daemona") from exc
        if (daemon.scheme != "http" or daemon.hostname != "127.0.0.1"
                or daemon_port is None or not 1 <= daemon_port <= 65535
                or daemon.username is not None
                or daemon.password is not None or daemon.path not in {"", "/"}
                or daemon.query or daemon.fragment):
            raise StudioError("Adres daemona musi wskazywać wyłącznie http://127.0.0.1:PORT")
        if obj.cloudflare_url:
            from latka_jazn.tools.jazn_studio.core import StudioSettings
            StudioSettings.validate({"cloudflare_url": obj.cloudflare_url})
        if obj.runtime_profile not in {"off", "operator"}:
            raise StudioError("Profil runtime: off albo operator")
        return obj


def daemon_cli_options(settings: Settings) -> list[str]:
    """Validated local endpoint args shared by Studio lifecycle and chat.

    Do not infer daemon ownership from a listening port. The canonical CLI
    performs root/process verification; Studio only selects the endpoint.
    """
    checked = Settings.validate(asdict(settings))
    endpoint = urlsplit(checked.daemon_url)
    assert endpoint.port is not None  # Guaranteed by Settings.validate.
    return ["--daemon-host", "127.0.0.1", "--daemon-port", str(endpoint.port)]


def settings_path(root: Path) -> Path:
    # A local operator profile, not runtime or private MEMORY configuration.
    return _path_without_links(workspace_runtime_path(root) / "jazn_run_studio" / "settings.json")


def load_settings(root: Path) -> tuple[Settings, str | None]:
    canonical = read_system_config(root)
    target = settings_path(root)
    if not target.exists():
        return Settings.validate(dict(canonical.studio)), None
    raw = target.read_bytes()
    if len(raw) > 32768:
        raise StudioError("Zbyt duży plik ustawień")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise StudioError("Nieprawidłowy format ustawień Studio")
    return Settings.validate({**data, **canonical.studio}), sha256(raw).hexdigest()


def save_settings(root: Path, settings: Settings, expected: str | None) -> str:
    settings = Settings.validate(asdict(settings))
    target = settings_path(root)
    current = sha256(target.read_bytes()).hexdigest() if target.exists() else None
    if current != expected:
        raise StudioError("Ustawienia zmieniły się na dysku; wczytaj je ponownie")
    target.parent.mkdir(parents=True, exist_ok=True)
    canonical = read_system_config(root)
    shared = {key: val for key, val in (
        ("python", settings.python), ("model", settings.model),
        ("daemon_url", settings.daemon_url),
    ) if val}
    write_system_config(root, canonical.values, shared, expected_digest=canonical.digest)
    data = (json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=".settings-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)
    return sha256(data).hexdigest()


def python_executable(settings: Settings) -> str:
    explicit = settings.python or os.environ.get("JAZN_STUDIO_PYTHON", "")
    if explicit:
        if not Path(explicit).is_absolute() or not Path(explicit).is_file():
            raise StudioError("Nieprawidłowy JAZN_STUDIO_PYTHON / interpreter")
        return explicit
    if getattr(sys, "frozen", False):
        raise StudioError("Wersja EXE wymaga ścieżki do Pythona w ustawieniach lub JAZN_STUDIO_PYTHON")
    return sys.executable


def executable(explicit: str, name: str) -> str:
    found = explicit or shutil.which(name)
    if not found or not Path(found).is_file():
        raise StudioError("Brak programu: " + name + ". Otwórz stronę instalacji w Studio.")
    return str(Path(found).absolute())


def discovery(settings: Settings) -> dict[str, Any]:
    return {
        "python": settings.python or os.environ.get("JAZN_STUDIO_PYTHON") or (None if getattr(sys, "frozen", False) else sys.executable),
        "python_version": sys.version.split()[0],
        "ollama": settings.ollama or shutil.which("ollama"),
        "cloudflared": settings.cloudflared or shutil.which("cloudflared"),
        "git": shutil.which("git"),
        "dependencies": {m: find_spec(m) is not None for m in ("PySide6", "mcp", "uvicorn", "starlette", "pydantic")},
        "chatgpt": "Zdalny host; lokalny proces nie jest zarządzany przez Studio",
        "openai_api": "Planowane; lokalna rozmowa Ollama nie wymaga klucza",
    }


def daemon_evidence(data: dict[str, Any]) -> dict[str, Any]:
    """Preserve evidence levels without upgrading a listening port to readiness."""
    daemon = data.get("daemon")
    daemon = daemon if isinstance(daemon, dict) else {}
    ping = daemon.get("ping")
    ping = ping if isinstance(ping, dict) else {}
    matrix = data.get("capability_matrix")
    matrix = matrix if isinstance(matrix, dict) else {}
    return {
        "system_version": data.get("runtime_version"),
        "daemon_version": ping.get("runtime_version"),
        "pid": daemon.get("pid"),
        "instance_id": daemon.get("daemon_instance_id"),
        "endpoint_reachable": daemon.get("endpoint_reachable") is True,
        "process_identity_confirmed": daemon.get("process_identity_confirmed") is True,
        "endpoint_identity_matches": daemon.get("endpoint_identity_matches") is True,
        "heartbeat_fresh": daemon.get("endpoint_heartbeat_fresh") is True,
        "active_state": daemon.get("active_state"),
        "conversation_ready": matrix.get("conversation_ready") is True,
        "accepted_visible_turn": False,
    }


@dataclass
class Job:
    key: str
    state: str = "starting"
    pid: int | None = None
    returncode: int | None = None
    error: str | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None
    proc: subprocess.Popen[bytes] | None = field(default=None, repr=False)
    done: threading.Event = field(default_factory=threading.Event, repr=False)
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    output: bytearray = field(default_factory=bytearray, repr=False)
    input_data: bytes | None = field(default=None, repr=False)

    def snapshot(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in ("key", "state", "pid", "returncode", "error", "started", "finished")}


def write_error_record(root: Path, key: str, snapshot: dict[str, Any], redactor: Redactor) -> Path:
    """Persist only redacted, bounded failure metadata in the Git-ignored workspace.

    Never persist command arguments, chat contents, raw stdout or tracebacks.
    This is an operator diagnostic, not a runtime event or finalization record.
    """
    folder = _path_without_links(workspace_runtime_path(root) / "jazn_run_studio")
    folder.mkdir(parents=True, exist_ok=True)
    filename = _path_without_links(folder / "errors_jazn_studio.log")
    fields = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "job": redactor.text(key[:128]),
        "state": "failed",
        "error": redactor.text(str(snapshot.get("error") or "unspecified")[:256]),
        "returncode": snapshot.get("returncode") if isinstance(snapshot.get("returncode"), int) else None,
    }
    handler = RotatingFileHandler(filename, maxBytes=1_048_576, backupCount=3, encoding="utf-8")
    try:
        record = logging.LogRecord("jazn_studio_errors", logging.ERROR, "", 0,
                                   json.dumps(fields, ensure_ascii=False), (), None)
        handler.emit(record)
    finally:
        handler.close()
    return filename


class Controller:
    """Bounded job and event registry; work never runs on the GUI thread."""

    def __init__(self, root: Path, settings: Settings | None = None):
        self.root = verified_root(root)
        self.settings = settings or load_settings(self.root)[0]
        self.redactor = Redactor()
        self.jobs: dict[str, Job] = {}
        self.logs: dict[str, deque[str]] = {}
        self.events: queue.Queue[tuple[str, str, Any]] = queue.Queue(maxsize=5000)
        # Terminal states, validated chat finals and helper results cannot be
        # discarded when a burst of diagnostic logs fills the bounded queue.
        self.critical_events: queue.SimpleQueue[tuple[str, str, Any]] = queue.SimpleQueue()
        self.lock = threading.RLock()
        self.closed = False
        self.chat: Any = None
        self.memory_observations: dict[str, Any] = {}

    def emit(self, key: str, kind: str, value: Any) -> None:
        with self.lock:
            if kind == "log":
                value = self.redactor.text(str(value))
                self.logs.setdefault(key, deque(maxlen=2500)).append(value)
            elif kind == "state" and isinstance(value, dict):
                value = dict(value)
                if value.get("error"):
                    value["error"] = self.redactor.text(str(value["error"]))
                if value.get("state") == "failed":
                    try:
                        write_error_record(self.root, key, value, self.redactor)
                    except (OSError, StudioError):
                        # A diagnostic disk failure must never lose the terminal
                        # job state or the accepted chat-final delivery channel.
                        warning = "BŁĄD: nie można zapisać lokalnego rejestru awarii"
                        self.logs.setdefault("studio:errors", deque(maxlen=2500)).append(warning)
                        self.critical_events.put(("studio:errors", "log", warning))
            try:
                self.events.put_nowait((key, kind, value))
            except queue.Full:
                if kind != "log":
                    self.critical_events.put((key, kind, value))

    def command(self, key: str) -> list[str]:
        try:
            action = ACTION_BY_KEY[key]
        except KeyError:
            raise StudioError("Nieznana operacja") from None
        args = list(action.args)
        if key in {"status", "doctor", "start", "stop", "restart"}:
            # Preserve unchanged default commands while routing configured
            # non-default endpoints through the public Jaźń control plane.
            if self.settings.daemon_url != "http://127.0.0.1:8787":
                target = daemon_cli_options(self.settings)
                if key in {"start", "stop", "restart"}:
                    args.append("--")  # argparse.REMAINDER on lifecycle verbs.
                args.extend(target)
        return [python_executable(self.settings), "-X", "utf8", str(self.root / "run.py"), *args]

    def _reserve(self, key: str) -> Job:
        with self.lock:
            if self.closed:
                raise StudioError("Studio jest zamykane")
            if key in self.jobs and not self.jobs[key].done.is_set():
                raise StudioError("Operacja już trwa: " + key)
            if key in {"start", "stop", "restart"} and any(
                j.key in {"start", "stop", "restart"} and not j.done.is_set() for j in self.jobs.values()
            ):
                raise StudioError("Inna operacja lifecycle już trwa")
            job = Job(key)
            self.jobs[key] = job
            return job

    def start_action(self, key: str) -> Job:
        argv = self.command(key)
        job = self._reserve(key)
        self._launch(job, argv, ACTION_BY_KEY[key].timeout)
        return job

    def start_studio(self, key: str) -> Job:
        spec = next((s for s in STUDIOS if s.key == key), None)
        if spec is None:
            raise StudioError("Nieznane Studio")
        entry = list(spec.entry)
        if entry[0] != "-m":
            script = self.root / entry[0]
            if not script.is_file():
                raise StudioError("Brak pliku Studio")
            entry[0] = str(script)
        job = self._reserve("studio:" + key)
        self._launch(job, [python_executable(self.settings), "-X", "utf8", *entry], None)
        return job

    def start_service(self, service: str) -> Job:
        if service == "ollama":
            # Fail closed if another service already occupies the API port.
            with socket.socket() as probe:
                probe.settimeout(0.3)
                if probe.connect_ex(("127.0.0.1", 11434)) == 0:
                    raise StudioError("Port Ollama jest zajęty; Studio nie przejmuje istniejącego procesu")
            argv = [executable(self.settings.ollama, "ollama"), "serve"]
        elif service == "cloudflare":
            if not self.settings.tunnel_config or not self.settings.tunnel_id:
                raise StudioError("Wskaż istniejącą konfigurację i nazwę/UUID tunelu w ustawieniach")
            argv = [executable(self.settings.cloudflared, "cloudflared"), "tunnel", "--config",
                    self.settings.tunnel_config, "run", self.settings.tunnel_id]
        elif service == "gateway":
            port = int(self.settings.mcp_port)
            with socket.socket() as probe:
                probe.settimeout(0.3)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise StudioError("Port MCP jest zajęty; Studio nie przejmuje istniejącej bramy")
            # The canonical CLI refuses MCP without an explicit security mode.
            # Studio owns only a local developer listener; public OAuth must be
            # configured through the separately validated deployment workflow.
            mcp_interpreter = python_executable(Settings(python=self.settings.mcp_python or self.settings.python))
            argv = [mcp_interpreter, "-X", "utf8", str(self.root / "run.py"),
                    "mcp-http", "--loopback-dev", "--host", "127.0.0.1",
                    "--port", str(port), "--daemon-url", self.settings.daemon_url]
        else:
            raise StudioError("Ta usługa nie jest lokalnym zarządzanym procesem")
        job = self._reserve("service:" + service)
        self._launch(job, argv, None)
        return job

    def probe(self, key: str) -> Job:
        from . import probes
        calls = {"ollama": lambda: probes.ollama(self.settings.model),
                 "gateway": lambda: probes.gateway(self.settings.mcp_port),
                 "cloudflare": lambda: probes.cloudflare(self.settings.cloudflare_url),
                 "tunnel_service": lambda: probes.tunnel_service(self.root)}
        if key not in calls:
            raise StudioError("Nieznany test połączenia")
        job = self._reserve("probe:" + key)
        def worker() -> None:
            try:
                job.state = "running"
                evidence = calls[key]()
                self.emit(job.key, "probe", evidence)
                self.emit(job.key, "log", json.dumps(evidence, ensure_ascii=False))
                # A reachable endpoint or successful probe execution is not proof
                # of service readiness. Preserve the evidence event, but keep
                # the operator job red when the selected capability is absent.
                if key in {"gateway", "cloudflare"} and evidence.get("ready") is not True:
                    job.state, job.error = "failed", "service_not_ready"
                elif key == "ollama" and evidence.get("selected_model_present") is False:
                    job.state, job.error = "failed", "selected_model_missing"
                else:
                    job.state = "succeeded"
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                job.state, job.error = "failed", type(exc).__name__
                self.emit(job.key, "log", "Test połączenia nie powiódł się: " + type(exc).__name__)
            finally:
                job.finished = time.time()
                job.done.set()
                self.emit(job.key, "state", job.snapshot())
        threading.Thread(target=worker, daemon=True).start()
        return job

    def connect_chat(self) -> None:
        if self.chat is None:
            from .chat import ChatClient
            self.chat = ChatClient(self)
        self.chat.connect()

    def child_environment(self, *, profile: bool = False) -> dict[str, str]:
        env = environment()
        if profile and self.settings.runtime_profile == "operator":
            result = run_external([python_executable(self.settings), "-X", "utf8", "-m",
                                  "tools.jazn_run_studio.studio_worker", "profile-env"], cwd=self.root, timeout=35)
            if result.returncode or len(result.stdout) > 32768:
                raise StudioError("Walidacja profilu przyszłego uruchomienia nie powiodła się")
            values = json.loads(result.stdout)
            if not isinstance(values, dict):
                raise StudioError("Niepoprawny profil środowiska")
            env.update(values)
        if self.settings.secrets_file:
            target = _path_without_links(Path(self.settings.secrets_file))
            if target.is_relative_to(self.root):
                if not target.is_relative_to(workspace_runtime_path(self.root)):
                    checked = run_external(["git", "check-ignore", "--quiet", "--", str(target)], cwd=self.root, timeout=5)
                    if checked.returncode:
                        raise StudioError("Plik sekretów wewnątrz SYSTEM musi być ignorowany przez Git")
            if target.stat().st_size > 16384:
                raise StudioError("Plik sekretów przekracza 16 KiB")
            values = json.loads(target.read_bytes())
            allowed = {"JAZN_MEMORY_CLOUD_TOKEN", "JAZN_MEMORY_WRITER_LEASE_TOKEN", "JAZN_MCP_OAUTH_CLIENT_SECRET", "TUNNEL_TOKEN"}
            if not isinstance(values, dict) or set(values) - allowed or any(not isinstance(v, str) or not v or "\0" in v or "\n" in v for v in values.values()):
                raise StudioError("Nieprawidłowe pola pliku sekretów")
            env.update(values)
            with self.lock:
                self.redactor.values = sorted(set(self.redactor.values) | set(values.values()), key=len, reverse=True)
        return env

    def studio_helper(self, mode: str, key: str = "", data: dict[str, Any] | None = None) -> Job:
        if mode not in {"schema", "preview", "execute", "profile-read", "profile-save"}:
            raise StudioError("Nieznana operacja Studio")
        if mode in {"schema", "preview", "execute"} and key not in {"memory", "rebuild", "tests", "packages", "dependencies", "python"}:
            raise StudioError("Nieznane Studio")
        job = self._reserve("helper:" + mode + ":" + key)
        if data is not None:
            job.input_data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            if len(job.input_data) > 65536:
                job.done.set()
                job.state = "failed"
                raise StudioError("Zbyt duże dane operacji")
        argv = [python_executable(self.settings), "-X", "utf8", "-m", "tools.jazn_run_studio.studio_worker", mode]
        if key:
            argv.append(key)
        self._launch(job, argv, 7200 if mode == "execute" else 45)
        return job

    def _launch(self, job: Job, argv: list[str], timeout: int | None) -> None:
        threading.Thread(target=self._run, args=(job, argv, timeout), daemon=True,
                         name="studio-" + job.key).start()

    def inspect_memory(self, operation: str, *, project: str = "",
                       reference: str = "", reference_sha256: str = "",
                       parent: str = "", parent_sha256: str = "") -> Job:
        if operation not in {"layout", "comparison", "readiness"}:
            raise StudioError("Nieznana inspekcja pamięci")
        if operation != "readiness" and not project:
            raise StudioError("Wybierz plik projektu pamięci")
        argv = [python_executable(self.settings), "-X", "utf8", str(self.root / "run.py"),
                "memory-inspection", "--root", str(self.root), "--operation", operation, "--json"]
        for option, value in (("project", project), ("reference", reference),
                              ("reference-sha256", reference_sha256), ("parent", parent),
                              ("parent-sha256", parent_sha256)):
            if value:
                argv.extend(("--" + option, value))
        job = self._reserve("memory:p1:" + operation)
        with self.lock:
            self.memory_observations.pop(operation, None)
        # Comparison's existing bounded backups and hashes can each take 90 s.
        self._launch(job, argv, 600 if operation == "comparison" else 45)
        return job

    def _read(self, job: Job, pipe: Any) -> None:
        pending = bytearray()
        overflow = False
        while True:
            chunk = pipe.read1(4096)
            if not chunk:
                break
            with self.lock:
                if job.key.startswith(("service:", "studio:")):
                    pass  # Long-running logs rotate; no raw capture is needed.
                elif len(job.output) + len(chunk) <= MAX_OUTPUT:
                    job.output.extend(chunk)
                else:
                    job.error = "output_limit"
                    job.cancel.set()
            for byte in chunk:
                if byte == 10:
                    if not job.key.startswith(("helper:schema:", "helper:preview:", "helper:profile-", "memory:p1:")):
                        self.emit(job.key, "log", "[Pominięto zbyt długi wiersz]" if overflow else pending.decode("utf-8", "replace").rstrip("\r"))
                    pending.clear()
                    overflow = False
                elif not overflow:
                    if len(pending) >= MAX_LINE:
                        pending.clear()
                        overflow = True
                    else:
                        pending.append(byte)
        if (pending or overflow) and not job.key.startswith(("helper:schema:", "helper:preview:", "helper:profile-", "memory:p1:")):
            self.emit(job.key, "log", "[Pominięto zbyt długi wiersz]" if overflow else pending.decode("utf-8", "replace"))
        pipe.close()

    def _run(self, job: Job, argv: list[str], timeout: int | None) -> None:
        try:
            # Never pass shell text; the retained handle is the ownership proof.
            proc = spawn(argv, cwd=self.root, stdin=subprocess.PIPE if job.input_data is not None else subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    env=self.child_environment(profile=job.key in {"start", "restart"}))
            with self.lock:
                job.proc = proc
                job.pid = proc.pid
                job.state = "running"
            self.emit(job.key, "state", job.snapshot())
            assert proc.stdout is not None
            reader = threading.Thread(target=self._read, args=(job, proc.stdout), daemon=True)
            reader.start()
            if job.input_data is not None:
                assert proc.stdin is not None
                proc.stdin.write(job.input_data)
                proc.stdin.close()
                job.input_data = None
            deadline = time.monotonic() + timeout if timeout else None
            while proc.poll() is None:
                if job.cancel.wait(0.05) or (deadline is not None and time.monotonic() >= deadline):
                    job.state = "stopping"
                    self.emit(job.key, "state", job.snapshot())
                    if not job.cancel.is_set():
                        job.error = "timeout"
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)
                    break
            reader.join(timeout=3)
            job.returncode = proc.returncode
            if reader.is_alive():
                job.error = "output_pipe_not_closed"
            job.state = ("failed" if job.error else "stopped" if job.cancel.is_set()
                         else "succeeded" if proc.returncode == 0 else "failed")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            job.state = "failed"
            job.error = type(exc).__name__
            self.emit(job.key, "log", "Nie udało się wykonać operacji: " + type(exc).__name__)
        finally:
            job.finished = time.time()
            # Raw diagnostic stdout is never retained after completion.
            raw = bytes(job.output)
            job.output.clear()
            if job.key.startswith("memory:p1:") and job.state in {"succeeded", "failed"} and raw:
                try:
                    observation = json.loads(raw)
                    if not isinstance(observation, dict) or observation.get("schema") != "jazn_memory_operator_observation/v1":
                        raise ValueError("memory_observation_shape")
                    with self.lock:
                        self.memory_observations[job.key.removeprefix("memory:p1:")] = {
                            "observed_at_utc": datetime.fromtimestamp(job.started, timezone.utc).isoformat(),
                            "report": observation,
                        }
                    self.emit(job.key, "memory_report", {"started": job.started, "report": observation})
                except ValueError:
                    job.state, job.error = "failed", "invalid_memory_observation_json"
            if job.state == "succeeded" and job.key in {"start", "stop", "restart"}:
                try:
                    outcome = json.loads(raw)
                    if not isinstance(outcome, dict) or outcome.get("ok") is not True:
                        job.state, job.error = "failed", "runtime_operation_rejected"
                except ValueError:
                    job.state, job.error = "failed", "invalid_operation_json"
            if job.state == "succeeded" and job.key == "status":
                try:
                    value = json.loads(raw)
                    if not isinstance(value, dict):
                        raise ValueError("status_shape")
                    self.emit(job.key, "evidence", daemon_evidence(value))
                except ValueError:
                    job.state = "failed"
                    job.error = "invalid_status_json"
            if job.state == "succeeded" and job.key.startswith(("helper:schema:", "helper:preview:", "helper:profile-")):
                try:
                    self.emit(job.key, "helper", json.loads(raw))
                except ValueError:
                    job.state, job.error = "failed", "invalid_helper_json"
            job.done.set()
            self.emit(job.key, "state", job.snapshot())

    def stop_owned(self, key: str) -> None:
        with self.lock:
            job = self.jobs.get(key)
            if job is None or job.done.is_set() or job.proc is None or job.proc.poll() is not None:
                raise StudioError("Brak aktywnego procesu należącego do tego Studio")
            job.cancel.set()

    def restart_service(self, service: str) -> None:
        key = "service:" + service
        self.stop_owned(key)
        job = self.jobs[key]
        def restart() -> None:
            if not job.done.wait(10) or job.state != "stopped":
                self.emit(key, "log", "Restart przerwany: zatrzymanie procesu nie zostało potwierdzone")
                return
            try:
                self.start_service(service)
            except (OSError, StudioError) as exc:
                self.emit(key, "log", str(exc))
        threading.Thread(target=restart, daemon=True).start()

    def run_batch(self, keys: tuple[str, ...] = DIAGNOSTIC_BATCH) -> Job:
        if any(key not in ACTION_BY_KEY or ACTION_BY_KEY[key].mutates for key in keys):
            raise StudioError("Pakiet diagnostyczny może zawierać wyłącznie znane odczyty")
        batch = self._reserve("batch")
        def worker() -> None:
            batch.state = "running"
            try:
                for key in keys:
                    if batch.cancel.is_set():
                        batch.state = "stopped"
                        return
                    job = self.start_action(key)
                    job.done.wait()
                    if job.state != "succeeded":
                        batch.state = "failed"
                        batch.error = "failed_step:" + key
                        return
                batch.state = "succeeded"
            except StudioError as exc:
                batch.state = "failed"
                batch.error = str(exc)
            finally:
                batch.finished = time.time()
                batch.done.set()
                self.emit("batch", "state", batch.snapshot())
        threading.Thread(target=worker, daemon=True).start()
        return batch

    def report(self) -> dict[str, Any]:
        with self.lock:
            return {"schema": "jazn_run_studio_report/v1", "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "jobs": [j.snapshot() for j in self.jobs.values()],
                    "logs": {k: list(lines) for k, lines in self.logs.items()},
                    "memory_observations": dict(self.memory_observations),
                    "memory_observation_boundary": "Separate historical read-only observations; not an atomic cross-database snapshot or activation authority.",
                    "accepted_visible_turn": False}

    def export_report(self, path: Path) -> None:
        path = _path_without_links(path.absolute())
        def sanitized(value: Any) -> Any:
            if isinstance(value, str):
                return self.redactor.text(value)
            if isinstance(value, dict):
                return {k: sanitized(v) for k, v in value.items()}
            if isinstance(value, list):
                return [sanitized(v) for v in value]
            return value
        # Exclusive creation prevents silently replacing a source/config file.
        with path.open("x", encoding="utf-8") as stream:
            json.dump(sanitized(self.report()), stream, ensure_ascii=False, indent=2)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                if not job.done.is_set():
                    job.cancel.set()
