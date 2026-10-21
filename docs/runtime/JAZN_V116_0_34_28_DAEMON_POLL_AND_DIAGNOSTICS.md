# Jaźń v16.3.25.5.116.0.34.28 — daemon poll provenance and live diagnostics

## Scope and observed evidence

The patch targets two defects reproduced in a separate ChatGPT sandbox with the
previous SYSTEM package `16.3.25.5.116.0.34.27`:

1. The original `chat-gpt` result identifies `persistent_daemon`, while a
   `--daemon-result <same request_id>` fetch retains the final text/turn identity
   but can lose the CLI-side `transport_observability` (falling to `unknown`).
2. Explicit requests for the live daemon PID / `daemon_instance_id` /
   `conversation_ready` can be overclassified as
   `package_runtime_status_question`, generating static package metadata
   rather than the requested process data.

The original sandbox's PID, private memory and raw logs are **not** committed.
This branch does not restart or modify that sandbox's daemon or MEMORY.

## Transport evidence contract

- The direct `chat-gpt` path retains its existing submit-side provenance.
- A completed `--daemon-result` may **independently re-attest** its *read path*
  against the canonical active marker, package/source provenance, live endpoint,
  matching daemon process identity and fresh heartbeat. A clock-degraded
  `active_degraded` status is eligible only when those independent identity and
  freshness checks succeed.
- The result then carries `transport_observability` for the host gate and
  `retrieval_transport_observability` with
  `transport_evidence_origin=retrieval_live_status`. The latter proves the
  current retrieval path; it does **not** retroactively authenticate the
  original submit envelope.
- No evidence, stale heartbeat, failed identity, missing marker or unreachable
  endpoint: **no transport promotion**. The host gate must retain `unknown` /
  fail-closed behavior.
- This changes no `request_id`, `turn_id`, `trace_id`, original
  `final_visible_text` or accepted finalization digest. It never resubmits
  a user message from a poll.

## Routing and exact fields

When a user explicitly asks for live daemon-specific fields
(`daemon_instance_id`, `conversation_ready`, `heartbeat_fresh`,
`runtime_ready`, `daemon_ready`, daemon PID), the classifier selects the
health-check path before a generic package-status fast path. Requests for ZIP,
CRC or SHA-256 alone keep their package-validation handler.

On the health route, an explicit daemon-fields request probes the canonical
`status_daemon` read-only. Returned daemon PID and instance ID must pass
endpoint identity, process identity, package/source integrity and heartbeat
checks; otherwise the handler emits `not_verified`. A missing
`conversation_ready` field is also `not_verified`, never inferred from PID
or process existence. The current CLI process's PID must never be substituted
for daemon PID.

## Acceptance and verification matrix

- New deterministic tests exercise daemon process fields overriding package
  routing, unaffected real package questions, trustworthy and untrustworthy
  live status, clock-degraded but otherwise healthy polling, missing evidence,
  and unchanged result IDs/text without resubmit.
- Run: `python -X utf8 -m pytest -q tests/test_v11603428_daemon_result_transport_and_live_diagnostics.py`.
- Then run the existing host, daemon and routing suites, `pyright`,
  `compileall`, `doctor`, `package-smoke --profile system`,
  `release_metadata_sync`, and `git diff --check`.
- A positive static GitHub commit is **not** equivalent to local pytest, CI,
  a new daemon start or production ChatGPT MCP availability.
- Required release metadata is maintained only by the canonical workflow;
  do not manually edit `SOURCE_PROVENANCE.json` or
  `PACKAGE_INTEGRITY_MANIFEST.json`.
- Preserve the existing `AGENTS.md` / `AGENTS.chatgpt.md` /
  `AGENTS.codex.md` ownership boundaries.

## Research basis (primary sources)

- MCP Streamable HTTP specification `2026-07-28`:
  https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx
  — request-scoped responses, independently operated server, origin validation.
- OpenTelemetry context and trace propagation:
  https://opentelemetry.io/docs/specs/otel/overview/
  — IDs and context are correlated across processes, but must have a trusted
  propagation boundary.
- Python `unittest.mock`:
  https://docs.python.org/3/library/unittest.mock.html
  — isolate daemon-status and messaging seams without creating real processes.
- Python shallow/deep copy semantics:
  https://docs.python.org/3/library/copy.html
  — copy provenance dictionaries rather than mutating a shared record.
- Berkeley Function Calling Leaderboard (BFCL), ICML 2025:
  https://proceedings.mlr.press/v267/patil25a.html
  — multi-turn agent/tool-state evaluation motivates explicit no-replay and
  no-silent-route-substitution regression cases.
- Liu et al., "Lost in the Middle" (TACL 2024):
  https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00638/119630/
  — do not rely on an LLM reading long instructions as a substitute for a
  deterministic verified per-turn contract.
- JavaScript structured cloning reference:
  https://developer.mozilla.org/en-US/docs/Web/API/Window/structuredClone
  — reviewed for potential client-side envelope copying. No JavaScript change
  is needed: both observed faults occur before any JS UI transformation.

Research references explain design tradeoffs, not proof that this patch passed
runtime validation. Actual acceptance must be based on executable tests and
observed CI results.
