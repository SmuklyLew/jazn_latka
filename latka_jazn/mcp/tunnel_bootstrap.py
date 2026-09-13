from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

# This file is intentionally executable by absolute path from OpenAI's
# tunnel-client.  Add the package root before importing Jaźń modules so the
# bridge works from a clean extracted SYSTEM package without installation.
_DEFAULT_ROOT = Path(__file__).resolve().parents[2]
if str(_DEFAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(_DEFAULT_ROOT))

from latka_jazn.config import JaznConfig
from latka_jazn.core.daemon_autostart import DaemonEnsureResult, ensure_daemon_for_runtime_turn
from latka_jazn.mcp.server import JaznMcpServer
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("secure_mcp_tunnel_bootstrap")
DEFAULT_DAEMON_URL = "http://127.0.0.1:8787"


class TunnelBootstrapError(RuntimeError):
    """Fail-closed bootstrap error that is safe to report on stderr."""


def _stderr_event(event: str, **details: Any) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION_FULL,
        "event": event,
        **details,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str), file=sys.stderr, flush=True)


def _resolve_verified_active_root(requested_root: Path, ensured: DaemonEnsureResult) -> Path:
    if not ensured.ok or not ensured.ensured:
        raise TunnelBootstrapError(f"runtime_not_ready:{ensured.reason}")
    if not ensured.daemon_identity_verified:
        raise TunnelBootstrapError("daemon_identity_not_verified")
    raw_root = str(ensured.resolved_active_root or "").strip()
    if not raw_root:
        raise TunnelBootstrapError("resolved_active_root_missing")
    active_root = Path(raw_root).expanduser()
    if not active_root.is_absolute():
        raise TunnelBootstrapError("resolved_active_root_not_absolute")
    active_root = active_root.resolve()
    if not active_root.is_dir():
        raise TunnelBootstrapError("resolved_active_root_not_directory")
    # The daemon may legitimately resolve a package-local requested root to the
    # canonical active subject root.  We therefore do not require path equality;
    # the identity check above is the authority for that transition.
    if not requested_root.is_absolute():
        raise TunnelBootstrapError("requested_root_not_absolute")
    return active_root


def ensure_tunnel_runtime(
    root: Path,
    *,
    startup_timeout: float | None = None,
) -> tuple[Path, DaemonEnsureResult]:
    requested_root = Path(root).expanduser().resolve()
    kwargs: dict[str, Any] = {
        "command": "secure_mcp_tunnel",
        "explicit_ensure": True,
    }
    if startup_timeout is not None:
        kwargs["startup_timeout"] = float(startup_timeout)
    ensured = ensure_daemon_for_runtime_turn(JaznConfig(root=requested_root), **kwargs)
    return _resolve_verified_active_root(requested_root, ensured), ensured


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verified stdio target for OpenAI Secure MCP Tunnel. Ensures one persistent Jaźń runtime "
            "and then delegates the protocol to the canonical private MCP server."
        )
    )
    parser.add_argument("--root", default=str(_DEFAULT_ROOT))
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL)
    parser.add_argument("--startup-timeout", type=float, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    requested_root = Path(args.root).expanduser().resolve()
    try:
        active_root, ensured = ensure_tunnel_runtime(
            requested_root,
            startup_timeout=args.startup_timeout,
        )
    except (TunnelBootstrapError, OSError, RuntimeError, ValueError) as exc:
        _stderr_event(
            "secure_mcp_tunnel_bootstrap_failed",
            ok=False,
            error_type=type(exc).__name__,
            error=str(exc),
            requested_root=str(requested_root),
            truth_boundary=(
                "The MCP server was not exposed because a verified persistent Jaźń runtime could not be established."
            ),
        )
        return 78

    _stderr_event(
        "secure_mcp_tunnel_runtime_ready",
        ok=True,
        requested_root=str(requested_root),
        active_root=str(active_root),
        daemon_pid=ensured.daemon_pid,
        daemon_reused=ensured.daemon_reused,
        daemon_started=ensured.daemon_started,
        transport="openai_secure_mcp_tunnel_stdio",
        truth_boundary=(
            "This event proves local runtime and stdio-target readiness only. Remote tunnel/control-plane readiness "
            "and each accepted visible turn require their own evidence."
        ),
    )
    server = JaznMcpServer(
        root=active_root,
        daemon_url=str(args.daemon_url),
        trust_stdio_parent=True,
    )
    return server.serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
