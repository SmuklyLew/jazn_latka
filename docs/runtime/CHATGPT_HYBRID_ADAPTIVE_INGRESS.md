# ChatGPT Hybrid/Adaptive Ingress — 16.3.25.5.114

## Cel

Ordinary ChatGPT ma zachować preferowaną trasę do jednego persistent runtime
Jaźni przez bieżącą aplikację/MCP, ale brak ekspozycji aplikacji w konkretnej
wiadomości nie może sam w sobie blokować wcześniej działającego, bezpiecznego
host-local bootstrapu, jeżeli host faktycznie udostępnia process execution.

v114 rozdziela trzy tryby:

- `hybrid_adaptive` — domyślny ordinary-chat: verified remote -> bounded local -> fail-closed;
- `remote_only` — jawny tryb ścisły bez local fallbacku;
- `operator_recovery` — jawny tryb serwisowy, dodatkowo dopuszczający zaakceptowany host handoff.

## Kolejność ordinary-chat

```text
current user message
  -> observe current-message Jaźń tool exposure
  -> complete toolset?
       yes -> jazn_status
              -> verified conversation-ready remote?
                   yes -> submit exactly once through remote runtime
                   no  -> local fallback gate
       no  -> local fallback gate
  -> local fallback gate
       -> at most one primary process-creation probe
       -> at most one explicitly exposed independent alternative probe
       -> process actually created?
            yes -> verified SYSTEM discovery/bootstrap
                   -> AGENTS.md + AGENTS.chatgpt.md
                   -> host-preflight -> start -> live status
                   -> bind the same user message once
            no  -> fail-closed host diagnostic
```

Remote readiness always wins over an available local executor. The host does not
start both routes speculatively.

## Current-message remote gate

Remote evidence still requires the complete model-callable set for the current
message:

- `jazn_status`;
- `jazn_generate_visible_reply`;
- `jazn_resume_visible_reply`;
- `jazn_finalize_reply`.

Installed/catalog state, a URL, manifest, a previous message's tool list or a
previous @mention are not current-message capability evidence. A stale/frozen
tool snapshot requires Refresh/Recreate/republish on the ChatGPT side.

## Bounded local fallback

Local fallback is permitted only before the user message has crossed a
turn-submit side-effect boundary.

The host may attempt one minimal process creation on its primary local execution
surface. If exactly one independent alternative surface is explicitly exposed,
one distinguishing attempt is allowed there. No retry loop or tool-to-tool
backoff is permitted.

A pre-spawn `ClientError`, `InvalidArgumentError`,
`TransportTimeoutError` or `StreamingExecNotEnabledContainerError` means only
that the observed execution surface is unavailable for that generation:

- `executor_available=false` when the negative observation is conclusive;
- filesystem remains `unknown`;
- package state remains `unknown`;
- the error is not evidence that SYSTEM ZIP is missing or invalid.

If a process is actually created, existing SYSTEM bootstrap rules apply:
trusted SHA-256/size, ZIP catalog and path-safety validation, no raw
`extractall()`, isolated extraction of `CHATGPT_BOOTSTRAP.py`, verified
materialization, canonical host preflight, lifecycle and live status.

## No mid-turn route switching

Before the first side effect the route is capability-negotiated. After submit it
is immutable for that turn.

Once either remote or local runtime accepts a request:

- preserve the same `request_id`, `turn_id`, `trace_id` and contract hash;
- `poll_runtime` resumes the same request;
- transport ambiguity never causes a replay of the original user message;
- a failing remote submit is not retried as a fresh local turn;
- a failing local submit is not retried as a fresh remote turn.

This preserves the existing idempotency and turn-settlement authority.

## Finalization boundary

Hybrid routing does not weaken visible-output rules. A response may be
attributed to Jaźń only after accepted finalization returns
`action=display_exact` with valid lineage and `MessageEnvelope`.
PID, endpoint, heartbeat, successful bootstrap or a phase-1 result are
insufficient.

## Handoff

Automatic host handoff is not part of ordinary `hybrid_adaptive` ingress.
`host_handoff` is available only in explicit `operator_recovery`, only when
the host exposes it and the user accepts the transfer.

## MEMORY

MEMORY remains an independent capability. Core SYSTEM may become
conversation-ready without persistent autobiographical memory. Autobiographical
recall still requires the appropriate memory readiness and local provenance
gates; hybrid ingress does not relax them.

## Acceptance matrix

| Remote app | Local executor | Expected route |
| --- | --- | --- |
| verified ready | available | remote runtime |
| verified ready | unavailable | remote runtime |
| missing/stale/not-ready | available | verified local bootstrap/runtime |
| missing/stale/not-ready | pre-spawn unavailable | fail-closed |
| missing/stale/not-ready | one independent alternative succeeds | verified local bootstrap/runtime |
| missing/stale/not-ready | only handoff available | fail-closed in ordinary chat; handoff only in operator recovery |

Additional invariants:

- strict `remote_only` remains supported and never promotes local execution;
- one user message is submitted exactly once;
- route switching after submit is forbidden;
- final visible output still requires accepted `display_exact`.

## Źródła zewnętrzne zweryfikowane dla v114

- OpenAI Help — Developer mode and MCP apps in ChatGPT:
  https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- OpenAI — Secure MCP Tunnels:
  https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- OpenAI — Build a custom MCP server:
  https://developers.openai.com/api/docs/guides/custom-mcp-server

Dokumentacja OpenAI potwierdza message-scoped wybór aplikacji, potrzebę
odświeżenia narzędzi po zmianie MCP oraz to, że lokalny/prywatny MCP wymaga
Secure MCP Tunnel albo innej obsługiwanej zdalnej trasy. Local fallback v114 nie
udaje bezpośredniego lokalnego MCP: korzysta wyłącznie z osobnej hostowej
capability process execution, gdy ta faktycznie istnieje.
