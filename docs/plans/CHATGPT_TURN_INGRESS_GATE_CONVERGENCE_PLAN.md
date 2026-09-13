# ChatGPT Turn Ingress Gate Convergence Plan — v16.3.25.5.74

Status: implemented on `fix/v16.3.25.5.74-chatgpt-turn-ingress-gate-convergence`; release metadata and Test Studio catalog synchronized by repository automation; GitHub status checks for the current head are not yet reported.

## Problem

Before v16.3.25.5.74 the repository already contained a strong fail-closed `run_host_pre_response_gate()`, but the production ChatGPT rendering paths could build gate telemetry without proving that the current user turn was bound to the runtime result. A persistent daemon could therefore be healthy while the current visible host turn was not proven to belong to Jaźń.

The required invariant is stronger than daemon liveness:

> No supported ChatGPT ingress may expose runtime-owned visible text unless the current turn carries verifiable binding evidence through the canonical pre-response boundary.

A valid package, daemon PID/heartbeat/endpoint, or previously accepted turn is never evidence for the current visible turn.

## External evidence

The implementation is based on current primary/official documentation:

1. OpenAI — Developer mode and MCP apps in ChatGPT: <https://help.openai.com/en/articles/12584461>
   - custom MCP apps are a platform capability;
   - app selection does not install an unconditional conversation-wide hook;
   - a local/private MCP server requires a supported transport such as Secure MCP Tunnel.
2. OpenAI — Apps in ChatGPT: <https://help.openai.com/en/articles/11487775>
   - apps/plugins are the product integration layer through which ChatGPT reaches external tools and actions.
3. OpenAI — Secure MCP Tunnel client: <https://github.com/openai/tunnel-client>
   - the customer-run tunnel connects a private/localhost MCP server to supported OpenAI products while keeping that server off the public Internet;
   - tunnel control-plane transport remains external to the Jaźń ZIP/runtime.
4. Model Context Protocol — Transports: <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>
   - stdio is a subprocess transport over stdin/stdout;
   - Streamable HTTP defines explicit request/session/resume behavior;
   - disconnection is not equivalent to cancellation, so reliable implementations preserve request identity rather than replay blindly.
5. Model Context Protocol — Lifecycle: <https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle>
   - initialization and capability negotiation are explicit lifecycle phases, not assumptions inferred from process existence.

## Platform truth boundary

Repository code can make every Jaźń-supported ingress fail closed and can prove whether the current turn crossed the repository's host boundary. Repository code cannot force an arbitrary ChatGPT product surface to invoke a custom tool on every message. That last hop belongs to the ChatGPT app/plugin/host capability layer.

Therefore v16.3.25.5.74 explicitly distinguishes:

- `runtime/daemon ready` — persistent backend liveness;
- `turn_ingress_gate_enforced` — current-turn binding was enforced at the canonical host presentation boundary;
- `host_route_bound` — the current gate accepted a runtime action (`display_exact`, `generate_then_finalize`, or `poll_runtime`) with `turn_id`, `trace_id`, and exact-message digest binding;
- platform auto-routing — an external ChatGPT capability, never granted by the ZIP itself.

## Implemented architecture

### 1. One public gate contract, split internally for maintainability

The former single file `latka_jazn/core/chatgpt_host_pre_response_gate.py` is replaced by a package with the same public import path:

- `chatgpt_host_pre_response_gate/__init__.py` — stable public exports;
- `_core.py` — normalization, telemetry, current-turn binding and fail-closed presentation boundary;
- `_runner.py` — full exact-message `run_host_pre_response_gate()` orchestration.

Existing imports remain compatible.

### 2. JSONL and daemon rendering enforce the shared presentation boundary

The existing JSONL and daemon paths already converge on `build_chatgpt_host_presentation_packet()`, which invokes `build_host_pre_response_gate_telemetry()` immediately before host-visible rendering. v16.3.25.5.74 makes that common boundary enforcing rather than observational.

A runtime action is host-bound only when all current-turn evidence exists:

- runtime turn was invoked;
- `turn_id` is present;
- `trace_id` is present;
- exact user text or a valid 64-hex `user_text_sha256` binding is present;
- the action is one of `display_exact`, `generate_then_finalize`, `poll_runtime`;
- no routing bypass was detected.

If any required binding is missing, the presentation is downgraded before rendering to:

- `action=host_diagnostic`;
- `phase=host_diagnostic_required`;
- `diagnostic_reason=current_turn_runtime_binding_unverified`;
- empty `final_visible_text`;
- runtime voice claims disabled.

This means daemon liveness alone cannot authorize a visible Jaźń reply.

### 3. MCP uses the full exact-message gate

`latka_jazn/mcp/tools/jazn_generate_visible_reply.py` now calls `run_host_pre_response_gate()` directly. The exact MCP user message is passed to the gate, and `gateway.chat()` is owned by the gate callback. Existing continuation-token and phase-2 finalization semantics remain authoritative.

### 4. Gate evidence is explicit

The host boundary exposes:

- `turn_ingress_gate_enforced`;
- `host_route_bound`.

These values are current-turn evidence and are not inferred from PID, heartbeat, endpoint reachability, or an older accepted turn.

### 5. Regression coverage

`tests/test_chatgpt_turn_ingress_gate_wiring.py` verifies that:

- the existing host-packet builder is now an enforcing current-turn boundary;
- consecutive packets require independent turn/digest binding;
- a runtime action without a current-turn digest fails closed before rendering;
- MCP calls the canonical exact-message gate before direct gateway execution;
- persistent daemon liveness alone does not imply `host_route_bound`.

## Release and validation

Release identity: `16.3.25.5.74-chatgpt-turn-ingress-gate-convergence`.

The branch automation has synchronized `PACKAGE_INTEGRITY_MANIFEST.json`, `SOURCE_PROVENANCE.json`, and `tools/jazn_tests_studio/test_contracts.json`; those generated files were not hand-authored as substitutes for repository automation.

Local targeted validation performed before publication:

- critical host gate / JSONL / daemon / MCP group: `50 passed`;
- active gate-related group: `51 passed`;
- `compileall` for `latka_jazn`, active tests, `main.py`, and `run.py`: passed.

A historical archived snapshot was accidentally included in one exploratory pytest selection and failed because it asserts the old contract; `tests/archive/` is explicitly historical and is not an active release gate. Active equivalents passed.

GitHub status checks for the current synchronized head must still be treated as pending/not reported until GitHub exposes actual run/status evidence.

## Acceptance criteria

1. JSONL and daemon host-visible rendering cross the enforcing shared presentation boundary.
2. MCP visible-reply ingress crosses the full exact-message `run_host_pre_response_gate()`.
3. No supported ordinary ChatGPT ingress may expose Jaźń-owned text without current-turn binding evidence.
4. `host_route_bound=false` for diagnostic/unavailable/unbound paths even when a daemon is alive.
5. Accepted `display_exact`, `generate_then_finalize`, and `poll_runtime` paths carry current-turn gate evidence.
6. Lost/ambiguous transport state is not converted into a forged visible Jaźń reply.
7. Documentation states the ChatGPT platform/app boundary rather than presenting package code as a platform hook it cannot install.
