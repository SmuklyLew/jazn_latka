# Jaźń: bounded operator executor (v16.3.25.5.116.0.34.24)

This is a host-local diagnostic capability, not an arbitrary shell and not
an attempt to install an executor into ChatGPT. A working process host is a
prerequisite. The canonical command owner remains main.py, reached through
the thin run.py starter. It is independent of model provider (ChatGPT or
Ollama), and uses the current Python interpreter on Windows or Unix.

## Usage

Windows PowerShell:

    py -X utf8 run.py operator-exec --action version --include-output --json
    py -X utf8 run.py operator-exec --action doctor --timeout-seconds 20 --json

Unix terminal:

    python3 -X utf8 run.py operator-exec --action status --timeout-seconds 20 --json
    python3 -X utf8 run.py operator-exec --action model-status --json

status, doctor, model-status, and version are the only accepted actions;
arguments cannot be appended, and no shell command is interpreted.
Timeout must be between 0.1 and 30 seconds. The child runs using Python
subprocess.Popen with shell=False. Result output is omitted by default,
with optional UTF-8 capture capped at 32 KiB/stream and full SHA-256 retained.
The runner does not access or install private MEMORY, fetch dependencies,
modify Git, or start the daemon. Timeout, spawn error and nonzero command
exit have distinct statuses. Runtime readiness is not inferred from process
creation or exit code alone.

## Evidence and deployment boundary

- process_created: only true after Popen returns a child PID.
- command_completed: only true when wait returned normally.
- ok: only true when the child exited 0.
- host_process_spawn_failed: OS process boundary, not an invalid ZIP.
- operator_action_timeout: an existing child exceeded the bounded budget.
- truth_boundary: execution does not verify jazn_status, a remote
  MCP connector, session lineage, MEMORY or accepted display_exact turn.

Do not expose this API as an unauthenticated or generic MCP shell tool.
To execute these operations from ChatGPT, deploy and authenticate the existing
Jaźń MCP server and bind actual callable tools in the current message. The
MCP host must explicitly provide tool access; this package cannot inject an
executor into ChatGPT. No change is made to MCP tool lists in this patch.
Windows acceptance and ChatGPT connector E2E must be confirmed separately.

## Sources

- Python subprocess security:
  https://docs.python.org/3/library/subprocess.html#security-considerations
- OpenAI MCP server auth and least privilege:
  https://developers.openai.com/plugins/build/mcp-server
- OpenAI local stdio MCP limits:
  https://developers.openai.com/plugins/deploy/desktop-only
- MCP 2026 protocol:
  https://modelcontextprotocol.io/specification/2026-07-28
