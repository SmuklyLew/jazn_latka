# Jaźń v16.3.25.5.115.18.2 — MCP ingress diagnosis and job recovery

This patch targets connection observability; it does **not** create an OpenAI app
connection, deploy OAuth, publish a public endpoint, or make Android/ChatGPT
expose tools automatically.

## Baseline and Codex comparison

- Baseline: master commit `48168b74ccfce42318c2568fbc78433c6051a0d5`.
- Compared Codex branches `codex/jazn-studio-pamieci` and
  `codex/jazn-studio-pamieci-v80-4-private-checkpoint-20260923`.
- Both branches diverge significantly from master and concern Memory Studio.
  This scoped MCP patch therefore starts from current master rather than
  importing their unrelated historical snapshot or overwriting their memory work.
- Persistent memory and its private data are untouched.

## Local checks

Start Jaźń daemon through canonical run.py/main.py and run this **read-only**
MCP diagnostic before attempting to bind any ChatGPT plugin:

```powershell
py run.py mcp-probe --url http://127.0.0.1:8080/mcp --json
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 8080,8787,8788 } | Select LocalPort,OwningProcess
```

If `mcp_path_missing_or_wrong_service` occurs, port 8080 can be occupied by
a different application. Choose a free port for the dedicated MCP gateway:

```powershell
py run.py mcp-http --loopback-dev --host 127.0.0.1 --port 8788 --daemon-url http://127.0.0.1:8787
py run.py mcp-probe --url http://127.0.0.1:8788/mcp --json
```

This check uses JSON-RPC `initialize` and **does not** prove `tools/list`,
ChatGPT tool exposure, an authenticated session, or an accepted visible Jaźń
turn. A 401 indicates an auth challenge, not readiness. For SSE or production
OAuth use MCP Inspector / an actual authenticated MCP client. Verify all four
canonical tool names with `tools/list` and test `jazn_status` before any
user message. Do not send private MEMORY over unauthenticated dev ingress.

## Public deployment

A real remote ChatGPT client requires a configured reachable HTTPS MCP URL,
valid OAuth resource server, and actual per-message tool exposure. Do not
put `127.0.0.1` in a plugin intended for cloud or Android invocation. Do not
publish `--loopback-dev` on a public interface or through an open tunnel.
Use canonical `chatgpt-plugin-package --endpoint https://.../mcp` only after
gateway HTTPS and authentication pass independently.

## Submit and recovery

Once a daemon submit explicitly acknowledges acceptance, a later
`chat_job_not_found` is diagnosed as `acknowledged_job_missing_from_daemon`.
The response reports the same submitted request ID and requires fail-closed
operator diagnosis; no user-message replay or route switching is allowed.
Check daemon instance ID, persistent job store, queue counters and TTL.
This is a diagnostic refinement, not proof of why the prior job vanished.

## Required release gates

- `python -X utf8 -m compileall -q latka_jazn tests main.py run.py`
- `python -X utf8 -m pytest -q tests/test_mcp_ingress_diagnostics.py tests/test_mcp_http_cli.py tests/test_chatgpt_transport_timeout_mcp_idempotency.py`
- project-wide deterministic tests, Pyright, doctor, package-smoke
- canonical `release_metadata_sync --root . --base-branch master --write --json`
- GitHub Actions and an authenticated end-to-end MCP handshake

A remote branch and passing unit tests alone are not a release candidate.
