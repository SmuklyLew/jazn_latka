# Jaźń v16.3.25.5.116.0.34.3 — MCP HTTP responsiveness and host timeout evidence

## Incident and scope

On 2026-10-16 a fresh ChatGPT conversation reported `caas.internal.errors.ClientError`
before any Python command was observed to execute. A second independent local
executor surface returned the same class. That is **pre-process host evidence**,
not an exception raised by `CHATGPT_BOOTSTRAP.py`, an elapsed Python subprocess
timeout, a bad ZIP, or a failed Jaźń daemon.

The source tree already contains the bounded remote-first/local-fallback rules,
`ClientError` normalization, an integrity-protected warm/resume bootstrap,
durable MCP task identifiers, and non-replay finalization. Replacing those systems
would increase risk without evidence of a defect.

## Concrete defect fixed

The MCP 2026-07-28 Tasks ASGI interceptor (`latka_jazn/mcp/http_tasks_bridge.py`)
was awaiting transport/security checks, then directly executing the synchronous
`protocol_backend.handle_public_authenticated()` or development
`protocol_backend.handle()` inside `async def __call__`.
The backend can perform blocking SQLite and local daemon I/O. One slow request
therefore stalled the event loop servicing other MCP and `/healthz` requests.

The bridge now executes exactly **one** authenticated backend call via
`starlette.concurrency.run_in_threadpool`, including its loopback-dev branch.
Authentication, request validation, admission, identities, task persistence and
JSON-RPC exception mapping remain on their existing boundaries. No automatic
retry, second task creation, or user-message replay has been added.

A new synthetic integration test blocks a task backend on a thread event and
requires `/healthz` to respond **before** releasing it. Another test checks
the JSON-RPC internal-error response and single-call guarantee on exception.
Neither test requires private MEMORY, a remote server, or paid APIs.

## Scope explicitly not fixed by Python

This change cannot make ChatGPT spawn a Python process or provide inaccessible
filesystem/MCP tools. In particular, shortening Python commands is powerless
when `ClientError` occurs before a subprocess has been created. An external
client timeout also does not safely cancel a synchronous worker already running
in a thread. A retry must first query the durable `request_id` or `taskId`;
do not resubmit the user message.

Cold SYSTEM ZIP must retain SHA-256, safe-path, CRC and manifest checks. Do not
skip those gates to reduce wall-clock duration. Prefer verified warm/resume
paths, with genuine live status, over repeated cold extraction. Optional MEMORY
attach/convergence must stay out of ordinary conversational startup.

## Acceptance matrix

| Gate | Command or test | Required result |
| --- | --- | --- |
| Static syntax | `python -X utf8 -m compileall -q latka_jazn tests main.py run.py` | exit 0 |
| Focused regression | `python -X utf8 -m pytest -q tests/test_mcp_http_tasks_nonblocking_dispatch.py` | both tests pass |
| Existing MCP conformance | `python -X utf8 -m pytest -q tests/test_mcp_http_gateway.py tests/test_mcp_task_protocol_authorization.py` | all collected tests pass |
| Project test gate | `python -X utf8 -m pytest -q -m "not live_model and not live_mcp"` | pass |
| Release identity | `python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json` | canonical sync idempotent |
| Host runtime | Live authenticated `jazn_status`, generate/resume/finalize in ChatGPT | independent operator evidence required |
| Pre-spawn host | A current conversation actually creates a Python process | cannot be proven by CI |

## Operational follow-up

1. Verify the four callable `jazn_*` tools in the **current** ChatGPT session.
2. When those tools are absent, do at most one minimal primary spawn probe and
   one independently available alternative, then stop on pre-spawn
   `ClientError`; do not loop over Python commands or blame Jaźń.
3. If no remote route is registered, configure and verify an authenticated
   HTTPS MCP endpoint or supported secure tunnel. Code in a ZIP does not install
   a ChatGPT app.
4. If both local surfaces fail before process creation, keep filesystem,
   SYSTEM and MEMORY status **unknown** until independently observed.
5. When escalating to platform support, preserve an exact timestamp, command
   surface, error class and whether process creation was ever observed; omit
   tokens, private paths and MEMORY. A HAR/console log may help for UI/network
   incidents; never treat it as proof of a Python stack trace.

## Primary sources checked

- OpenAI Help Center: [Troubleshooting ChatGPT Error Messages](https://help.openai.com/en/articles/7996703-troubleshooting-chatgpt-error-messages).
- OpenAI Help Center: [Connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt).
- MCP: [SEP-2663 Tasks Extension](https://tasks.extensions.modelcontextprotocol.io/seps/2663-tasks-extension).
- MCP: [2026-07-28 release candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/).
- Starlette: [Thread Pool](https://www.starlette.io/threadpool/) (the synchronous bridge must not block the ASGI event loop).
- GitHub: [Workflow syntax and step-level timeouts](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).

These references support event-loop isolation, safe task resume, and diagnostic
boundaries; they do **not** establish that a ChatGPT internal `ClientError` is
caused by the duration of a Jaźń command or that the host-specific incident is
resolved.
