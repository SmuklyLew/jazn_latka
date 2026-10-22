"""Black-box subprocess regression for mcp-http CLI unresponsive TCP listeners.

No public listener, live daemon, real turn or private MEMORY is required.
Each test uses an isolated temp root and terminates the full process tree.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib import error, request

import pytest

pytest.importorskip("mcp")
pytest.importorskip("uvicorn")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get(url: str, *, timeout: float = 2) -> tuple[int, dict[str, object]]:
    opener = request.build_opener(request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def _stop_tree(proc: subprocess.Popen[str]) -> None:
    if sys.platform == "win32":
        # A Windows venv redirector may start the actual listener as a child.
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True, check=False, timeout=10,
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        if sys.platform != "win32":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        proc.wait(timeout=5)


def test_real_runpy_mcp_http_listener_and_catalog_are_responsive(tmp_path: Path) -> None:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "mcp-http-process.log"
    cmd = [
        sys.executable, "-X", "utf8", str(PROJECT_ROOT / "run.py"),
        "mcp-http", "--root", str(tmp_path),
        "--loopback-dev", "--host", "127.0.0.1",
        "--port", str(port), "--daemon-url", "http://127.0.0.1:1",
    ]
    kwargs: dict[str, object] = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {"start_new_session": True}
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd, cwd=PROJECT_ROOT, stdout=log, stderr=subprocess.STDOUT,
            text=True, **kwargs,
        )
        try:
            deadline = time.monotonic() + 25
            health: tuple[int, dict[str, object]] | None = None
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                try:
                    health = _get(f"{url}/healthz", timeout=1.2)
                    break
                except (OSError, ValueError, json.JSONDecodeError):
                    time.sleep(0.2)
            assert health is not None, (
                "mcp-http CLI failed to answer healthz; "
                + log_path.read_text(encoding="utf-8", errors="replace")[-1800:]
            )
            assert health[0] == 200
            assert health[1].get("gateway_live") is True
            # An unreachable daemon must report NOT_READY promptly, not block ASGI.
            started = time.monotonic()
            ready_code, ready_body = _get(f"{url}/readyz", timeout=10)
            assert time.monotonic() - started < 10
            assert ready_code == 503
            assert ready_body.get("ready") is False

            probe = subprocess.run(
                [sys.executable, "-X", "utf8", str(PROJECT_ROOT / "run.py"),
                 "mcp-probe", "--url", f"{url}/mcp", "--timeout", "10",
                 "--check-chatgpt-tool-catalog", "--json"],
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=22,
                check=False,
            )
            assert probe.returncode == 0, probe.stderr[-1500:] + probe.stdout[-1500:]
            report = json.loads(probe.stdout)
            assert report["ok"] is True
            assert report["tool_catalog_verified"] is True
            assert report["missing_required_tool_names"] == []
        finally:
            _stop_tree(proc)
