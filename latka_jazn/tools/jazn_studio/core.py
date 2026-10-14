"""Jaźń Studio operator backend: no alternate runtime or private-memory editor.

All operations delegate to the canonical run.py -> main.py entrypoint.
Settings are a bounded, secret-free operator profile in workspace_runtime.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.version import PACKAGE_VERSION_FULL

STUDIO_VERSION = "1.0.0"
SCHEMA = "jazn_operator_studio/v1"
DEFAULT_CLOUDFLARE_URL = "https://jazn-runtime.jazn-lakta.workers.dev"
LOCAL_MCP_URL = "http://127.0.0.1:8080/mcp"
REQUIRED_TOOLS = (
    "jazn_status",
    "jazn_generate_visible_reply",
    "jazn_resume_visible_reply",
    "jazn_finalize_reply",
)
ALLOWED_COMMANDS: Mapping[str, tuple[str, ...]] = {
    "status": ("status", "--json"),
    "doctor": ("doctor", "--json"),
    "model": ("model-status", "--json"),
    "memory": ("memory-status", "--json"),
    "mcp_catalog": (
        "mcp-probe", "--url", LOCAL_MCP_URL,
        "--check-chatgpt-tool-catalog", "--timeout", "8",
    ),
}
_SAFE_PROFILE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}$")


class StudioError(ValueError):
    """Operator command rejected; no runtime, memory or Git write occurred."""


def verified_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if not (root / "main.py").is_file() or not (root / "run.py").is_file():
        raise StudioError("Not a Jaźń SYSTEM root: run.py and main.py required")
    if not (root / "latka_jazn" / "version.py").is_file():
        raise StudioError("Not a Jaźń SYSTEM root: package version marker missing")
    return root


def _local_http_url(value: str) -> str:
    u = urlsplit(value)
    if (u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost")
            or u.port != 8080 or u.path != "/mcp" or u.username or u.password
            or u.query or u.fragment):
        raise StudioError("Local MCP must remain http://127.0.0.1:8080/mcp")
    return LOCAL_MCP_URL


def _remote_url(value: str) -> str:
    u = urlsplit(value.strip())
    if (u.scheme != "https" or not u.hostname or u.username or u.password
            or u.query or u.fragment or u.port not in (None, 443)
            or u.path not in ("", "/")):
        raise StudioError("Cloudflare URL must be one HTTPS origin without credentials")
    if not u.hostname.endswith(".workers.dev"):
        raise StudioError("Cloudflare URL must end with .workers.dev")
    host = u.hostname.lower()
    if len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
        raise StudioError("Invalid Cloudflare hostname")
    return "https://" + host


@dataclass(frozen=True)
class StudioSettings:
    cloudflare_url: str = DEFAULT_CLOUDFLARE_URL
    local_mcp_url: str = LOCAL_MCP_URL
    refresh_seconds: int = 20
    timeout_seconds: int = 8
    show_details: bool = False

    @classmethod
    def validate(cls, value: Mapping[str, Any]) -> "StudioSettings":
        fields = set(cls.__dataclass_fields__)
        if set(value) - fields:
            raise StudioError("Unknown settings keys are not allowed")
        refresh = value.get("refresh_seconds", 20)
        timeout = value.get("timeout_seconds", 8)
        if type(refresh) is not int or not (5 <= refresh <= 300):
            raise StudioError("refresh_seconds must be integer 5..300")
        if type(timeout) is not int or not (2 <= timeout <= 30):
            raise StudioError("timeout_seconds must be integer 2..30")
        details = value.get("show_details", False)
        if type(details) is not bool:
            raise StudioError("show_details must be boolean")
        return cls(
            cloudflare_url=_remote_url(value.get("cloudflare_url", DEFAULT_CLOUDFLARE_URL)),
            local_mcp_url=_local_http_url(value.get("local_mcp_url", LOCAL_MCP_URL)),
            refresh_seconds=refresh,
            timeout_seconds=timeout,
            show_details=details,
        )


def _settings_file(root: Path) -> Path:
    target = workspace_runtime_path(root) / "jazn_studio" / "settings.json"
    # Never store UI state beneath private MEMORY, nor follow a symlink out.
    if any(p.is_symlink() for p in (target, target.parent, target.parent.parent)):
        raise StudioError("Settings path contains a symlink")
    return target


def _parse_json(blob: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, val in pairs:
            if key in result:
                raise StudioError("Duplicate settings key")
            result[key] = val
        return result
    result = json.loads(blob, object_pairs_hook=no_duplicates)
    if not isinstance(result, dict):
        raise StudioError("Settings JSON must be an object")
    return result


def settings_snapshot(root: str | Path) -> tuple[StudioSettings, str | None]:
    path = _settings_file(verified_root(root))
    if not path.is_file():
        return StudioSettings(), None
    raw = path.read_bytes()
    if len(raw) > 16_384:
        raise StudioError("Settings too large")
    return StudioSettings.validate(_parse_json(raw.decode("utf-8-sig"))), sha256(raw).hexdigest()


def write_settings(root: str | Path, settings: StudioSettings, *, expected_sha256: str | None) -> Path:
    """Explicit CAS save; absent file requires expected_sha256=None.

    No secrets, user memory or runtime config files are modified.
    """
    root = verified_root(root)
    validated = StudioSettings.validate(asdict(settings))
    target = _settings_file(root)
    current_sha = sha256(target.read_bytes()).hexdigest() if target.is_file() else None
    if current_sha != expected_sha256:
        raise StudioError("Settings changed on disk; reload first")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise StudioError("Settings path is a symlink")
    data = (json.dumps({"schema": SCHEMA, **asdict(validated)}, ensure_ascii=False,
                       indent=2, sort_keys=True) + "\n").encode("utf-8")
    # schema is the only extra key and never interpreted as an operator option.
    handle, name = tempfile.mkstemp(prefix=".jazn-studio-", suffix=".json", dir=target.parent)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return target


def load_settings(root: str | Path) -> tuple[StudioSettings, str | None]:
    path = _settings_file(verified_root(root))
    if not path.is_file():
        return StudioSettings(), None
    raw = path.read_bytes()
    if len(raw) > 16_384:
        raise StudioError("Settings too large")
    value = _parse_json(raw.decode("utf-8-sig"))
    if value.pop("schema", None) != SCHEMA:
        raise StudioError("Unsupported Jaźń Studio settings schema")
    return StudioSettings.validate(value), sha256(raw).hexdigest()


def _invoke(args: list[str], *, cwd: Path, timeout: int = 15) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            shell=False, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:350]}
    stdout = result.stdout[-1_500_000:]
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = {"stdout_tail": stdout[-1400:]}
    return {
        "ok": result.returncode == 0, "returncode": result.returncode,
        "result": parsed,
        "stderr_tail": result.stderr[-900:],
    }


def run_diagnostic(root: str | Path, command: str, *, python_executable: str | Path | None = None,
                   timeout: int = 15) -> dict[str, Any]:
    source = verified_root(root)
    if command not in ALLOWED_COMMANDS:
        raise StudioError("Command not on read-only diagnostics allowlist")
    interpreter = Path(python_executable or sys.executable).resolve()
    if not interpreter.is_file():
        raise StudioError("Selected Python executable is missing")
    return _invoke(
        [str(interpreter), "-X", "utf8", str(source / "run.py"), *ALLOWED_COMMANDS[command]],
        cwd=source, timeout=timeout,
    )


def probe_http(url: str, *, timeout: int = 8) -> dict[str, Any]:
    """Unauthenticated health/readiness only. Never send bearer tokens."""
    parts = urlsplit(url)
    if parts.scheme == "https":
        origin = _remote_url(f"https://{parts.netloc}")
        if parts.path not in ("/healthz", "/readyz"):
            raise StudioError("Only healthz and readyz may be probed")
        address = origin + parts.path
    elif parts.scheme == "http":
        if parts.hostname not in ("127.0.0.1", "localhost") or parts.port != 8080:
            raise StudioError("Local HTTP probes restricted to port 8080")
        if parts.path not in ("/healthz", "/readyz"):
            raise StudioError("Only healthz and readyz may be probed")
        address = f"http://127.0.0.1:8080{parts.path}"
    else:
        raise StudioError("Unsupported scheme")
    req = Request(address, headers={"Accept": "application/json", "User-Agent": "JaznStudio/1.0"})
    try:
        with urlopen(req, timeout=max(2, min(30, timeout))) as response:
            body = response.read(32_768)
            code = response.status
    except HTTPError as exc:
        code = exc.code
        body = exc.read(32_768)
    except (OSError, URLError) as exc:
        return {"ok": False, "endpoint": address, "error": type(exc).__name__}
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError):
        payload = {}
    # only stable non-sensitive fields; never include headers, tokens or arbitrary contents
    allowed = ("status", "ready", "gateway_live", "mcp_available", "reason", "error",
               "runtime_version", "gateway_instance_id")
    return {"ok": code == 200, "http_status": code, "endpoint": address,
            "status": {k: payload.get(k) for k in allowed if k in payload}}


def _git(root: Path, *argv: str, timeout: int = 10) -> tuple[int, str]:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *argv], capture_output=True, text=True,
            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
            shell=False, timeout=timeout, check=False,
        )
        return done.returncode, done.stdout.strip()[:4096]
    except (OSError, subprocess.TimeoutExpired):
        return 124, ""


def update_plan(root: str | Path) -> dict[str, Any]:
    source = verified_root(root)
    rc, inside = _git(source, "rev-parse", "--is-inside-work-tree")
    if rc or inside != "true":
        return {"ok": False, "reason": "no_git_checkout", "apply_allowed": False}
    checks = {
        "branch": _git(source, "branch", "--show-current")[1],
        "head": _git(source, "rev-parse", "--short", "HEAD")[1],
        "dirty": _git(source, "status", "--porcelain", "--untracked-files=normal")[1],
    }
    rc, diff = _git(source, "rev-list", "--left-right", "--count", "HEAD...origin/master")
    try:
        behind, ahead = map(int, diff.split())
    except (ValueError, TypeError):
        behind = ahead = None
    remote_exists = rc == 0
    lineage_ok = _git(source, "merge-base", "--is-ancestor", "HEAD", "origin/master")[0] == 0
    if checks["branch"] != "master":
        reason = "not_on_master"
    elif checks["dirty"]:
        reason = "dirty_worktree"
    elif not remote_exists:
        reason = "origin_master_not_fetched"
    elif not lineage_ok or ahead != 0:
        reason = "non_fast_forward"
    elif behind == 0:
        reason = "already_up_to_date"
    else:
        reason = "fast_forward_available"
    return {
        "ok": True, "branch": checks["branch"], "head": checks["head"],
        "worktree_clean": not bool(checks["dirty"]),
        "ahead": ahead, "behind": behind, "reason": reason,
        "apply_allowed": reason == "fast_forward_available",
    }


def _is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as channel:
        channel.settimeout(0.4)
        return channel.connect_ex(("127.0.0.1", port)) == 0


def apply_fast_forward(root: str | Path, *, acknowledged_backup: bool = False) -> dict[str, Any]:
    """Never fetch/merge unless explicitly requested by operator action.

    Requires prior manual backup and stopped Jaźń; does not modify MEMORY.
    """
    source = verified_root(root)
    if not acknowledged_backup:
        raise StudioError("Confirm external backup of MEMORY and workspace before update")
    if _is_listening(8787) or _is_listening(8080):
        raise StudioError("Stop Jaźń daemon AND MCP before changing installed code")
    state = update_plan(source)
    if not state.get("apply_allowed"):
        raise StudioError("Update blocked: " + str(state.get("reason")))
    before = _git(source, "rev-parse", "HEAD")[1]
    code, _ = _git(source, "merge", "--ff-only", "origin/master", timeout=90)
    after = _git(source, "rev-parse", "HEAD")[1]
    return {"ok": code == 0 and before != after,
            "previous_head": before, "new_head": after, "mode": "fast_forward_only",
            "reason": "updated" if code == 0 and before != after else "git_merge_failed"}


def fetch_updates(root: str | Path) -> dict[str, Any]:
    source = verified_root(root)
    code, out = _git(source, "fetch", "--no-tags", "origin", "master", timeout=60)
    return {"ok": code == 0, "reason": "fetched" if code == 0 else "fetch_failed",
            "output": out[:300]}


def safe_launcher(root: str | Path, target: str) -> list[str]:
    source = verified_root(root)
    tools = {
        "configuration": source / "tools" / "jazn_config_studio.py",
        "tests": source / "tools" / "jazn_tests_studio.py",
        "memory": source / "tools" / "jazn_memory_studio.py",
    }
    script = tools.get(target)
    if script is None or not script.is_file():
        raise StudioError("Unknown or unavailable canonical Studio: " + str(target))
    return [sys.executable, "-X", "utf8", str(script)]


def studio_snapshot(root: str | Path) -> dict[str, Any]:
    source = verified_root(root)
    config, _ = load_settings(source)
    return {
        "schema": SCHEMA, "studio_version": STUDIO_VERSION,
        "system_package": PACKAGE_VERSION_FULL,
        "root": str(source),
        "settings": asdict(config), "git": update_plan(source),
        "read_only": True,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
