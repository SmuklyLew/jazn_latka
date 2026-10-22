"""Bounded read-only service probes. HTTP availability never proves a turn."""
from __future__ import annotations

import json
from http.client import HTTPException
import os
import ssl
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
    local = parts.scheme == "http" and parts.hostname == "127.0.0.1" and parts.port in {8080, 11434}
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


def ollama(model: str = "") -> dict[str, Any]:
    code, payload = read_json("http://127.0.0.1:11434/api/tags")
    entries = payload.get("models")
    if code != 200 or not isinstance(entries, list) or any(not isinstance(m, dict) or not isinstance(m.get("name"), str) for m in entries):
        raise ValueError("Invalid Ollama model list")
    names = [entry["name"] for entry in entries]
    return {"service": "ollama", "endpoint_reachable": True, "models": names,
            "selected_model_present": model in names if model else None,
            "generation_verified": False, "accepted_visible_turn": False}


def gateway() -> dict[str, Any]:
    code, payload = read_json("http://127.0.0.1:8080/readyz")
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
