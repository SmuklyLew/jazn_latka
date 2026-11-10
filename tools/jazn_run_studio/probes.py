"""Bounded read-only service probes. HTTP availability never proves a turn."""
from __future__ import annotations

import json
from http.client import HTTPException
import os
import re
import ssl
import csv
import subprocess
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request

from .external import run


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("HTTP redirects are not allowed for service probes")


def read_json(url: str, *, timeout: float = 3) -> tuple[int, dict[str, Any]]:
    parts = urlsplit(url)
    local = (parts.scheme == "http" and parts.hostname == "127.0.0.1"
             and parts.port is not None and 1024 <= parts.port <= 65535
             and parts.path in {"/api/tags", "/readyz"})

    remote = parts.scheme == "https" and str(parts.hostname or "").endswith(".workers.dev") and parts.port in {None, 443}
    if not (local or remote) or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Unsupported service probe URL")
    # Do not inherit SSLKEYLOGFILE from desktop/AV launch environments.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs()
    opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))
    try:
        response = opener.open(Request(url, headers={"Accept": "application/json"}), timeout=timeout)
    except HTTPError as exc:
        response = exc
    with response:
        try:
            raw = response.read(262145)
        except HTTPException as exc:
            raise ValueError("Invalid HTTP response framing") from exc
        code = int(response.code)
    if len(raw) > 262144:
        raise ValueError("Response exceeds 256 KiB")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return code, data


def ollama_api_base(value: str) -> str:
    """Accept only an explicit loopback API, without credentials or URL suffixes."""
    parts = urlsplit(value)
    if (parts.scheme != "http" or parts.hostname != "127.0.0.1"
            or parts.port is None or not 1024 <= parts.port <= 65535
            or parts.username or parts.password or parts.path not in {"", "/"}
            or parts.query or parts.fragment):
        raise ValueError("Unsupported local Ollama API base")
    return f"http://127.0.0.1:{parts.port}"


def ollama(model: str = "", *, api_base: str = "http://127.0.0.1:11434") -> dict[str, Any]:
    code, payload = read_json(ollama_api_base(api_base) + "/api/tags")
    entries = payload.get("models")
    if code != 200 or not isinstance(entries, list) or any(not isinstance(m, dict) or not isinstance(m.get("name"), str) for m in entries):
        raise ValueError("Invalid Ollama model list")
    names = [entry["name"] for entry in entries]
    return {"service": "ollama", "endpoint_reachable": True, "models": names,
            "selected_model": model, "selected_model_present": model in names if model else None,
            "generation_verified": False, "accepted_visible_turn": False}


def ollama_process(executable: str = "") -> dict[str, Any]:
    """Read-only OS process inventory; not proof of a reachable API or model."""
    if sys.platform == "win32":
        system32 = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32" / "tasklist.exe"
        command = [str(system32), "/FO", "CSV", "/NH"]
    else:
        command = ["ps", "-A", "-o", "comm="]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=6, check=False,
    )
    if result.returncode != 0:
        raise OSError("ollama_process_inventory_failed")
    if len(result.stdout) > 1_048_576:
        raise OSError("ollama_process_inventory_too_large")
    if sys.platform == "win32":
        names = [row[0].strip().casefold()
                 for row in csv.reader(result.stdout.splitlines()) if row]
    else:
        names = [Path(line.strip()).name.casefold()
                 for line in result.stdout.splitlines() if line.strip()]
    count = sum(n in {"ollama.exe", "ollama app.exe", "ollama"} for n in names)
    installed = bool((executable and Path(executable).is_file())
                     or shutil.which("ollama"))
    return {
        "service": "ollama_process", "process_observed": True,
        "process_running": count > 0, "process_count": count,
        "program_installed": installed, "api_verified": False,
        "generation_verified": False, "accepted_visible_turn": False,
        "observation_basis": "os_process_name_inventory",
    }


def ollama_generation(model: str) -> dict[str, Any]:
    """Explicit bounded local generation test, never a Jaźń finalization."""
    if not isinstance(model, str) or not re.fullmatch(r"[\w./:@-]{1,200}", model) or model.startswith("-"):
        raise ValueError("Wybierz poprawną nazwę modelu Ollama")
    evidence = {**ollama(model), "accepted_visible_turn": False}
    if evidence["selected_model_present"] is not True:
        return {**evidence, "generation_verified": False, "reason": "model_not_visible"}
    request = Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps({
            "model": model, "messages": [{"role": "user", "content": "Odpowiedz: OK"}],
            "stream": False, "options": {"num_predict": 12},
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    # A local fixed endpoint, no proxies, no redirects and no raw prompt/response logs.
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=60) as response:
        if response.status != 200:
            raise ValueError("Ollama generation HTTP status was not 200")
        raw = response.read(262145)
    if len(raw) > 262144:
        raise ValueError("Ollama generation response too large")
    payload = json.loads(raw)
    message = payload.get("message") if isinstance(payload, dict) else None
    verified = (isinstance(payload, dict) and payload.get("done") is True
                and isinstance(message, dict)
                and isinstance(message.get("content"), str)
                and bool(message["content"].strip()))
    return {**evidence, "generation_verified": bool(verified),
            "generation_basis": "bounded_local_api_chat" if verified else "invalid_generation_response"}


def gateway(port: str = "8080") -> dict[str, Any]:
    if not isinstance(port, str) or not re.fullmatch(r"[0-9]{4,5}", port) or not 1024 <= int(port) <= 65535:
        raise ValueError("Invalid local MCP gateway port")
    code, payload = read_json(f"http://127.0.0.1:{int(port)}/readyz")
    return {"service": "gateway", "http_status": code, "endpoint_reachable": True,
            "ready": code == 200 and payload.get("ready") is True,
            "gateway_live": payload.get("gateway_live") is True,
            "accepted_visible_turn": False}


def cloudflare(origin: str) -> dict[str, Any]:
    code, payload = read_json(origin.rstrip("/") + "/readyz", timeout=5)
    return {"service": "cloudflare", "http_status": code, "endpoint_reachable": True,
            "ready": code == 200 and payload.get("ready") is True,
            "accepted_visible_turn": False}


def tunnel_service(root: Path) -> dict[str, Any]:
    if os.name != "nt":
        return {"service": "cloudflared_os", "status": "not_windows", "managed_by_studio": False}
    exe = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    result = run([str(exe), "-NoProfile", "-NonInteractive", "-Command",
        "$s=Get-Service -Name cloudflared -ErrorAction SilentlyContinue; "
        "if($null -eq $s){'{\"present\":false}'}else{"
        "[pscustomobject]@{present=$true;status=$s.Status.ToString()}|ConvertTo-Json -Compress}"], cwd=root, timeout=8)
    if result.returncode or len(result.stdout) > 4096:
        raise ValueError("Windows service query failed")
    data = json.loads(result.stdout.decode("utf-8-sig"))
    return {"service": "cloudflared_os", "present": data.get("present") is True,
            "status": str(data.get("status", "absent")), "managed_by_studio": False}
