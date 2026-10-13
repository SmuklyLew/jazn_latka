from __future__ import annotations

"""Exercise one isolated Jaźń MCP fixture with a pinned upstream conformance CLI.

Never connects to a public endpoint or private MEMORY. Exit status propagates
unchanged; all server and test output is saved for review.
"""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conformance", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--scenario", default="")
    parser.add_argument("--port", type=int, default=18796)
    options = parser.parse_args()
    if not 1024 <= options.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    project = Path(__file__).resolve().parents[1]
    cli = options.conformance.resolve()
    if not cli.is_file() or cli.suffix != ".js":
        parser.error("pinned conformance CLI must be a built JS file")
    out = options.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1")
    command = [
        sys.executable, "-X", "utf8", str(project / "run.py"),
        "mcp-http", "--root", str(project), "--loopback-dev",
        "--host", "127.0.0.1", "--port", str(options.port),
    ]
    with (out / "server.log").open("wb") as output:
        server = subprocess.Popen(
            command, cwd=project, env=env, stdout=output, stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError(f"MCP loopback process exited: {server.returncode}")
                try:
                    with socket.create_connection(("127.0.0.1", options.port), timeout=0.4):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("MCP loopback fixture readiness timed out")
            conformance = [
                "node", str(cli), "server",
                "--url", f"http://127.0.0.1:{options.port}/mcp",
                "--verbose",
            ]
            conformance.extend(
                ["--scenario", options.scenario] if options.scenario
                else ["--requirements", "2026-07-28"]
            )
            with (out / "conformance.log").open("wb") as report:
                result = subprocess.run(
                    conformance, cwd=project, env=env,
                    stdout=report, stderr=subprocess.STDOUT,
                    timeout=600, check=False,
                )
            print(f"MCP conformance exit={result.returncode}", flush=True)
            # The upstream CLI writes diagnostics into an artifact. Preserve
            # that artifact, but also expose bounded failure evidence in job
            # output: otherwise CI shows only exit=1 with no actionable cause.
            if result.returncode != 0:
                report_path = out / "conformance.log"
                try:
                    raw = report_path.read_text(encoding="utf-8", errors="replace")
                    import re

                    # Do not disclose bearer tokens while surfacing check IDs.
                    raw = re.sub(
                        r"(?i)(bearer\\s+)[A-Za-z0-9._~+/-]+",
                        r"\\1[REDACTED]",
                        raw,
                    )
                    lines = raw.splitlines()
                    keywords = ("FAILURE", "FAILED", "Error:", "errorMessage",
                                "✗", "❌", "not passed", "fail:")
                    failures = [line for line in lines if any(key in line for key in keywords)]
                    print("=== MCP conformance failure evidence (bounded) ===", flush=True)
                    for line in (failures[-110:] or lines[-70:]):
                        print(line[:600], flush=True)
                    print("=== End MCP conformance failure evidence ===", flush=True)
                except OSError as exc:
                    print(f"Conformance report unreadable: {type(exc).__name__}", flush=True)
            return result.returncode
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
