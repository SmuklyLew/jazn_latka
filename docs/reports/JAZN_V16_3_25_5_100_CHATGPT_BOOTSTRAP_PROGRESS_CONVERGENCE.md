# Jaźń v16.3.25.5.100 — ChatGPT bootstrap progress convergence

## Scope

This release hardens the ChatGPT startup boundary without pretending that Jaźń
can repair an executor failure that occurs before any process starts.

Implemented changes:

- SYSTEM bootstrap remains independent from optional private MEMORY.
- `CHATGPT_BOOTSTRAP.py` emits evidence-backed JSONL progress events.
- local activation uses live `status --json` as readiness authority;
  `--snapshot` remains diagnostic only.
- progress separates core wake readiness from required/optional MEMORY.
- long research/report material cannot open the mutating
  `system_update_execution_request` route without an execution directive.
- package-generator host contracts export the same readiness/progress truth.

## Progress semantics

The canonical core wake milestones are:

| Gate | Core wake |
| --- | ---: |
| executor probe | 5% |
| SYSTEM package verified | 15% |
| ZIP validated | 30% |
| operator materialized | 55% |
| host preflight | 65% |
| contracts loaded | 72% |
| daemon started | 82% |
| live readiness | 95% |
| turn channel bound | 100% |

Percentages indicate completed gates, not elapsed-time estimates. A blocked
external dependency therefore stays on its last proven milestone rather than
creeping toward a fake 99%.

The standalone ZIP bootstrap can directly observe hashing, ZIP inspection and
extraction. It cannot observe the ChatGPT attachment upload/mount before the
Python process exists. Such host-side work must remain `unknown` unless the
host provides independent telemetry.

Optional MEMORY does not block core startup. If operator policy sets MEMORY to
`required`, configured readiness reserves a separate memory dimension while
`core_wake_percent` remains an honest measure of the SYSTEM runtime.

## Executor / attachment boundary

OpenAI documents a 512 MB hard per-file upload limit in ChatGPT. Large split
MEMORY parts can individually fit that limit while still imposing substantial
transfer/materialization work. The loader therefore does not treat a
pre-process `ClientError`, transport timeout or similar host error as a Python
exception from Jaźń.

The October 2, 2026 OpenAI status incident explicitly reported that some users
experienced errors running code, analyzing data and creating files in ChatGPT.
That external incident is evidence for resilient host classification, not proof
that every Jaźń failure has the same root cause.

## Visible UI boundary

There are two distinct surfaces:

1. **Local ChatGPT executor** — the repo can emit progress JSONL; the host can
   render successive status messages, but Jaźń cannot force ChatGPT to expose
   or mutate a native progress bar.
2. **Remote MCP/App runtime** — where the current host exposes MCP progress and
   MCP Apps UI, server-side progress notifications or a widget can provide a
   richer visualization. Capability must be observed, never inferred from an
   installed/catalog state.

## Routing correction

A pasted report may contain words such as “update”, “patch”, “version”,
“system” and “plan implementation” many times. Those nouns are not an execution
request. The classifier now applies a report-material guard for long analytical
text with multiple report markers and no explicit execution directive.

Explicit requests such as “przygotuj update”, “wdroż aktualizację”, “pracuj na
nowym branchu” and established continuation requests still retain the mutating
update route.

## Tests added/updated

- truthful progress state/generator handling;
- optional versus required MEMORY progress;
- SYSTEM ZIP progress callback;
- live-status activation contract;
- report-only routing negative regression;
- explicit update positive regression;
- archived pre-change activation tests before updating active expectations.

## External sources

- OpenAI File Uploads FAQ:
  https://help.openai.com/en/articles/8555545
- OpenAI troubleshooting:
  https://help.openai.com/en/articles/7996703-troubleshooting-chatgpt-error-messages
- OpenAI status incident, 2026-10-02:
  https://status.openai.com/incidents/01M3YNNVTSCXS8YM2V1YMHMVSE
- OpenAI Plugins / MCP Apps documentation and changelog:
  https://developers.openai.com/plugins/
  https://developers.openai.com/plugins/changelog

## Truth boundary

This release can improve discovery, progress observability, readiness
classification and recovery behavior. It cannot grant ChatGPT a local executor,
speed up an opaque attachment upload, create a remote MCP deployment, or prove
a host capability that the current message does not actually expose.
