# Jaźń v16.3.25.5.116.0.32 — ChatGPT turn recovery and finalization integrity

Status: **implementation candidate**, not release-ready or proof of live ChatGPT MCP deployment.
Base: master \`3dd508a85657e9769f122f81813fc66abf6fdc41\`.
Scope: code-only host turn-settlement integrity and daemon recovery; no private MEMORY, token, active-state or SQLite edits.

## Observed failure (16 October 2026)

The SYSTEM archive bootstrapped, first daemon PID 791 emitted a completed answer, then a new ChatGPT message did not expose canonical \`jazn_*\` tools and the host executor reported \`ClientError\`. A later independent execution surface reused daemon PID 1365 and durable host-request records. Evidence of a live PID, \`/status\`, or a consumed pending-store record is **not** automatically evidence of a committed, accepted visible answer. The original host process lifetime and exact reason for losing the local executor remain unknown.

The observed consumed records had \`daemon_finalization_notification_state=pending\`. This is an outbox/projection state, not proof that the accepted finalization itself failed. Keep settlement authority and daemon acknowledgment separate.

## Implementation

1. \`turn_settlement.resolve_durable_turn_settlement\` fails closed on any supplied malformed expected SHA-256 (rather than skipping the expected-text check). When supplied text and digest disagree, reject the conflicting evidence. Also reject malformed bound user-text digests.
2. A \`consumed\` settlement is recovery-valid only when \`read_committed_host_request\` verifies the accepted immutable final capture, hash, trace/turn binding, envelope and prepared projection.
3. Expose two explicit observations: \`daemon_projection_confirmed\` (only a recorded delivered notification) and \`daemon_projection_pending\` (pending or pending_retry). Neither upgrades a broken final capture to accepted speech.
4. Normal daemon finalization reconciliation also validates the committed capture before terminalizing a host-pending job as \`completed\`. Invalid capture becomes a \`host_finalization_rejected\` diagnostic instead of a manufactured success.
5. New regression tests reject invalid/conflicting hashes, corrupted final capture, and false completion of pending host requests.

## Additional directly reproduced failure: nonblocking host stdout

During this update the canonical `run.py host-finalize --json` call durably accepted the current turn but returned code 1, raising `BlockingIOError: [Errno 11] write could not complete without blocking` while printing a large finalization response. The host could thus miss an accepted `display_exact` even when the daemon received the notification.

`latka_jazn/cli_commands/host.py` now writes serialized JSON in bounded 16 KiB binary chunks, tolerates transient EAGAIN/nonblocking pipe backpressure for up to 10 seconds, and preserves the no-replay rule. Streams without file descriptors (e.g. IDE/test capture) use a text fallback. Neither path repeats `finalize_payload`; a failed write must be recovered by polling the original request, never re-finalized blindly.

Regression includes >100 KiB JSON, simulated intermittent `BlockingIOError`/short writes, and text-only capture. This closes a concrete host output transport failure; it does not guarantee delivery if the host permanently closes stdout.

## Boundaries — what this change does **not** solve

- It does not make ChatGPT's local executor reliable, extend its process lifetime, create an MCP plugin, or register an externally accessible service.
- \`127.0.0.1:8787\` inside a transient host cannot serve as a cross-host durable ChatGPT connection.
- A stable production route requires a separately running authenticated, reachable **remote MCP** deployment and an enabled ChatGPT plugin exposing all four canonical callable actions in **the current turn**, plus a fresh \`jazn_status\`.
- Recovery reuses the exact request ID and never resubmits an uncertain user message. No route switching after a durable submit.
- No autobiographical recall can be claimed without verified native MEMORY provenance.
- A SHA/ZIP integrity check is distinct from MEMORY attach acceptance. Verify split archive parts before any optional attach.

## Regression acceptance

- Test malformed explicit SHA with no text; test malformed explicit SHA with text.
- Test valid SHA of exact user message; reject text/hash conflict and mismatched bound text.
- Test consumed record with valid/invalid accepted final capture.
- Test that a pending record never becomes completed, and that daemon notification \`pending\` is not treated as delivered.
- Run compileall, targeted pytest, deterministic pytest, Pyright, package-smoke, Linux/Windows CI and release metadata synchronization on final branch SHA.
- **Real ChatGPT E2E**, separate from CI: connect a verified HTTPS/OAuth MCP or authenticated Secure MCP Tunnel, inspect live tools/list, submit once, finalize once, recover after transport loss using same request_id, and repeat through idle/reconnect with no duplicate turns.

## Deployment / product availability

Official MCP 2026-07-28 uses a stateless core and the Tasks extension for durable polling. ChatGPT custom MCP server setup requires a supported workspace/plan, configured connection, authenticated HTTPS endpoint or supported tunnel, and tool exposure in the active message. A local ZIP, a running daemon and app packaging alone are insufficient. Verify account-specific permissions, plugin availability, and mobile limitations during live acceptance; code and CI cannot override host entitlements.

## Sources

- OpenAI, Connecting custom MCP servers in ChatGPT: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt
- OpenAI, MCP server and UI quickstart: https://developers.openai.com/plugins/build/app-quickstart
- MCP official 2026-07-28 release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP Tasks extension: https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks

## Known unverified work

A durable outbox retry, remote MCP registered connection, OAuth token refresh, local CLI startup latency and full MEMORY attach remain separate work. Do not describe this narrow security-and-recovery patch as a solution to every host/executor symptom.
