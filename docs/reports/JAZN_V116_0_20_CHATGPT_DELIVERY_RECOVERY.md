# ChatGPT delivery recovery — v116.0.20 target (2026-10-14)

## Problem and evidence

The SYSTEM-only daemon can report `runtime_core_ready=true`, accept host
finalization into `chatgpt_host_bridge/consumed`, yet lose the one-shot
stdout response with `BlockingIOError`. Repeating the finalization then
correctly raises `host_request_replay_detected` (do not relax this check).
A second issue is false detection of persistent MEMORY from transient
operational `memory/sqlite/runtime_write_v1` and bare raw/layered directories.

This fix is scoped to delivery and source selection. It does not grant host
execution or publish an MCP app.

## Implementation

* `core/host_stdout_delivery.py`: bounded complete UTF-8 writes to a
  nonblocking descriptor, partial-write retry, descriptor-mode restoration,
  fail-closed delivery error; never an implicit newline.
* `core/chat_command_contract.py` and `cli.py`: use the same emitter. A
  stdout delivery failure is not a finalization failure.
* `core/chatgpt_host_recovery.py`: read-only delivery recovery from a
  `consumed/commit_accepted` record with verified `request_contract_hash`,
  `turn_id` and `daemon_request_id`. The existing
  `read_committed_host_request` checks the final-text digest and envelope.
  This path does not claim a pending request, regenerate text, change records
  or trigger finalization. A missing contract hash forbids local disclosure.
* `mcp/tools/jazn_resume_visible_reply.py`: prefer the verified committed
  delivery before polling the daemon. Pending/claimed requests continue down
  the established polling/recovery path.
* `memory/availability.py`: an operational DB or a newly created directory
  is not private-memory evidence. Legacy explicit recall files are accepted
  as attachment *candidates*, not as proof of autobiographical readiness.
  Formal MEMORY verification is still required for recall.
* Replay protection remains strict. `host_request_replay_detected` is not
  handled by running the user turn again.

## Bounded test matrix

Run from a clean checkout with Python dependencies installed:

```shell
python -X utf8 -m compileall -q latka_jazn
python -X utf8 -m pytest -q tests/test_v11620_host_delivery_faults.py tests/test_finalization_projection_recovery.py tests/test_optional_memory_attach_convergence.py
python -X utf8 -m pytest -q tests/test_mcp_http_gateway.py tests/test_mcp_ingress_diagnostics.py tests/test_mcp_task_protocol_authorization.py tests/test_mcp_modern_protocol.py tests/test_mcp_connector_status_probe_contract.py tests/test_transport_resilience_fault_injection.py
python -X utf8 -m pytest -q tests --ignore=tests/archive
pyright
```

Regression cases include: UTF-8 fragmentation, a slow pipe reader, a pipe
that never drains (bounded timeout), a consumed capture returned without
access to the daemon, wrong request hash, wrong turn ID, tampered capture,
original replay protection and runtime-created MEMORY artifacts.

A failed or interrupted suite is **not** proof of a full pass. The stdout
writer protects the child; the *host* must consume only complete framed
JSONL records, otherwise an interrupted frame may be partially rendered.

## MCP deployment / platform boundary

Local stdio and a SYSTEM ZIP cannot make tools callable in ChatGPT. The
`jazn_status`, `jazn_generate_visible_reply`,
`jazn_resume_visible_reply`, `jazn_finalize_reply` toolset must be
exposed by an actually connected, authorized remote MCP app for the
current ChatGPT message. The existing `deploy/chatgpt_mcp` gateway is
still a separate operator deployment.

Checklist:
1. Deploy an authenticated HTTPS MCP endpoint or supported Secure MCP
   Tunnel on an always-on host; do not expose localhost without auth.
2. Confirm `/healthz`, `/readyz`, protocol revision and per-tool auth,
   including `tools/list` on the deployed endpoint.
3. Register/test the app through available ChatGPT plan/workspace
   capabilities, with explicit operator authorization.
4. Verify all four tools are **callable in the current message**,
   then perform one normal turn, a forced transport disconnect and
   `jazn_resume_visible_reply` against the same request/hash.
5. Restart the ChatGPT client; verify continuity through the remote
   daemon and separate native MEMORY readiness.

The packaged implementation cannot by itself supply a public endpoint,
install an app on an account or prove a remote deployment.

## Sources

* Python: https://docs.python.org/3/library/os.html#os.write
* Python I/O: https://docs.python.org/3/library/io.html
* MCP 2026-07-28: https://modelcontextprotocol.io/specification/2026-07-28
* ChatGPT developer mode: https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt
