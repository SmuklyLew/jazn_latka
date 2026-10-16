# Jaźń / ChatGPT runtime reliability acceptance — v16.3.25.5.116.0.34.5

**Status:** evidence-backed implementation plan and measurable acceptance matrix.
**Prepared:** 2026-10-16. A plan, GitHub CI or plugin package is *not*
an activated runtime, current-message callable app or accepted visible turn.

## What the repository already implements

- Canonical launcher and lifecycle: `run.py -> main.py`, persistent daemon,
  supervisor identity and heartbeat lease, `status --json`.
- ChatGPT hybrid/adaptive ingress: first require complete current-message
  `jazn_*` toolset and real `jazn_status`; otherwise one primary and
  at most one *independent* alternative local process probe, with separate
  evidence of filesystem, SYSTEM and remote capabilities.
- Remote transport: MCP 2026-07-28, public OAuth-protected Streamable HTTP
  or separately configured Secure MCP Tunnel. Auth and public internet
  reachability are *external* deployment facts, not properties of a ZIP.
- Request lineage: stable session/request/turn/trace, no resubmission on
  ambiguous transport, `poll_runtime`/resume of the same request, and
  exact accepted `display_exact` as the only visible output authority.
- SYSTEM and MEMORY are independent packages; core readiness does not
  imply autobiographical continuity. Avoid false memory claims.

Sources of project truth: `AGENTS.md`, `AGENTS.chatgpt.md`,
`docs/runtime/CHATGPT_MCP_CONNECTION_RECOVERY.md`,
`docs/runtime/TURN_FINALIZATION_CONTRACTS.md`,
`docs/runtime/CHATGPT_HOST_MEMORY_INGRESS_V116034.md`,
`docs/project/CURRENT_STATE.md`.
Archived plans are historical references, not executable runbooks.

## Verified gap addressed in this patch (P0)

Before v116.0.34.5 the read-only `mcp-probe --check-chatgpt-tool-catalog`
verified only names/descriptions/input schemas. It could report a catalog
PASS even when a canonical tool was hidden from the ChatGPT model or
advertised unsafe/inconsistent metadata.

- Public gateway now explicitly declares model+app visibility for the
  canonical four and app-only visibility for diagnostics.
- Probe now rejects incorrect visibility, incomplete safety annotations,
  invalid security metadata and remote HTTPS without OAuth.
- Probe remains read-only and reports `current_message_toolset_verified=false`.
  A validated catalog is one gate, not proof of app installation or status.
- New regression tests cover descriptor parity *through the real FastMCP SDK*
  and fail-closed catalog cases; tests are not a deployment substitute.
- Deployment contract version is synchronized with the release identity.

## Necessary next acceptance gates (not implemented or assumed by this patch)

### A. Runtime and host truth (P0 / operator)

1. Verify package and effective `active_root`; run `run.py host-preflight --json`,
   `run.py start` and `run.py status --json` with identity and fresh heartbeat.
2. Check `/healthz` and `/readyz` *separately*. A reachable HTTP endpoint
   without `conversation_ready` must never pass.
3. Confirm the primary executor's actual spawn result independently from
   the alternative executor, and do not infer filesystem or package absence
   from a pre-spawn `ClientError`.
4. Log six tri-state discovery fields, not synthetic booleans.
5. Recovery must use existing daemon/request identity, not another submit.

### B. Public/remote ChatGPT connection (P0 / operator)

1. Provision stable TLS origin and OAuth discovery, issuer, scopes,
   audience, 401 challenge, token introspection and origin/host controls.
   Do not expose private daemon port or use anonymous public tunnel.
2. Run `run.py mcp-probe --url https://<deployed-host>/mcp
   --check-chatgpt-tool-catalog --token-env JAZN_MCP_PROBE_TOKEN --json`
   using a token provided only in operator's secure environment.
3. Add/refresh/select the genuine MCP plugin in the intended ChatGPT
   workspace. Check all four tools on a *current* user message.
4. Invoke `jazn_status` and prove version, ready, gateway/runtime ids,
   fresh observation time and heartbeat in structured content.
5. Complete two messages with preserved request lineage, no replay,
   a valid finalization and accepted `action=display_exact`.
6. Repeat on desired web, mobile and Desktop surfaces independently.
   Unsupported host surfaces are explicit blockers, not software fallback.

### C. Durable continuity and optional MEMORY (P1 / operator)

1. Fail closed on forged/stale request receipts; verify duplicate calls
   return the same durable result and cannot double-commit a conversation.
2. Inject a gateway timeout *after* daemon commit, then poll/resume the
   same request. Kill and recover daemon separately; no identity fabrication.
3. Restore MEMORY through canonical exact-set manifest, SHA, provenance,
   schema and SQLite integrity gates while respecting active-daemon
   maintenance boundaries; only claim recall when a real recall probe passes.
4. Record recovery provenance and session continuity without raw private
   text, secrets, tokens or memory database paths in ChatGPT model-visible
   diagnostic metadata.

### D. Measurable dialogue quality (P1/P2 / proposed evaluation)

Track not only aggregate `pytest PASS`, but also:

- 0 false-ready and 0 false-accepted-visible-turn scenarios;
- 0 duplicated request/turn commits after transport failure injection;
- per-host percentage of messages where all four tools were really callable;
- p50/p95/p99 status, generate, resume, finalize latency by remote transport;
- end-to-end two-turn success rate after cold startup, warm restart,
  disconnected tunnel, lost host executor, stale OAuth and stale app snapshot;
- multi-run repeatability and policy compliance for technical/ordinary Polish
  chat, ambiguous requests, correction in second turn, and memory unavailable.

Use `pass^k` / repeated trials to detect brittle success rather than only
one-shot success. Analyze reasoning, tool availability and user coordination
as separate error families; never change model/persona prompts to mask
failures in the transport or host layer.

## External primary sources and research

- OpenAI: https://developers.openai.com/plugins/reference
- OpenAI: https://developers.openai.com/plugins/build/mcp-server
- OpenAI: https://developers.openai.com/plugins/deploy/connect-chatgpt
- OpenAI: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- MCP specification 2026-07-28:
  https://blog.modelcontextprotocol.io/posts/2026-07-28/
- Cloudflare Tunnel: https://developers.cloudflare.com/tunnel/
- Yao et al., *tau-bench* (2024), repeated-run agent-tool-user evaluation:
  https://arxiv.org/abs/2406.12045
- Barres et al., *tau²-bench*, ICML 2026, dual-control coordination:
  https://proceedings.mlr.press/v306/barres26a.html
- Mittal, *How Fast Do Agents Rot?* (2026 preprint), horizon-aware
  reliability measurement (preprint, not independently reproduced here):
  https://arxiv.org/abs/2609.01660

The papers motivate evaluation methodology. They do **not** establish
that Jaźń's particular runtime is correct or that a change resolves a
ChatGPT platform `ClientError`.
