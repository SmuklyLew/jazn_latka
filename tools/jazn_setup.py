"""Operator-owned Jaźń installer; stdlib-only before Dependency Studio handoff.

No daemon lifecycle, MEMORY mutations, public tunnel or automatic network access.
All package resolution, hash verification and installation belong to Dependency Studio.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = ("run.py", "main.py", "pyproject.toml", "AGENTS.md")
SUPPORTED_PYTHONS = {(3, 12), (3, 13), (3, 14)}
MAX_OUTPUT = 1600


class SetupError(RuntimeError):
    """An explicit setup refusal, not a silently recovered install error."""


def _base_python() -> Path:
    """Never install into an ambient v89 or unrelated activated virtualenv."""
    return Path(getattr(sys, "_base_executable", sys.executable)).absolute()


def _venv_path(root: Path) -> Path:
    return root / ".venv"


def _venv_python(root: Path) -> Path:
    return _venv_path(root) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _run(command: Sequence[str], root: Path, *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONUTF8"] = "1"
    env["JAZN_ROOT"] = str(root)
    try:
        return subprocess.run(
            list(command), cwd=root, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupError(f"Cannot execute installer step: {type(exc).__name__}") from exc


def _root_check(root: Path) -> None:
    if root != ROOT:
        raise SetupError("Installer root must be its own SYSTEM directory")
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise SetupError("Incomplete SYSTEM root: " + ", ".join(missing))


def _target() -> dict[str, Any]:
    import platform
    version = sys.version_info[:2]
    platform_name = sys.platform
    supported = (version in SUPPORTED_PYTHONS
                 and platform.machine().lower() in {"amd64", "x86_64"}
                 and (platform_name == "win32" or
                      (platform_name.startswith("linux") and platform.libc_ver()[0] == "glibc")))
    return {
        "python": f"{version[0]}.{version[1]}",
        "base_executable": str(_base_python()),
        "platform": platform_name,
        "architecture": platform.machine(),
        "release_wheelhouse_target_supported": supported,
    }


def _available_profiles(root: Path) -> set[str]:
    registry = root / "latka_jazn/resources/dependencies/profiles.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    return set(data["profiles"])


def _requested_profiles(root: Path, raw: Sequence[str]) -> list[str]:
    choices = _available_profiles(root)
    profiles = ["core"]
    for entry in raw:
        for raw_name in entry.split(","):
            name = raw_name.strip()
            if not name:
                continue
            if name not in choices or name == "all":
                raise SetupError(f"Unsupported dependency profile: {name}")
            if name not in profiles:
                profiles.append(name)
    return profiles


def _probe_venv(root: Path) -> dict[str, Any]:
    venv = _venv_path(root)
    python = _venv_python(root)
    status: dict[str, Any] = {"path": str(venv), "python": str(python), "ready": False}
    if not venv.exists() and not venv.is_symlink():
        status["state"] = "missing"
        return status
    if venv.is_symlink():
        status["state"] = "unsafe_symlink"
        return status
    if not (venv / "pyvenv.cfg").is_file() or not python.is_file():
        status["state"] = "incomplete"
        return status
    code = (
        "import json,sys;"
        "print(json.dumps({'prefix':sys.prefix,'base':sys.base_prefix,"
        "'executable':sys.executable}))"
    )
    run = _run([str(python), "-X", "utf8", "-c", code], root, timeout=15)
    if run.returncode:
        status["state"] = "interpreter_failed"
        return status
    try:
        result = json.loads(run.stdout)
        same = Path(result["prefix"]).resolve() == venv.resolve()
        isolated = result["prefix"] != result["base"]
        correct_entry = Path(result["executable"]).absolute() == python.absolute()
        status["ready"] = bool(same and isolated and correct_entry)
        status["state"] = "ready" if status["ready"] else "wrong_environment"
    except (ValueError, KeyError, TypeError, OSError):
        status["state"] = "invalid_interpreter_response"
    return status


def _operator_python(root: Path) -> Path:
    """Use only the verified project's .venv or a system base interpreter."""
    current = _probe_venv(root)
    return _venv_python(root) if current["ready"] else _base_python()


def _read_declarations(root: Path) -> dict[str, Any]:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    result: dict[str, Any] = {}
    for entry in data.get("project", {}).get("dependencies", []):
        name = re.split(r"[<>=!~\[; ]", entry, maxsplit=1)[0]
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            version = None
        result[name] = {"installed_version_in_invoking_interpreter": version, "requirement": entry}
    return result


def _dependency_studio(root: Path, operation: str, *options: str, timeout: int = 1800) -> dict[str, Any]:
    command = [
        str(_operator_python(root)), "-X", "utf8", "-m",
        "latka_jazn.tools.dependency_studio",
        "--root", str(root), "--json", operation, *options,
    ]
    done = _run(command, root, timeout=timeout)
    try:
        payload = json.loads(done.stdout)
    except (ValueError, TypeError):
        raise SetupError(
            f"Dependency Studio {operation} returned no valid JSON (exit {done.returncode}). "
            "Inspect its diagnostics; the installer will not bypass hash checks."
        ) from None
    if done.returncode or payload.get("ok") is not True:
        reason = str(payload.get("error_type") or payload.get("state") or "not_ready")
        raise SetupError(f"Dependency Studio {operation} failed ({reason}, exit {done.returncode})")
    return payload


def _managed_status(root: Path) -> dict[str, Any]:
    command = [
        str(_operator_python(root)), "-X", "utf8", "-c",
        "import json,sys; from latka_jazn.dependencies.runtime import managed_environment_status;"
        "print(json.dumps(managed_environment_status(sys.argv[1])))", str(root),
    ]
    completed = _run(command, root, timeout=30)
    if completed.returncode:
        return {"ready": False, "status": "managed_probe_unavailable"}
    try:
        return json.loads(completed.stdout)
    except (ValueError, TypeError):
        return {"ready": False, "status": "invalid_managed_probe"}


def _managed_matches(status: dict[str, Any], profiles: Sequence[str]) -> bool:
    if status.get("ready") is not True:
        return False
    configured = set(status.get("resolved_profiles") or status.get("profiles") or [])
    python = status.get("python_executable")
    return (set(profiles).issubset(configured)
            and isinstance(python, str) and Path(python).is_file())


def _create_venv(root: Path) -> dict[str, Any]:
    previous = _probe_venv(root)
    if previous["ready"]:
        return {"created": False, "venv": previous}
    if previous["state"] != "missing":
        raise SetupError(
            f"Existing .venv is {previous['state']}; never overwrite or repair it in place."
        )
    if sys.version_info[:2] not in SUPPORTED_PYTHONS:
        raise SetupError("Supported Python for this release: 3.12, 3.13 or 3.14")
    python = _base_python()
    if not python.is_file():
        raise SetupError("Base Python executable unavailable")
    created = _run([str(python), "-m", "venv", str(_venv_path(root))], root, timeout=180)
    if created.returncode:
        raise SetupError(f"venv creation failed (exit {created.returncode})")
    verified = _probe_venv(root)
    if not verified["ready"]:
        raise SetupError("venv created but interpreter ownership check failed")
    return {"created": True, "venv": verified}


def _confirm(yes: bool, online: bool) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        raise SetupError("Non-interactive mutation requires --yes")
    message = "POBIERZ" if online else "INSTALUJ"
    print(f"Operator action; type {message} to authorize:", file=sys.stderr)
    if input("> ").strip() != message:
        raise SetupError("Operator did not approve the install")


def execute(args: argparse.Namespace) -> dict[str, Any]:
    root = ROOT
    _root_check(root)
    profiles = _requested_profiles(root, args.profile)
    target = _target()
    if args.mode in {"doctor", "preflight"}:
        return {
            "ok": True, "mode": "doctor", "root": str(root), "target": target,
            "local_venv": _probe_venv(root), "core_declarations": _read_declarations(root),
            "managed_environment": (managed := _managed_status(root)),
            "environment_ready": bool(managed.get("ready")),
            "status": "ready" if managed.get("ready") else "requires_setup",
            "note": "Inspection succeeded; environment_ready is independent of daemon/Ollama/MCP.",
        }
    if args.mode == "venv":
        _confirm(args.yes, False)
        return {"ok": True, "mode": "venv", **_create_venv(root)}
    if args.mode == "verify":
        status = _managed_status(root)
        ready = _managed_matches(status, profiles)
        return {
            "ok": ready, "mode": "verify", "profiles": profiles,
            "managed_environment": status, "local_venv": _probe_venv(root),
            "note": "Managed dependency readiness only; daemon and MCP are separate.",
        }
    if args.mode not in {"install", "repair", "online"}:
        raise SetupError("Unsupported setup mode")
    if not target["release_wheelhouse_target_supported"]:
        raise SetupError("Unsupported release wheelhouse target; use supported Windows/Linux x64 and Python 3.12–3.14")
    managed = _managed_status(root)
    if args.mode != "repair" and _managed_matches(managed, profiles):
        return {"ok": True, "mode": "install", "state": "already_ready",
                "python_executable": managed["python_executable"], "profiles": profiles}
    if not args.online and args.mode != "online" and not args.bundle:
        raise SetupError("Supply --bundle (verified wheelhouse), or explicitly choose --online with operator consent")
    online = args.online or args.mode == "online"
    if online and args.bundle:
        raise SetupError("Choose --bundle OR --online, not both")
    _confirm(args.yes, online)
    if online:
        result = _dependency_studio(
            root, "download", "--profile", ",".join(profiles),
            "--platform", "current", "--python-version", target["python"],
            "--python-executable", str(_base_python()), timeout=3600,
        )
        bundle = Path(str(result.get("bundle_dir") or ""))
    else:
        bundle = Path(args.bundle).expanduser()
    if not bundle.is_absolute() or not bundle.is_dir():
        raise SetupError("No wheelhouse bundle available after the download step")
    verification = _dependency_studio(root, "verify", "--bundle", str(bundle))
    installation = _dependency_studio(
        root, "install", "--bundle", str(bundle), "--profile", ",".join(profiles),
        "--python-executable", str(_base_python()), "--offline", timeout=3600,
    )
    python_path = str(installation.get("python_executable") or "")
    if not python_path or not Path(python_path).is_file():
        raise SetupError("Dependency Studio did not return a real managed interpreter")
    status = _managed_status(root)
    if set(profiles).issubset(set(status.get("resolved_profiles") or [])):
        ready = bool(status.get("ready"))
    else:
        # An optional-only environment cannot replace an active core environment.
        ready = bool(installation.get("ok")) and bool(python_path)
    if not ready:
        raise SetupError("Post-install managed environment verification failed")
    return {
        "ok": True, "mode": "install", "state": str(installation.get("state")),
        "profiles": profiles, "python_executable": python_path,
        "bundle": str(bundle), "bundle_verified": verification.get("ok") is True,
        "activation_marker_updated": installation.get("activation_marker_updated") is True,
        "next": {
            "core": f'"{python_path}" -X utf8 run.py host-preflight --json',
            "jss": f'"{python_path}" -X utf8 run_studio.py',
            "mcp": "Configure authenticated MCP transport later in JSS; do not publish loopback-dev.",
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jaźń operator setup (no daemon lifecycle)")
    parser.add_argument("mode", nargs="?", default="doctor",
                        choices=("doctor", "install", "repair", "verify", "venv",
                                 "preflight", "online"))
    parser.add_argument("--profile", action="append", default=[],
                        help="One or more canonical Dependency Studio profiles, comma-separated")
    parser.add_argument("--bundle", default="", help="Exact existing verified wheelhouse directory")
    parser.add_argument("--online", action="store_true", help="Explicit operator-authorized bundle download")
    parser.add_argument("--yes", action="store_true", help="Noninteractive operator approval")
    parser.add_argument("--json", action="store_true", help="Machine-readable result")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = execute(args)
        code = 0 if result.get("ok") is True else 3
    except SetupError as exc:
        code = 2
        result = {"ok": False, "mode": args.mode, "error_type": "SetupError", "reason": str(exc)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        label = ("INSPECTED" if args.mode in {"doctor", "preflight"} and result.get("ok")
                 else "PASS" if result.get("ok") else "BLOCKED")
        print("Jaźń setup:", label)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
