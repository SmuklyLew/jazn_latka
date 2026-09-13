# ChatGPT Turn Ingress Gate Convergence Plan — v16.3.25.5.74

Status: implemented locally and pending branch validation/publication.

## Problem

Before v16.3.25.5.74 the repository already contained a strong fail-closed `run_host_pre_response_gate()`, but production ChatGPT paths could build gate telemetry without actually executing that gate. The helper therefore protected its direct tests better than it protected every real ingress. A persistent daemon could be healthy while the current visible host turn was not proven to be bound to Jaźń.

The required invariant is stronger than daemon liveness:

> Every ordinary ChatGPT user message handled by a Jaźń-supported ingress must cross the canonical pre-response gate before any runtime-owned visible text can be exposed.

A valid package, a daemon PID/heartbeat/endpoint, or a previously accepted turn is never evidence for the current visible turn.

## External evidence

The implementation is based on current primary/official documentation:

1. OpenAI — Developer mode and MCP apps in ChatGPT: <https://help.openai.com/en/articles/12584461>
   - custom MCP apps are a platform capability;
   - app selection applies to the message where it is used, rather than installing an unconditional conversation-wide hook;
   - full MCP, including write/modify actions, is currently available to Business and Enterprise/Edu;
   - a local/private MCP server requires Secure MCP Tunnel on supported products.
2. OpenAI — Apps in ChatGPT: <https://help.openai.com/en/articles/11487775>
   - apps/plugins are the product integration layer through which ChatGPT reaches external tools and actions.
3. OpenAI — Secure MCP Tunnel client: <https://github.com/openai/tunnel-client>
   - the customer-run tunnel process connects a private/localhost MCP server to supported OpenAI products while keeping that server off the public Internet;
   - tunnel control-plane transport remains external to the Jaźń ZIP/runtime.
4. Model Context Protocol — Transports: <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>
   - stdio is a subprocess transport over stdin/stdout;
   - Streamable HTTP defines explicit request/session/resume behavior;
   - disconnection is not equivalent to cancellation, so reliable implementations must preserve request identity rather than replay blindly.
5. Model Context Protocol — Lifecycle: <https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle>
   - initialization and capability negotiation are explicit lifecycle phases, not assumptions inferred from process existence.

## Platform truth boundary

Repository code can make every *supported Jaźń ingress* fail closed and can prove whether the current turn crossed that gate. Repository code cannot force an arbitrary ChatGPT product surface to invoke a custom tool on every message. That last hop belongs to the ChatGPT app/plugin/host capability layer.

Therefore v16.3.25.5.74 explicitly distinguishes:

- `runtime/daemon ready` — persistent backend liveness;
- `turn_ingress_gate_enforced` — the current message crossed the canonical host gate;
- `host_route_bound` — the current gate accepted a runtime action (`display_exact`, `generate_then_finalize`, or `poll_runtime`);
- platform auto-routing — an external ChatGPT capability, never granted by the ZIP itself.

A Plus/consumer surface must not be documented as if full custom write-capable MCP were automatically available. Current OpenAI documentation limits full MCP write/modify apps to Business and Enterprise/Edu, while Pro is limited to read/fetch MCP in developer mode. The local persistent bridge / daemon-bound transactional route therefore remains the executable path when the ChatGPT host supplies an executor.

## Implementation stages

### 1. Make the canonical gate production code

Wire `run_host_pre_response_gate()` into every ordinary ChatGPT ingress controlled by this repository:

- persistent JSONL `run_jsonl_chat_bridge()`;
- daemon fast path used by `run.py chat-gpt -- ...`;
- MCP `jazn_generate_visible_reply`.

The exact user text is the gate input. Host-generated visible text cannot precede the gate.

### 2. Preserve gate evidence through rendering

`build_chatgpt_host_presentation_packet()` revalidates compact host packets. When rebuilding a packet after a real gate execution, it may preserve gate telemetry only if the evidence is explicitly marked as enforced and still matches the revalidated action plus turn/trace lineage.

Expose:

- `turn_ingress_gate_enforced`;
- `host_route_bound`.

Neither may be inferred from daemon liveness.

### 3. Prevent replay after daemon-bound submit

Before message submission, capability discovery may choose another valid route. After the current message enters the verified daemon route, ambiguous submit/poll/finalization failure must not create a new independent local turn. The safe outcomes are `poll_runtime` for the same request or `host_diagnostic`.

### 4. Converge MCP onto the same gate

`jazn_generate_visible_reply` uses the same canonical gate rather than duplicating a partial set of checks. Existing continuation-token and phase-2 finalization semantics remain authoritative.

### 5. Add regression coverage

The active tests must prove that:

- consecutive JSONL messages each cross the gate with their exact text;
- daemon fast path crosses the gate;
- MCP visible-reply ingress crosses the gate before direct gateway execution;
- `persistent_daemon` alone does not imply `host_route_bound`;
- host-packet rebuilding preserves only matching enforced gate evidence;
- pending-request/no-replay/finalization contracts remain green.

### 6. Release and validation

Release identity: `16.3.25.5.74-chatgpt-turn-ingress-gate-convergence`.

Do not manually edit `PACKAGE_INTEGRITY_MANIFEST.json` or `SOURCE_PROVENANCE.json`; use the repository's canonical release metadata synchronization.

Required gates:

- targeted host gate / JSONL / daemon / MCP tests;
- `compileall`;
- default non-live pytest suite;
- repository static typing gate;
- `doctor --json` and system package smoke where the runtime environment permits;
- release metadata synchronization and idempotence;
- GitHub Actions for the branch.

## Acceptance criteria

1. Production code has real call sites for `run_host_pre_response_gate()` in JSONL, daemon fast path and MCP ingress.
2. No supported ordinary ChatGPT ingress can expose a Jaźń-visible answer without current-turn gate evidence.
3. `host_route_bound=false` for diagnostic/unavailable paths even if a daemon was alive earlier.
4. Accepted `display_exact`, `generate_then_finalize`, and `poll_runtime` paths carry current-turn gate evidence.
5. Lost daemon responses are not converted into replayed second turns.
6. Documentation accurately states the ChatGPT plan/app boundary rather than presenting package code as a platform hook it cannot install.
