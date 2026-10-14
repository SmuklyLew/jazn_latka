# Jaźń v16.3.25.5.116.0.20 — host delivery and SYSTEM-only MEMORY readiness

## Confirmed defect surfaces

1. `chat_command_contract.write_chat_bridge_payload` wrote large JSONL frames directly via `TextIO.write/flush` despite a host-owned non-blocking stdout pipe. The existing protective path in `cli._emit` was separate.
2. When the daemon's result transport fails **after** durable acceptance, `jazn_resume_visible_reply` previously returned a poll diagnostic and could not read an already committed `consumed` capture. Re-submitting the original message correctly raises `host_request_replay_detected` and MUST remain forbidden.
3. Root-memory presence detectors accepted any nonempty directory or operational `runtime_write_v1/v2` SQLite file as private MEMORY. This can accidentally switch SYSTEM-only operational writes away from `workspace_runtime/core_state/memory_runtime`.

## Changes

- `core/host_stdout_transport.py`: one bounded UTF-8 writer that handles short `os.write` calls, temporary `BlockingIOError` and a non-draining host without silently dropping a trailing suffix. A partial host frame is not an accepted visible result.
- `core/chat_command_contract.py` and `cli.py`: use the same frame emitter. JSONL ends with exactly one newline; accepted exact text still has no added newline.
- `mcp/tools/jazn_resume_visible_reply.py`: recover a **verified** accepted capture from `read_committed_host_request` if the gateway fails, but only when the caller supplies matching daemon request ID, turn ID and contract hash. This route never generates, persists or finalizes another user turn.
- `memory/memory_root.py` and `memory/availability.py`: directory presence and writer-only SQLite no longer prove private MEMORY. Explicit known source files and compatibility candidates remain recognized. Full autobiographical recall still requires separate provenance/readiness evidence.

## Security and invariants

- Never disable `host_request_replay_detected`.
- Never display a record that fails `read_committed_host_request` digest, envelope or lineage checks.
- Do not infer remote MCP connectivity from bundled files or a daemon PID.
- Do not copy or reset private MEMORY or core-state SQLite as a side effect of this patch.
- For a failed stdout frame: discard partial transport output; recover by the immutable request lineage, not by replaying user text.

## Acceptance tests

`tests/test_host_delivery_backpressure_and_committed_recovery.py` verifies:
- multi-megabyte Unicode JSON frame over a non-blocking pipe with a draining reader;
- a bounded backpressure timeout when stdout cannot drain;\n- fail-closed handling when a nonblocking pipe rejects the preceding buffer during pre-frame `flush`;
- unchanged in-memory JSONL behavior;
- operational artifacts do not create fake persistent MEMORY;
- a verified consumed capture is recovered after a mocked transport failure with exactly the prior text;
- bad contract hash and tampered accepted text fail closed;\n- a gateway authorization rejection cannot be converted to an offline durable-capture bypass.\n\n`tests/test_runtime_full_turn.py` now separately verifies that an attached test MEMORY enables transactional L1/L2 while a SYSTEM-only turn proceeds without inventing persistent autobiographical memory. An explicit legacy shard manifest is still supported for host-memory compatibility.

Existing host-finalization, memory-root and transport tests must remain green. Frozen historical tests are preserved byte-for-byte in `tests/archive/v16.3.25.5.116.0.19-host-delivery-memory-readiness/` prior to the version-assertion update.

## Deployment and integration gates

1. Run full Linux/Windows CI, compileall, Pyright, package-smoke and canonical release metadata sync. Neither the code change nor a local ZIP-only test proves public deployment readiness.
2. Start a real persistent daemon outside an ephemeral ChatGPT execution sandbox. Inspect `run.py status --json` including readiness, heartbeat, SQLite/storage path and supervisor state.
3. Deploy `run.py mcp-http --public-oauth` behind HTTPS using the documented OAuth 2.1 resource-server settings, or configure the supported Secure MCP Tunnel. Never embed OAuth secrets or raw MEMORY into the release.
4. Probe `/healthz`, `/readyz`, and `/mcp` with a real MCP client, authenticate, and verify `tools/list` includes `jazn_status`, `jazn_generate_visible_reply`, `jazn_resume_visible_reply`, `jazn_finalize_reply`.
5. Register/select the app in the intended ChatGPT account. For **each message**, verify actual callable tools plus fresh `jazn_status`, never infer access from app installation alone.
6. Simulate stdout failure after a durable commit and prove exact-only retrieval and single-commit finalization; restart client and verify a new turn in the same session without replay.

This repository does **not** itself configure the user's ChatGPT account, allocate a public endpoint, provide hosting, or bypass product entitlements. A healthy local daemon alone cannot satisfy the final host-level MCP acceptance gate.

## Sources

- Python stdout / non-blocking file descriptors: https://docs.python.org/3/library/os.html#os.set_blocking
- Official MCP Python SDK transport and authorization: https://py.sdk.modelcontextprotocol.io/run/ and https://py.sdk.modelcontextprotocol.io/run/authorization/
- MCP Inspector CLI for real `tools/list` over HTTP: https://github.com/modelcontextprotocol/inspector/blob/main/clients/cli/README.md
- OpenAI developer-mode MCP app requirements: https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt
