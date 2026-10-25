"""Minimal Jaźń first-run operator preflight, never an alternate runtime.

A default invocation is read-only, offline, and does not claim daemon, model,
memory or remote MCP readiness. Profile creation requires explicit opt-in.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.util import find_spec
import json
from pathlib import Path
import sys
from typing import Any
from urllib import request

from latka_jazn.core.telemetry_evidence import sample_host_memory
from latka_jazn.tools.configuration_studio import (
    profile_file, profile_snapshot, save_profile, system_root,
)

LOCAL_OLLAMA = "http://127.0.0.1:11434"
FUTURE_PROFILE = {"JAZN_LLM_ROUTE": "local", "JAZN_MEMORY_MODE": "optional"}
REQUIRED_MCP_IMPORTS = ("mcp", "pydantic", "starlette", "uvicorn")


def _probe_ollama(url: str = LOCAL_OLLAMA, *, timeout: float = 2.5) -> dict[str, Any]:
    # Caller explicitly opted into local network; never issue arbitrary URLs.
    if url != LOCAL_OLLAMA:
        raise ValueError("ollama_probe_only_allows_127_0_0_1_11434")
    result: dict[str, Any] = {"source": url, "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                              "status": "unreachable", "installed_models": None, "loaded_models": None}
    opener = request.build_opener(request.ProxyHandler({}))
    try:
        values: dict[str, Any] = {}
        for endpoint in ("/api/tags", "/api/ps"):
            with opener.open(url + endpoint, timeout=timeout) as response:
                data = json.loads(response.read(131072).decode("utf-8"))
                if int(response.status) != 200 or not isinstance(data, dict):
                    raise ValueError("invalid_ollama_response")
                values[endpoint] = data
        listed = values["/api/tags"].get("models")
        running = values["/api/ps"].get("models")
        if not isinstance(listed, (list, dict)) or not isinstance(running, (list, dict)):
            raise ValueError("invalid_ollama_model_lists")
        result.update(
            status="observed",
            installed_models=len(listed),
            loaded_models=len(running),
            model_unloaded_is_not_error=len(running) == 0,
            generation_verified=False,
        )
    except (OSError, ValueError, TimeoutError, json.JSONDecodeError):
        result["status"] = "probe_failed"
    return result


def inspect_minimal_setup(root: Path, *, probe_ollama: bool = False, probe_ram: bool = False) -> dict[str, Any]:
    root = system_root(root)
    dependencies = {name: find_spec(name) is not None for name in REQUIRED_MCP_IMPORTS}
    profile, digest = profile_snapshot(root)
    return {
        "schema_version": "jazn_minimal_setup_preflight/v1",
        "system_root": str(root),
        "system_verified": True,
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "dependencies": dependencies,
        "mcp_dependencies_importable": all(dependencies.values()),
        "future_profile_path": str(profile_file(root)),
        "future_profile_present": digest is not None,
        "future_profile_overrides": sorted(profile),
        "recommended_future_profile": dict(FUTURE_PROFILE),
        "ollama": _probe_ollama() if probe_ollama else {"status": "not_probed", "source": None},
        "ram": sample_host_memory() if probe_ram else {"status": "not_probed", "physical_ram_percent_used": None},
        "daemon_ready_verified": False,
        "mcp_tools_verified": False,
        "oauth_ready_verified": False,
        "memory_continuity_verified": False,
        "accepted_turn_verified": False,
        "read_only": True,
        "truth_boundary": (
            "Read-only first-run preflight. Python imports, file paths, and "
            "Ollama /api/ps do not prove model generation, daemon readiness, "
            "autobiographical continuity or a finalized visible Jaźń turn."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jaźń minimal first-run safety preflight")
    parser.add_argument("--root", default=".", help="Verified SYSTEM root")
    parser.add_argument("--probe-ollama", action="store_true",
                        help="Opt-in local /api/tags and /api/ps observation")
    parser.add_argument("--probe-ram", action="store_true",
                        help="Opt-in current host OS RAM measurement with source")
    parser.add_argument("--create-profile", action="store_true",
                        help="Explicitly create missing future-run operator profile; never overwrite")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = system_root(Path(args.root))
    if args.create_profile:
        _, digest = profile_snapshot(root)
        if digest is not None:
            parser.error("operator profile exists; no silent overwrite")
        save_profile(root, FUTURE_PROFILE, expected_sha256=None)
    report = inspect_minimal_setup(root, probe_ollama=args.probe_ollama, probe_ram=args.probe_ram)
    if args.create_profile:
        report["read_only"] = False
        report["profile_created"] = True
        report["daemon_ready_verified"] = False
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) if args.json
          else f"Jaźń minimal setup: SYSTEM verified, MCP dependencies={report['mcp_dependencies_importable']}, "
               f"future profile present={report['future_profile_present']}; no runtime activated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
