from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from typing import Any, Sequence


MINIMUM_NODE_MAJOR = 24
CI_NODE_MAJOR = 24
_NODE_VERSION_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:[-+].*)?$"
)
_ESM_PROBE = r"""
const awaited = await Promise.resolve("esm");
const major = Number(process.versions.node.split(".", 1)[0]);
const payload = {
  ok: awaited === "esm" && typeof structuredClone === "function",
  runtime: process.release?.name ?? "",
  version: process.versions.node,
  major,
  esm: typeof import.meta.url === "string" && import.meta.url.length > 0
};
console.log(JSON.stringify(payload));
if (!payload.ok) process.exitCode = 2;
""".strip()


def parse_node_version(value: str) -> tuple[int, int, int] | None:
    """Parse the ordinary ``node --version`` representation."""

    match = _NODE_VERSION_RE.fullmatch(str(value or "").strip())
    if match is None:
        return None
    return tuple(int(match.group(name)) for name in ("major", "minor", "patch"))


def inspect_javascript_runtime(
    node_executable: str | None = None,
    *,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Inspect the optional Node/JavaScript capability without making it mandatory.

    The Python runtime remains canonical.  This probe never installs Node, never
    uses a shell, and never contacts the network.  Node 24 is the CI-tested LTS
    line; newer majors can be reported as supported but are not called tested.
    """

    requested = str(node_executable or "node").strip() or "node"
    resolved = (
        shutil.which(requested)
        if node_executable is None
        else shutil.which(requested) or requested
    )
    base: dict[str, Any] = {
        "ok": False,
        "available": False,
        "supported": False,
        "tested_line": False,
        "minimum_node_major": MINIMUM_NODE_MAJOR,
        "ci_node_major": CI_NODE_MAJOR,
        "requested_executable": requested,
        "executable": resolved,
        "version": None,
        "major": None,
        "probe": None,
        "reason": "node_not_found",
    }
    if not resolved:
        return base

    timeout = max(0.1, float(timeout_seconds))
    try:
        version_result = subprocess.run(
            [resolved, "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        base["reason"] = f"node_version_probe_failed:{type(exc).__name__}"
        return base

    version_text = (version_result.stdout or version_result.stderr or "").strip()
    parsed = parse_node_version(version_text)
    base["available"] = version_result.returncode == 0 and parsed is not None
    base["version"] = version_text or None
    if not base["available"] or parsed is None:
        base["reason"] = "node_version_invalid"
        return base

    major = parsed[0]
    base["major"] = major
    base["supported"] = major >= MINIMUM_NODE_MAJOR
    base["tested_line"] = major == CI_NODE_MAJOR
    if not base["supported"]:
        base["reason"] = "node_major_below_minimum"
        return base

    try:
        probe_result = subprocess.run(
            [resolved, "--input-type=module", "--eval", _ESM_PROBE],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        base["reason"] = f"node_esm_probe_failed:{type(exc).__name__}"
        return base

    probe_payload: dict[str, Any] | None = None
    if probe_result.stdout.strip():
        try:
            decoded = json.loads(probe_result.stdout.strip().splitlines()[-1])
            if isinstance(decoded, dict):
                probe_payload = decoded
        except json.JSONDecodeError:
            probe_payload = None
    base["probe"] = probe_payload
    probe_ok = bool(
        probe_result.returncode == 0
        and probe_payload
        and probe_payload.get("ok") is True
        and probe_payload.get("runtime") == "node"
        and int(probe_payload.get("major") or -1) == major
        and probe_payload.get("esm") is True
    )
    base["ok"] = bool(base["supported"] and probe_ok)
    base["reason"] = "ok" if base["ok"] else "node_esm_probe_failed"
    return base


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m latka_jazn.tools.javascript_runtime",
        description="Inspect the optional JavaScript/Node capability used by Jaźń tooling.",
        allow_abbrev=False,
    )
    parser.add_argument("--node", help="Explicit Node.js executable or command name.")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--require-node24",
        action="store_true",
        help="Fail unless the detected runtime is the CI-tested Node 24 line.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    payload = inspect_javascript_runtime(args.node, timeout_seconds=args.timeout_seconds)
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        version = payload.get("version") or "missing"
        print(
            "JavaScript runtime: "
            f"{payload.get('reason')} (node={version}, supported={payload.get('supported')}, "
            f"tested_line={payload.get('tested_line')})"
        )
    if not args.require_node24:
        return 0
    return 0 if payload.get("ok") is True and payload.get("tested_line") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
