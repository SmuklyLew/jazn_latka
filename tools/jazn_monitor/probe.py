"""Bounded, read-only service probes: no daemon lifecycle or private MEMORY access."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
from urllib import request

from .telemetry import jobs_snapshot, process_snapshot, _windows_process_rows

MAX_JSON = 128 * 1024
SERVICES = ("Daemon Jaźni", "Runtime Core", "Ollama", "MCP", "Supervisor", "JSS", "MEMORY")


@dataclass(frozen=True)
class Observation:
    state: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _parse_json(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_JSON:
        raise ValueError("JSON exceeds size limit")
    obj = json.loads(data.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("Expected JSON object")
    return obj


def _marker(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_JSON:
            return None
        return _parse_json(path.read_bytes())
    except (OSError, ValueError, UnicodeError):
        return None


def _http_json(port: int, endpoint: str, timeout: float = 1.5) -> dict[str, Any] | None:
    """Fixed 127.0.0.1, explicit endpoint whitelist, no ambient proxy."""
    if type(port) is not int or not 1 <= port <= 65535:
        return None
    if endpoint not in {"/live", "/ready", "/api/tags"}:
        return None
    url = f"http://127.0.0.1:{port}{endpoint}"
    opener = request.build_opener(request.ProxyHandler({}))
    req = request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with opener.open(req, timeout=timeout) as response:
            if response.status != 200:
                return None
            return _parse_json(response.read(MAX_JSON + 1))
    except (OSError, ValueError, UnicodeError):
        return None


def _path_matches(value: Any, root: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        return os.path.normcase(os.path.normpath(str(Path(value).resolve()))) == os.path.normcase(
            os.path.normpath(str(root.resolve())))
    except (OSError, ValueError, RuntimeError):
        return False


def _matches_instance(marker: dict[str, Any], live: dict[str, Any], root: Path) -> bool:
    if not (isinstance(marker.get("daemon_instance_id"), str)
            and marker.get("daemon_instance_id")
            and marker.get("daemon_instance_id") == live.get("daemon_instance_id")):
        return False
    marker_pid = marker.get("daemon_pid", marker.get("pid"))
    live_pid = live.get("daemon_pid", live.get("pid"))
    if type(marker_pid) is not int or type(live_pid) is not int:
        return False
    if marker_pid <= 0 or marker_pid != live_pid:
        return False
    return _path_matches(live.get("active_root", live.get("subject_runtime_root")), root)


def snapshot(root: Path | None, *, daemon_port: int = 8787,
             ollama_port: int = 11434) -> dict[str, Any]:
    """Read-only observation. UNKNOWN is not STOPPED and /live is not /ready."""
    services = {name: Observation("unknown", "Brak zweryfikowanych danych") for name in SERVICES}
    selected = Path(root).expanduser().resolve() if root is not None else None
    verified_marker: dict[str, Any] | None = None
    verified_live: dict[str, Any] | None = None
    if selected is not None and (selected / "run.py").is_file():
        marker = _marker(selected / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json")
        live = _http_json(daemon_port, "/live")
        if marker is None:
            services["Daemon Jaźni"] = Observation("unknown", "Brak poprawnego markera instancji")
        elif live is None:
            # A missing HTTP response alone does NOT establish stopped state.
            rows = _windows_process_rows()
            marker_pid = marker.get("daemon_pid")
            fingerprint = marker.get("process_fingerprint")
            identity_verified = (
                isinstance(fingerprint, dict)
                and fingerprint.get("available") is True
                and fingerprint.get("pid") == marker_pid
                and isinstance(fingerprint.get("identity_token"), str)
                and bool(fingerprint["identity_token"])
            )
            if (identity_verified and rows is not None and type(marker_pid) is int
                    and not any(row.get("pid") == marker_pid for row in rows)):
                services["Daemon Jaźni"] = Observation("stopped", "Brak PID w odczycie systemu Windows i brak /live")
            elif rows is not None:
                services["Daemon Jaźni"] = Observation("unavailable", "Brak /live; tożsamość procesu niezweryfikowana")
            else:
                services["Daemon Jaźni"] = Observation("unknown", "Brak /live i dowodu stanu procesu")
        elif not _matches_instance(marker, live, selected):
            services["Daemon Jaźni"] = Observation("error", "PID, identyfikator lub ROOT nie zgadzają się")
        else:
            trusted = live.get("heartbeat_fresh") is True and live.get("liveness_ok") is True
            services["Daemon Jaźni"] = (
                Observation("ready", f"PID {live.get('daemon_pid')} · port {daemon_port} · świeży heartbeat")
                if trusted else Observation("reachable", "Instancja zgodna, lecz liveness/heartbeat niepotwierdzony"))
            if trusted:
                verified_marker, verified_live = marker, live
                ready = _http_json(daemon_port, "/ready")
                if ready is not None and ready.get("daemon_instance_id") == marker.get("daemon_instance_id"):
                    if (ready.get("readiness_ok") is True
                            and ready.get("runtime_write_ready") is True):
                        services["Runtime Core"] = Observation(
                            "ready", "Chat worker i runtime-write gotowe wg /ready; finalizacja tury osobno")
                    elif ready.get("readiness_ok") is False:
                        services["Runtime Core"] = Observation("reachable", "Daemon działa, /ready zgłasza brak gotowości")
                    if ready.get("authenticated_mcp_ready") is True:
                        services["MCP"] = Observation("reachable", "Uwierzytelnione MCP potwierdzone przez /ready")
                    if (ready.get("full_autobiographical_recall_ready") is True
                            and ready.get("continuity_ready") is True):
                        services["MEMORY"] = Observation("ready", "Recall i continuity potwierdzone")
                    elif ready.get("persistent_memory_enabled") is False:
                        services["MEMORY"] = Observation("disabled", "MEMORY nieaktywna")
                else:
                    services["Runtime Core"] = Observation("unavailable", "Daemon działa, brak odpowiedzi /ready")
    elif selected is not None:
        services["Daemon Jaźni"] = Observation("unknown", "Wybrany katalog nie zawiera run.py")

    tags = _http_json(ollama_port, "/api/tags")
    if isinstance(tags, dict) and isinstance(tags.get("models"), list):
        models = [m.get("name") for m in tags["models"] if isinstance(m, dict)
                  and isinstance(m.get("name"), str)]
        services["Ollama"] = Observation("reachable", f"API dostępne · modeli: {len(models)}; generacja niesprawdzona")
    elif selected is not None:
        services["Ollama"] = Observation("unavailable", "Brak odpowiedzi /api/tags; stan procesu Ollama niepotwierdzony")
    if services["MCP"].state == "unknown":
        services["MCP"] = Observation("unknown", "Brak potwierdzonej trasy, autoryzacji i toolsetu")
    services["Supervisor"] = Observation("unknown", "Brak niezależnego dowodu właściciela supervisora")
    services["JSS"] = Observation("unknown", "Proces JSS niezweryfikowany; monitor go nie uruchamia")
    processes = process_snapshot(selected, verified_marker, verified_live)
    jobs = jobs_snapshot(selected, verified_marker)
    return {
        "schema_version": "jazn_monitor_snapshot/v1",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_root": str(selected) if selected is not None else None,
        "observation_only": True,
        "services": {name: item.as_dict() for name, item in services.items()},
        "processes": processes,
        "jobs": jobs,
        "finalization": jobs["finalization"],
    }
