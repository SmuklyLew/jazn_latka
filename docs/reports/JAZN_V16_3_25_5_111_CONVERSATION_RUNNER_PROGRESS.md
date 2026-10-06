# v111 ConversationRunner and legacy dialogue cutover

Baseline: v110 `ee6bb3f4430ab19240d55823314112da205d70f5`, metadata-only descendant
of code checkpoint `c04aebada879b8b560a24a9fbfdac4ca6df18d8a`. This series is stacked
over unmerged PRs #318, #319 and #320. No PR merge is authorized.

## Implemented

- ConversationRunner owns the existing composition, engine and one session state.
  JaznRuntimeSession is an exact class alias, with no additional lifecycle/registry.
  CLI, worker, provider and daemon factories execute that same implementation.
- Worker execution enters execute_turn(TurnRequest) and the v110 TurnOrchestrator.
  A transport view constructs neither engine nor session: it delegates durable
  submission/polling to the existing gateway/daemon, with no extra durable job store.
- Typed submit/poll/resume/finalize operations use TurnStateMachine and the shared
  ProfessionalTurnRuntime transition policy. Repeated local submission fails closed.
  Restart and response-loss recovery poll the same request and never replay text.
- Production MCP submission and resume use the runner API. Historical direct MCP
  callers without a preallocated request id keep their explicit compatibility shape.
- Phase-2 compatibility entrypoints converge on ConversationRunner.finalize_candidate
  and v109 FinalizationService, without constructing a cognitive engine. Typed
  finalization checks its handle against the existing durable pending binding.
- Normal dialogue builds a classified structured candidate and ResponsePlan instead
  of calling legacy compose. Ordinary handlers pass intent/constraints to NLG without
  hardcoded greetings, stories, feedback or sleep text. Without language generation,
  existing disclosure/host-finalization gates remain closed.
- Historical compose remains an explicit compatibility/debug API in
  legacy_conversation.py. The inventory classifies every old conditional; it does
  not claim old debug callers are unreachable. Time/status/truth/recovery text
  remains deterministic where it reports runtime evidence or protocol state.

## Retry and acceptance owners

| Concern | Owner |
| --- | --- |
| Session/composition and execution | ConversationRunner worker |
| Durable jobs, queues, supervision | Existing RuntimeDaemonState/worker registry |
| Durable operation before POST | Existing SecureHostRuntimeGateway operation store |
| Read-only transport retries | Existing bounded gateway/client policy |
| Candidate repair/regeneration | TurnOrchestrator RecoveryPolicy |
| Resume after interruption | ConversationRunner poll/resume with the same request id |
| Host candidate acceptance/replay guard | FinalizationService + durable_host_request_store |
| Exact visible output | Existing MessageEnvelope, integrity/consensus/truth/finalization gates |

TurnStateMachine observes these authorities; it cannot promote answer_ok or an
accepted_visible_turn_ready boolean to accepted visibility. It consults existing
exact-envelope validation. Transport ambiguity is never permission to resubmit.

## Initial checkpoint validation

- v110 final local deterministic suite: **2078 PASS, 4 platform SKIPPED**, one expected
  duplicate-ZIP-member warning, zero failures, 700.82 seconds.
- v110 code checkpoint CI: Pyright, release-hardening, package cleanroom and persistent
  E2E Linux/Windows **SUCCESS**; PowerShell **IN_PROGRESS** at this observation.
- v111 session/atomicity/degraded persistence: **17 PASS**.
- v111 runner/cutover/historical pipeline parity/MCP phase-2/host continuity/budgets:
  **33 PASS** at the first focused integration run.
- v111 route audit and compileall: **PASS**.
- v111 full suite/final Pyright/release-hardening/Linux+Windows E2E/cleanroom/PowerShell:
  **NOT RUN/IN_PROGRESS**, awaiting actual results.

This is not complete v111 or merge readiness. Follow-up must cover the full tree,
final immutable SHA gates, soak/restart behavior, and accepted-but-unpublished
finalization projection recovery. No external ChatGPT voice acceptance is claimed.

## Primary architecture references

- [MCP transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
- [MCP versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)
- [OpenTelemetry Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [Python os.replace](https://docs.python.org/3/library/os.html#os.replace)

Same-filesystem atomic replacement retains the existing durability contract; it
does not establish a universal power-loss guarantee.

## Accepted projection recovery checkpoint

The durable consumed request remains the sole host acceptance authority. Recovery
reads and verifies its committed capture and exact MessageEnvelope; it does not
rerun finalization, claim a new request, or resubmit user text. Existing cross-process
write guards serialize initial publication and recovery. Exact assistant/event
projections and epistemic entries are reused; missing projections are appended once.
Conflicting, duplicate, corrupt or substituted records fail closed. Conversation and
session projections reuse their existing lineage guards. A torn JSONL record is an
explicit recovery error, not permission to discard history.

MCP resume repairs a committed pending projection after validating the exact accepted
runtime/host final. Shallow integrity/truth flags alone no longer authorize display.
The historical recovery fixture now supplies the complete accepted runtime contract;
all original assertions and the historical version are preserved in its archive.

Evidence at this checkpoint:
- v109 final metadata SHA 452df9d: Pyright/release-hardening/cleanroom/PowerShell SUCCESS.
- v110 final metadata SHA ee6bb3f: Pyright/release-hardening/cleanroom SUCCESS;
  final dispatched PowerShell IN_PROGRESS. Earlier code-SHA PowerShell SUCCESS.
- v111 initial c9a67bf CI: Pyright/release-hardening/cleanroom/PowerShell and persistent
  runtime E2E Linux/Windows SUCCESS. Metadata persistence/redundant release finalization
  jobs marked SKIPPED remain SKIPPED, not PASS.
- Initial local full suite: 1 FAIL, 2092 PASS, 4 platform SKIPPED. The unchanged daemon
  stop assertion timed out. Its fresh focused rerun with the full-suite network-time
  settings PASS; the failed initial run remains validation evidence.
- Recovery/service/atomicity/MCP/resume focused integration: 28 PASS before adding
  the additional shallow-flag rejection regression.
- Follow-up full suite and immutable final-SHA CI: IN_PROGRESS/NOT RUN.

No merge, external ChatGPT voice acceptance, or universal power-loss guarantee is claimed.
