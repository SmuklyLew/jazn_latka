# v111 ConversationRunner and legacy dialogue cutover

**Final status 2026-10-06:** `REPOSITORY_COMPLETE / REAL_CHATGPT_HOST_LOCAL_E2E_PASS / PR_UNMERGED`.
Earlier `IN_PROGRESS` and `NOT RUN` statements below are chronological checkpoint evidence, not the final status.

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

## Cross-platform architecture gate

Persistent-runtime E2E now adds the composition lifecycle, finalization service,
crash atomicity/projection recovery, orchestrator pipeline/historical parity, runner
contract and legacy cutover tests to both Linux and Windows. Local execution of
this exact added matrix: **43 PASS**, 49.60 seconds. Existing workflow steps and
assertions are retained. Its new remote results remain pending.

The five-hour usage checkpoint was pushed before the approximately 35-percent
remaining threshold: code 2a6829d, canonical metadata 9609016, followed by the
normal merge 3756a79 of identical automated metadata 1f46321. No history rewrite,
force push or PR merge occurred. Validation logs stay outside tracked runtime data.

## Lifecycle and last public caller follow-up

The second full local suite was **1 FAIL, 2097 PASS, 4 platform SKIPPED**.
Unlike the initial stop timeout, this failure was startup readiness timeout.
An isolated restart attempt also timed out at startup. A diagnostic process
wrapper retained exact package bytes and showed repeated safe-path checks during
manifest verification/marker writes. A single non-following lstat now preserves
POSIX symlink and Windows reparse/junction detection, reducing redundant metadata
queries. All protected file sizes and hashes still run on every verification.
Measured verification of the same 2021 files: 3.83 seconds before, 2.33 after.
Safety/path/integrity tests: **24 PASS, 2 platform SKIPPED**. No timeout or assertion
was relaxed. Three restarts and a new full suite remain required evidence.

Caller inventory also found default CLI direct text bypassing the session facade.
It now delegates to the same one-shot runner helper as named chat modes before
constructing any debug engine. The superseded direct process_turn branch is removed.
Cognitive-frame, explicit debug and bootstrap diagnostics retain compatibility access.
The public direct-message routing regression: **1 PASS**.

External host acceptance remains **NOT RUN**: repository/loopback test execution does
not prove an actual ChatGPT application accepted display_exact/finalization. This
external evidence is separate from repository completion and CI merge readiness.

## Isolated restart soak result

The corrected soak harness uses a dedicated parent directory so its canonical
host-level workspace cannot collide with a prior synthetic MEMORY fixture.
Three consecutive start/status/doctor/stop cycles of the same runtime: **3 PASS**.
Each cycle proved trusted daemon identity, fully-ready transactional memory, a
single valid wake snapshot with unchanged snapshot_id/logical fingerprint, and
complete process/endpoint stop under the original timeouts. The earlier harness
attempt that reused a sibling workspace failed with an existing synthetic table;
it is not counted as a runtime PASS or used to conceal the initial startup failure.

Final follow-up Pyright: **0 errors, 1 existing warning, 1116 analyzed files**.
Compileall, RouteGraphAudit and CognitiveArchitectureAudit: **PASS**. The new
complete deterministic suite remains **IN_PROGRESS**. Final-SHA GitHub gates and
external real-host evidence retain their independent statuses.


## Final repository and real-host closeout — 2026-10-06

Final immutable v111 SHA:
`ee00529cdbd9a4d0a469007db787ed4895667ddf`.

Repository validation after the historical checkpoints above:

- local full deterministic suite: **2107 PASS, 4 platform SKIPPED, 0 FAIL**,
  527.09 seconds, one expected duplicate-ZIP warning;
- Pyright final SHA: **SUCCESS**;
- release-hardening: **SUCCESS**;
- persistent-runtime E2E: **SUCCESS** on Linux and Windows;
- package-distribution-cleanroom: **SUCCESS**;
- PowerShell full suite/package smoke/clean checkout: **SUCCESS**;
- PR #321 rollup: **51 SUCCESS, 2 SKIPPED**; skipped metadata/redundant
  finalization jobs remain SKIPPED rather than being relabeled PASS.

### Actual ChatGPT-host E2E

The previously missing external-host evidence was executed in a real ChatGPT
conversation on 2026-10-06 using the final v111 GitHub Actions Linux system artifact.

Package evidence:

- workflow run: `37410740819`;
- artifact: `jazn-package-linux-x64-py3.12`, artifact id `11389445665`;
- outer artifact SHA-256:
  `541def22dbd2f6f0ea88ffa4cc3cc259f175b176806164d5290b87283986d613`;
- inner SYSTEM ZIP SHA-256:
  `aa9ba3cb8182b4fb63617f7e850d73039eb20731d7ab8849ca07de8d45d5356c`;
- ZIP CRC/path audit: PASS, 2025 entries;
- stdlib-only `CHATGPT_BOOTSTRAP.py` verified/materialized the operator and
  `host-preflight` selected `local_executor`;
- live status then reported `system_fully_ready=true`, daemon identity/root/PID
  verified, fresh heartbeat and finalization ready.

Turn evidence was bounded and replay-safe:

- request id:
  `chatgpt-v111-3e423b5c5af14f9b9d71a9b4ace83388`;
- turn id: `6545d98a-35ea-4a0d-8c7a-f8af41a9880b`;
- user-text SHA-256:
  `88b39175f6ff3919870eaf7c1f797d77255b6dc1e5787a1faa41baabec56f6d3`;
- durable host-request contract:
  `d019552d5a08acf3eb00251147caa3f383beb01a458170ad0caee2aaf60b8bcc`;
- first phase-2 attempt used the wrong contract hash and was rejected
  `host_request_contract_hash_mismatch`; the user message was **not replayed**;
- the same durable request was polled/resumed and finalized with the correct binding;
- finalization returned `accepted=true`;
- `turn_authority_validation.ok=true`;
- `accepted_visible_turn_ready=true`;
- `action=display_exact`;
- `visible_output_source=runtime_finalized`;
- turn-authority receipt SHA-256:
  `dcd8f7300a5c9f9f6870862ac4d14ffc6f474775d86387c56bb6f0997c6f9d14`.

This proves the **local-executor real ChatGPT host route** for v111. It does not
prove a deployed/callable public MCP or Secure MCP Tunnel route; that remains a
separate deployment capability.

Primary current protocol/product references checked for this closeout:

- https://tasks.extensions.modelcontextprotocol.io/specification/2026-07-28/tasks
- https://ts.sdk.modelcontextprotocol.io/v2/protocol-versions
- https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt

No PR merge is authorized by this evidence.
