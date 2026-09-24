from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import time
from typing import Any, Mapping
from urllib.parse import urlsplit
import webbrowser

from latka_jazn.cli_commands import diagnostics
from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon import status_daemon
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version


CONSOLE_SCHEMA_VERSION = schema_version("runtime_console")
SNAPSHOT_SCHEMA_VERSION = schema_version("runtime_console_snapshot")
_ALLOWED_BIND_HOSTS = frozenset({"127.0.0.1", "localhost"})
_ASSET_TYPES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.mjs": ("app.mjs", "text/javascript; charset=utf-8"),
    "/model.mjs": ("model.mjs", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'"
    ),
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class RuntimeConsoleError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeConsoleConfig:
    root: Path
    host: str = "127.0.0.1"
    port: int = 8765
    daemon_host: str = "127.0.0.1"
    daemon_port: int = 8787
    event_interval_seconds: float = 1.0
    stream_window_seconds: float = 30.0

    def normalized(self) -> "RuntimeConsoleConfig":
        root = Path(self.root).expanduser().resolve()
        host = str(self.host or "").strip().lower()
        daemon_host = str(self.daemon_host or "").strip()
        if host not in _ALLOWED_BIND_HOSTS:
            raise RuntimeConsoleError(
                "runtime_console_loopback_only: host must be 127.0.0.1 or localhost"
            )
        port = int(self.port)
        if not 0 <= port <= 65535:
            raise RuntimeConsoleError("runtime_console_port_out_of_range")
        daemon_port = int(self.daemon_port)
        if not 1 <= daemon_port <= 65535:
            raise RuntimeConsoleError("runtime_console_daemon_port_out_of_range")
        interval = max(0.25, min(float(self.event_interval_seconds), 10.0))
        window = max(interval, min(float(self.stream_window_seconds), 120.0))
        return RuntimeConsoleConfig(
            root=root,
            host=host,
            port=port,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            event_interval_seconds=interval,
            stream_window_seconds=window,
        )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _daemon_projection(daemon: Mapping[str, Any]) -> dict[str, Any]:
    ping = _mapping(daemon.get("ping"))
    readiness = _mapping(daemon.get("readiness"))
    return {
        "active_state": daemon.get("active_state") or ping.get("active_state") or "unknown",
        "endpoint_reachable": daemon.get("endpoint_reachable"),
        "pid_alive": daemon.get("pid_alive"),
        "pid": daemon.get("pid") or ping.get("pid"),
        "heartbeat_age_seconds": (
            daemon.get("heartbeat_age_seconds")
            if daemon.get("heartbeat_age_seconds") is not None
            else ping.get("heartbeat_age_seconds")
        ),
        "timestamp_trusted": daemon.get("timestamp_trusted", ping.get("timestamp_trusted")),
        "ready_endpoint_ok": readiness.get("ok"),
    }


def build_live_snapshot(
    root: Path,
    *,
    daemon_host: str = "127.0.0.1",
    daemon_port: int = 8787,
) -> dict[str, Any]:
    config = JaznConfig(root=Path(root).resolve())
    daemon = status_daemon(
        config,
        host=daemon_host,
        port=int(daemon_port),
        probe_endpoint=True,
    )
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "kind": "live",
        "generated_at_utc": _utc_now(),
        "runtime_version": PACKAGE_VERSION_FULL,
        "runtime": _daemon_projection(daemon),
        "truth_boundary": (
            "This live console snapshot is read-only operational evidence. "
            "Daemon liveness/readiness never proves an accepted visible turn."
        ),
    }


