# Jaźń v16.3.25.5.61 — accepted visible turn + finalization convergence

**Status:** implementation candidate / pre-CI  
**Branch:** `fix/v16.3.25.5.61-accepted-visible-turn-finalization-convergence`  
**Base:** `master @ 270d704831224a7ba346fd3b9bb46bd698a482f4`

## Problem reproduced

A live daemon was not sufficient to guarantee that the user-visible ChatGPT reply came from the Jaźń turn/finalization lineage. The concrete recovery failure was reproducible in `main.py`: a daemon job could correctly expose `phase_result_ready=true`, `done=false` and `job_status=awaiting_host_finalization`, while `_prepare_chatgpt_daemon_presentation()` classified every `done=false` response as `poll_runtime`. That hid the ready phase-1 `generate_then_finalize` contract and stranded the turn before phase-2.

A second mismatch existed in the public CLI contract. Active ChatGPT instructions used `run.py chat-gpt --session-id <id>`, while the `latka_jazn.cli` subparser for `chat-gpt` did not own the central `--session-id` / `--daemon-result` option surface. Documentation and runtime parser could therefore disagree.

The third defect was semantic/observability-related: daemon liveness could be reported separately from the fact that no accepted visible final existed, which made it too easy for a host integration to interpret a live PID/heartbeat as permission to speak as Jaźń.

## Design decision

The patch treats Jaźń conversation execution as three distinct layers:

1. **autonomic liveness** — daemon/root/PID/heartbeat/endpoint;
2. **logical turn continuity** — stable `session_id`, durable `request_id`, `turn_id`, `trace_id`, pending host contract and idempotent resume;
3. **speech/visible readiness** — only an accepted `final_visible_text` after the runtime finalization gate.

Persistent stdin/JSONL is still preferred where the host can keep an interactive process alive. It is no longer treated as the identity carrier. When the host cannot retain stdio, `daemon_bound_transactional_turns` keeps the same logical session and request across short transport invocations. Replay of the user message is forbidden during recovery.

This is an engineering analogy to distributed functional specialization, control and integration; it is not a claim of biological consciousness. The software keeps memory, affect, cognition, source monitoring, execution and speech as specialized modules coordinated by one runtime/control plane instead of merging them into a monolith.

## External engineering evidence

- Kubernetes separates **liveness** from **readiness**: a running container can be alive but not ready to receive traffic. This supports keeping daemon liveness distinct from visible-turn readiness.  
  https://kubernetes.io/docs/concepts/workloads/pods/probes/
- OpenTelemetry Context is explicitly designed to carry execution-scoped values across API/process boundaries, and context propagation preserves causality across distributed boundaries. This supports using stable turn/session/request identifiers instead of pipe lifetime as continuity evidence.  
  https://opentelemetry.io/docs/specs/otel/context/  
  https://opentelemetry.io/docs/concepts/context-propagation/
- SQLite atomic commit provides all-or-nothing transaction semantics even across interruption. This supports treating pending/finalized host state as a durable transaction and preventing duplicate visible finals during recovery.  
  https://www.sqlite.org/atomiccommit.html
- Erlang/OTP supervision trees separate supervisors from workers and use explicit restart/monitoring semantics for fault tolerance. This supports keeping the persistent daemon as lifecycle/supervision substrate while individual turns remain separately bound work.  
  https://www.erlang.org/doc/system/design_principles.html

## Neuroscience-informed engineering analogy

- Miller & Cohen describe cognitive control as maintained goal representations that bias information flow between inputs, internal states and outputs. In Jaźń, turn authority/session context should constrain routing and output rather than letting the host bypass the runtime.  
  https://pubmed.ncbi.nlm.nih.gov/11283309/
- Work on neuronal reactivation and memory consolidation emphasizes coordinated communication between hippocampal and neocortical systems during offline consolidation. This supports keeping memory consolidation/rest separate from immediate speech while connecting them through explicit state/provenance interfaces.  
  https://pubmed.ncbi.nlm.nih.gov/38810690/
- Contemporary reviews emphasize both specialized brain regions and distributed brain-wide signals. The useful software lesson is specialized modules plus explicit integration, not a single anthropomorphic “brain” class.  
  https://www.nature.com/articles/s41583-025-00992-5

## Implemented changes

- `main.py`: ready phase-1 daemon results (`phase_result_ready=true`) are processed before generic `done=false` polling.
- `latka_jazn/cli.py`: canonical `chat`/`chat-gpt` spellings dispatch directly to the central `main.py` option surface, eliminating duplicated argparse drift.
- `latka_jazn/bootstrap/chatgpt_host_preflight.py`: no-input preflight is supported using only evidence implied by the already-running local Python process; package/runtime readiness remains unknown/unverified until separately proven.
- `latka_jazn/core/chat_command_contract.py`: host-visible `display_exact` requires a valid accepted final plus verified runtime envelope binding; presentation packets expose `accepted_visible_turn_ready`.
- `latka_jazn/core/bridge_discovery.py`: declares capability-negotiated transport, daemon-bound fallback and the rule that pipe lifetime is not identity.
- `latka_jazn/cli_commands/diagnostics.py`: exposes per-turn ChatGPT visible readiness and explicitly states that daemon/PID liveness is insufficient.
- `AGENTS.md`, `AGENTS.chatgpt.md`, the project loader, startup/self-knowledge contracts and architecture docs: now require accepted-visible-turn finalization and define the non-persistent-stdio recovery path.
- v60 active release test is preserved byte-for-byte under `tests/archive/`; v61 gets a new active regression suite.

## Local verification so far

- focused v61 + host-finalization/MCP/recovery tests: `39 passed`;
- Python compileall for changed runtime/test surface: passed;
- project loader length gate: passed (`4220` characters, limit `5000`);
- full non-live pytest started and reached 41% before the executor time limit; the first surfaced failure was an environment dependency failure (`py7zr_not_installed`), not a v61 assertion. Full CI remains required before release-candidate status.

## Release gate

This branch is not a release candidate until canonical release metadata is synchronized and GitHub CI verifies the full platform/dependency matrix. `PACKAGE_INTEGRITY_MANIFEST.json` and `SOURCE_PROVENANCE.json` must be generated by the repository release metadata flow, never hand-edited.