def build_overview_snapshot(
    root: Path,
    *,
    daemon_host: str = "127.0.0.1",
    daemon_port: int = 8787,
) -> dict[str, Any]:
    status = diagnostics.status_payload(
        Path(root).resolve(),
        probe_endpoint=True,
        daemon_host=daemon_host,
        daemon_port=int(daemon_port),
    )
    capability = _mapping(status.get("capability_readiness"))
    transactional = _mapping(status.get("transactional_memory"))
    daemon = _mapping(status.get("daemon"))
    visible = _mapping(status.get("chatgpt_visible_turn_readiness"))
    system_profile = _mapping(status.get("system_readiness_profile"))
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "kind": "overview",
        "generated_at_utc": _utc_now(),
        "runtime_version": status.get("runtime_version") or PACKAGE_VERSION_FULL,
        "runtime": {
            "operational_state": status.get("operational_state"),
            "process_ok": status.get("process_ok"),
            "runtime_core_ready": status.get("runtime_core_ready"),
            "system_fully_ready": status.get("system_fully_ready"),
            **_daemon_projection(daemon),
        },
        "memory": {
            "transactional_ready": transactional.get("ready"),
            "search_ready": capability.get("memory_search_ready"),
            "search_status": capability.get("memory_search_status"),
            "legacy_search_ready": capability.get("legacy_memory_search_ready"),
            "continuity_ready": capability.get("continuity_ready"),
        },
        "nlp": {
            "core_ready": capability.get("nlp_core_ready"),
            "enhanced_ready": capability.get("nlp_enhanced_ready"),
            "enhanced_status": capability.get("nlp_enhanced_status"),
        },
        "rest": {
            "scheduler_ready": capability.get("rest_scheduler_ready"),
            "scheduler_running": capability.get("rest_scheduler_running"),
            "scheduler_status": capability.get("rest_scheduler_status"),
        },
        "visible_turn": {
            "scope": visible.get("scope"),
            "status": visible.get("status"),
            "ready": visible.get("ready"),
            "accepted_visible_turn_required": visible.get(
                "accepted_visible_turn_required"
            ),
            "daemon_liveness_sufficient": visible.get(
                "daemon_liveness_sufficient"
            ),
        },
        "readiness_profile": {
            "profile": system_profile.get("profile"),
            "system_fully_ready": system_profile.get("system_fully_ready"),
        },
        "truth_boundary": (
            "The browser is a presentation client only. Python runtime state remains authoritative; "
            "this console cannot create turns, mutate memory, change lifecycle, or claim authorship."
        ),
    }


def _asset_root() -> Path:
    return Path(__file__).resolve().parents[1] / "resources" / "runtime_console"


def _host_header_is_loopback(value: str | None) -> bool:
    raw = str(value or "").strip()
    if not raw or len(raw) > 255:
        return False
    parsed = urlsplit(f"//{raw}")
    return str(parsed.hostname or "").lower() in _ALLOWED_BIND_HOSTS


def _origin_is_same_loopback(value: str | None, *, server_port: int) -> bool:
    if not value:
        return True
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "http":
            return False
        if str(parsed.hostname or "").lower() not in _ALLOWED_BIND_HOSTS:
            return False
        return parsed.port == server_port
    except ValueError:
        return False


class RuntimeConsoleServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, config: RuntimeConsoleConfig) -> None:
        self.console_config = config.normalized()
        super().__init__(
            (self.console_config.host, self.console_config.port),
            RuntimeConsoleHandler,
        )


class RuntimeConsoleHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "JaznRuntimeConsole/1"
    sys_version = ""

    @property
    def console_server(self) -> RuntimeConsoleServer:
        server = self.server
        if not isinstance(server, RuntimeConsoleServer):
            raise RuntimeConsoleError("runtime_console_server_type_invalid")
        return server

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _security_headers(self) -> None:
        for name, value in _SECURITY_HEADERS.items():
            self.send_header(name, value)

    def _authorized_request_surface(self) -> bool:
        if not _host_header_is_loopback(self.headers.get("Host")):
            self._json_response(
                {"ok": False, "error": "runtime_console_host_header_rejected"},
                status=HTTPStatus.FORBIDDEN,
            )
            return False
        if not _origin_is_same_loopback(
            self.headers.get("Origin"),
            server_port=int(self.console_server.server_port),
        ):
            self._json_response(
                {"ok": False, "error": "runtime_console_cross_origin_rejected"},
                status=HTTPStatus.FORBIDDEN,
            )
            return False
        return True

    def _write_body(
        self,
        body: bytes,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str,
    ) -> None:
        self.send_response(int(status))
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json_response(
        self,
        payload: Mapping[str, Any],
        *,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        body = (
            json.dumps(
                dict(payload),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            + "\n"
        ).encode("utf-8")
        self._write_body(
            body,
            status=status,
            content_type="application/json; charset=utf-8",
        )

    def _serve_asset(self, request_path: str) -> bool:
        spec = _ASSET_TYPES.get(request_path)
        if spec is None:
            return False
        filename, content_type = spec
        path = _asset_root() / filename
        try:
            body = path.read_bytes()
        except OSError as exc:
            self._json_response(
                {
                    "ok": False,
                    "error": "runtime_console_asset_unavailable",
                    "asset": filename,
                    "error_type": type(exc).__name__,
                },
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return True
        self._write_body(body, content_type=content_type)
        return True

    def _serve_sse(self) -> None:
        config = self.console_server.console_config
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "close")
        self.end_headers()
        started = time.monotonic()
        sequence = 0
        try:
            while time.monotonic() - started < config.stream_window_seconds:
                sequence += 1
                snapshot = build_live_snapshot(
                    config.root,
                    daemon_host=config.daemon_host,
                    daemon_port=config.daemon_port,
                )
                payload = json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
                frame = (
                    f"id: {sequence}\n"
                    "event: runtime\n"
                    f"data: {payload}\n\n"
                ).encode("utf-8")
                self.wfile.write(frame)
                self.wfile.flush()
                time.sleep(config.event_interval_seconds)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.close_connection = True

    def do_HEAD(self) -> None:
        if not self._authorized_request_surface():
            return
        path = urlsplit(self.path).path
        if self._serve_asset(path):
            return
        if path in {"/healthz", "/api/v1/live", "/api/v1/overview"}:
            self._json_response({"ok": True})
            return
        self._json_response(
            {"ok": False, "error": "not_found"},
            status=HTTPStatus.NOT_FOUND,
        )

    def do_GET(self) -> None:
        if not self._authorized_request_surface():
            return
        path = urlsplit(self.path).path
        if self._serve_asset(path):
            return
        config = self.console_server.console_config
        if path == "/healthz":
            self._json_response(
                {
                    "ok": True,
                    "schema_version": CONSOLE_SCHEMA_VERSION,
                    "surface": "loopback_read_only",
                }
            )
            return
        if path == "/api/v1/live":
            self._json_response(
                build_live_snapshot(
                    config.root,
                    daemon_host=config.daemon_host,
                    daemon_port=config.daemon_port,
                )
            )
            return
        if path == "/api/v1/overview":
            self._json_response(
                build_overview_snapshot(
                    config.root,
                    daemon_host=config.daemon_host,
                    daemon_port=config.daemon_port,
                )
            )
            return
        if path == "/api/v1/events":
            self._serve_sse()
            return
        self._json_response(
            {"ok": False, "error": "not_found"},
            status=HTTPStatus.NOT_FOUND,
        )

    def _method_not_allowed(self) -> None:
        self._json_response(
            {
                "ok": False,
                "error": "runtime_console_read_only",
                "allowed_methods": ["GET", "HEAD"],
            },
            status=HTTPStatus.METHOD_NOT_ALLOWED,
        )

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed


def runtime_console_startup_payload(server: RuntimeConsoleServer) -> dict[str, Any]:
    config = server.console_config
    port = int(server.server_port)
    return {
        "ok": True,
        "schema_version": CONSOLE_SCHEMA_VERSION,
        "url": f"http://{config.host}:{port}/",
        "host": config.host,
        "port": port,
        "daemon_host": config.daemon_host,
        "daemon_port": config.daemon_port,
        "read_only": True,
        "loopback_only": True,
        "javascript_required_for_ui": True,
        "node_required_for_runtime": False,
        "truth_boundary": (
            "Runtime Console is a local read-only browser client. "
            "It does not own runtime, memory, identity, routing, lifecycle, or finalization."
        ),
    }


def run_runtime_console(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    daemon_host: str = "127.0.0.1",
    daemon_port: int = 8787,
    open_browser: bool = False,
    as_json: bool = False,
) -> int:
    config = RuntimeConsoleConfig(
        root=Path(root),
        host=host,
        port=port,
        daemon_host=daemon_host,
        daemon_port=daemon_port,
    ).normalized()
    server = RuntimeConsoleServer(config)
    payload = runtime_console_startup_payload(server)
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Jaźń Runtime Console: {payload['url']}")
        print("read-only / loopback-only; Ctrl+C kończy konsolę")
    if open_browser:
        webbrowser.open(str(payload["url"]), new=2, autoraise=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0
