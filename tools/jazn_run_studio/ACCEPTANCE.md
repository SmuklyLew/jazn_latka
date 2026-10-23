# Scope, evidence and remaining gates

Baseline verified on 2026-10-22:
`master = origin/master = 2503ccdc407cc733e4282372173dd17b3e3be068`.
Working branch: `codex/jazn-run-studio`. No merge is authorized.

The audit found the existing system/operator, Configuration, Memory, Memory
Rebuild, Tests, Package Generator, Dependencies, Python Runtime and Start
studios. Their public entrypoints are listed in the shared `STUDIOS` registry.
Existing reusable contracts include Configuration Studio validated profiles,
operator-root verification, public lifecycle commands, HTTP probes and local
Ollama final rendering in `chat_command_contract.write_local_ollama_visible_reply`.
The source audit is not yet an exhaustive review of every source file.

## Milestone 1: operator foundation

Implemented: Python/Qt desktop shell and public launcher; shared terminal/backend
actions; separate logs and job state; diagnostic batches; owned-child controls;
root and executable validation; secret-free settings; five appearance modes;
official installer links; existing-studio launcher catalog; About page; report
export; optional dependency profile; native build script; dedicated CI workflow.

Local verification (Windows, isolated Python 3.14.4, Qt 6.12.0):

| Gate | Outcome / evidence |
| --- | --- |
| New operator and GUI tests | PASS: 25 tests included in related regression run |
| New + existing operator/config/start/dashboard tests | PASS: 79 passed, 3 skipped, 3.98 s |
| Focused Pyright with explicit interpreter | PASS: 0 errors, 0 warnings |
| Source startup / GUI smoke | PASS: exit 0 |
| Native PyInstaller build | PASS: controlled build PATH; Windows onedir EXE GUI smoke exit 0 against explicit external SYSTEM/interpreter |
| GitHub Actions SHA / Node24 audit | PASS: 22 workflows, no findings; three reused action.yml files verified upstream |
| Compile active Python excluding historical archive | PASS |
| Required unfiltered compileall | FAIL: existing syntax error in immutable historical `tests/archive/v16.3.25.5.115.5-mcp-exposure-compat/test_fast_bootstrap_persistent_runtime.py:242` |
| Baseline status / doctor | Commands executed; no daemon or accepted visible turn established |
| Full deterministic suite | NOT RUN at milestone 1 |
| Native Windows/Linux offline wheelhouse | NOT RUN |
| Live model + runtime chat | NOT RUN / not yet implemented in this desktop shell |
| GitHub CI | Draft PR #409; initial Linux EGL and Windows interpreter failures; corrections under validation |

The first pytest attempt could not create its default sandbox temporary folder.
An explicit writable `--basetemp` resolved the environment error. The subsequent
test run caught invalid JSON from re-redacting serialized reports; values are
now sanitized before JSON serialization, and the unchanged assertion passes.

Related existing unittest fixtures also needed writable TEMP/TMP, rather than
only pytest basetemp; no test assertions were modified. Initial frozen startup
failed because PyInstaller found a foreign ICU DLL on PATH (20 missing ICU
entrypoints). Qt's source import uses the Windows ICU. The build now scans a
controlled Windows PATH and the rebuilt EXE smoke passes; a regression test
checks foreign DLL directories cannot enter that scan. A debug artifact was
modified only to isolate this cause; the passing non-console build was generated
from the corrected build script without artifact surgery.

## Milestone 1b: cross-platform CI corrections

The `.43` checkpoint is pushed as `eec4d5acef9964717d1600344ba19a329ba0c24c`
(content source `1fd74de09f2b6332b960ffa1417102c17058c4c3`) in draft
https://github.com/SmuklyLew/jazn_latka/pull/409. Independent metadata check:
PASS, synchronized=true, manifest_matches=true, provenance_matches=true,
3292 static files. A Windows EXE built from that committed source passed GUI
smoke, exit 0; its SHA256 was
`3F8340C53B3A7F90B74FC20562DEFC832AF4E7EFA3BAA9CC28903C08F7D72D49`.

CI on the initial checkpoint caught missing Linux `libEGL.so.1` and Pyright's
failure to resolve imports when passed relative `--pythonpath python` on
Windows. `.44` adds Linux graphics libraries and an absolute-running-interpreter
type-check wrapper. The GUI test selects Qt offscreen only on headless Unix;
it still executes all navigation/theme assertions. Its prior committed source
is preserved byte-for-byte in the versioned test archive. Local revalidation:
25 passed in 2.59 s; the new type-check wrapper reports zero errors/warnings.

Preparing optional dependencies for a full local suite hit two PyPI read
timeouts (including a retry with a longer package-download timeout). Runtime
and test timeouts were not changed. Full local testing remains NOT RUN; resolve
the download route or use completed remote evidence before claiming it passed.

## Required next milestones (not completed)

1. Verify the final committed-source EXE and complete packaged notices.
2. Complete HTTP/Ollama model/readiness probes, Cloudflare Windows service
   observation, MCP readiness and the settings/profile/secrets workflow without
   logging sensitive values. Test start/stop/restart failure, timeout, ownership
   and concurrency for every service, including pre-existing services.
3. Integrate persistent local runtime chat through canonical `chat-ollama`
   JSONL: stable session/request identity, accepted final rendering through the
   existing validator, no replay on ambiguous transport, and a real Ollama E2E.
4. Migrate all existing studios to shared appearance and functional Qt pages,
   reusing their business logic. Opening a legacy window is not full integration.
5. Improve the user-facing dashboard from raw diagnostic JSON to clear service
   summaries; verify keyboard navigation, DPI, system theme changes and custom
   color contrast. Complete interactive visual QA on Windows and Unix.
6. Materialize and verify native offline dependency bundles, run the full
   repository suite, type checks, doctor/package/release gates and final-SHA CI.
   Record every PASS, FAIL, SKIPPED and NOT RUN separately. Resolve failures
   without weakening existing tests or changing immutable archives.
7. Finish the reviewable PR with installation, build artifacts, exact test
   results and known limits. Never merge without explicit user instruction.

The live model, external ChatGPT acceptance and Cloudflare credentials are not
inferred from a running PID or a successful loopback test. Source/GUI/build
success is not proof of a finalized runtime turn.

## Continuation details

Checkout: `D:\.AI\jazn_branchs\jazn-run-studio`.
Isolated development interpreter:
`D:\.AI\codex_tasks\jazn-run-studio-env\Scripts\python.exe`.
Use explicit interpreter paths: the default system `python` launcher tried to
download a runtime in the sandbox. Keep private/ignored data and build artifacts
out of commits. Commit named source paths only; unfiltered compileall created
untracked bytecode inside historical archive trees, which must not be staged.

The 5-hour platform window showed 78% remaining at the most recent milestone
implementation check. Refresh the platform tool before making later budget claims.

## Milestone 2: services, local chat and shared operation forms (.45)

Implemented persistent public chat-ollama transport, durable session/request
checkpoint without prompt content, same-request result retrieval, and an external
SYSTEM-side validator reusing write_local_ollama_visible_reply. No candidate is
shown as runtime speech before acceptance, request binding and turn/trace checks.
The canonical JSONL bridge now forwards an explicitly supplied request_id to its
existing daemon session; it previously dropped that field.

Read-only probes cover Ollama models, local HTTP readiness, configured Cloudflare
Worker readiness and Windows cloudflared service observation. The selected local
model endpoint currently reports gemma3:latest; this alone is not a chat pass.
The dashboard now uses readable component rows rather than raw JSON.

Shared Qt forms describe and execute original Memory/Rebuild, Tests, Packages,
Dependency and Python Runtime argparse commands. Profiles are edited via the
existing Configuration Studio validators and CAS save. A secrets-file selector
loads only allowlisted secret keys into child environments and redaction. The
frozen subprocess environment follows PyInstaller guidance for DLL/library paths.
Classic specialized windows remain explicitly available, including Version Rebuild;
these rich visual inspectors have not all been reimplemented as native Qt widgets.

Focused validation: 44 Studio tests passed in 4.67 s; related runtime/contract run
passed 66 tests before the final helper test was added. Focused Pyright reports
zero errors/warnings. .44 dedicated Windows/Linux tests and Windows package CI
are SUCCESS; .44's full-PR failures identified stale startup/deployment versions
and a dependency-sensitive build test. .45 updates the two non-integrity release
contracts, preserves the exact original release-hardening installation command
and adds Qt separately, and makes the DLL-path unit fixture dependency-independent.
No existing assertion was weakened.

Still required before completion: current-source full suite and CI, actual live
chat acceptance, frozen external command integration, offline Qt wheelhouse
evidence, process/service restart failure coverage, and richer visual/keyboard/DPI
acceptance. The broad original objective is not marked complete by these focused
results. The current source remains a reviewable implementation checkpoint.
## Milestone 3: acceptance evidence and cross-platform type fix (.46)

- 56 focused Studio/host-turn-coverage tests passed with PYTHONUTF8=1; focused
  Pyright reports zero errors/warnings. Linux CI on .45 identified an indirect
  platform guard around ctypes.WinDLL. .46 adds the explicit sys.platform guard
  required by the platform-specific types; behavior on Windows is unchanged.
- .45's native Windows EXE passed both GUI smoke and external `--run version`,
  exit 0. Qt/shiboken license metadata is present in the onedir artifact.
- Dependency Studio downloaded core+run-studio, verified all four wheel RECORDs
  and the generated hash lock, then installed a fresh environment with --offline.
  Its Python imported Qt 6.12.0 and ran GUI smoke successfully. The generated
  native Windows/Python 3.14 lock was preserved byte-for-byte under `locks/`.
- Node 24.20.0: npm ci, syntax check, ESM probe and canonical runtime probe passed.
- Full local deterministic suite on .45: **9 failed, 2900 passed, 21 skipped,
  7 warnings, 330.39 seconds**. This is a FAIL, despite the focused passes.
  A missing inherited PYTHONUTF8 setting explained two CLI decoding failures;
  with that environment corrected those coverage tests pass unchanged.
- Focused comparison on untouched master reproduces the three runtime
  time-route/persistence failures, the unreadable optional-memory test failure,
  and the MCP process/SSE IncompleteRead failure. The full master comparison is
  complete: 6 failed, 2859 passed, 21 skipped, 6 warnings in 337.01 s. It also
  reproduces the Tk GUI failure; the recall test passed on master. None of
  these assertions or runtime truth gates were weakened for this branch.
- First live chat test on a working checkout stopped at runtime preflight,
  preserving its request ID. Canonical staging then produced a verified .45
  SYSTEM export with manifest_ok=true, provenance_ok=true, needs_recovery=false.
  A separate new test turn on that export timed out after 180 s without an
  accepted visible reply. Its durable request ID is preserved, the earlier
  message was not replayed, and canonical cleanup returned exit 0. This live
  acceptance is FAIL; the cause still requires investigation.

Remaining acceptance is explicit: final-SHA CI and metadata check, a successful
real model turn with lineage/finalization, native Linux Qt offline installation,
full passing runtime suite or reviewed resolution of the reproduced base
failures, and complete replacement of specialized legacy visual inspectors.
This file documents evidence and limits rather than declaring the original broad
objective complete.

Final code evidence for 3a874f9f335f73d2c30fdebf323b91cb0e656aec:
native Windows build and both frozen GUI/external version smoke checks passed.
GitHub full active-tree Pyright passed. Studio tests, types and GUI smoke passed
on Ubuntu Python 3.12/3.14 and Windows Python 3.14; Windows Python 3.12 remains
queued at this checkpoint. The Windows package CI job passed. These are results
for the source commit, not a claim that all final-head PR checks are green.

The repeated .46 full suite with PYTHONUTF8=1 has not completed at the time
of this source checkpoint (last progress: 14%, in the MCP descriptor area).
Its final status is recorded separately in the checkpoint/PR; no full-suite
PASS is inferred from the focused results.

## P0 continuation: actual result binding (.47)

The completed .46 HEAD CI has one red workflow (PowerShell Tk), with the other
checks successful or explicitly skipped release finalization. A new complete
local .46 run with local-network permission reports 2904 passed, 21 skipped,
5 failed in 354.71 s. Tk and recall pass in this run. The earlier 14% stall is
diagnosed by a stack dump: Windows asyncio's socketpair blocks in accept in the
restricted executor. The same MCP test passes with local-network permission.
This is execution-environment evidence, not a reason to weaken tests.

A real .46 Ollama turn returned answer_ok=true, final_visible_answer, valid
integrity and no pending host finalization. Studio rejected it because the
completed daemon result retains request_id inside daemon_job, not at top level.
.47 validates that canonical binding, rejects all conflicting IDs, additionally
binds the expected session and checks turn/trace agreement with the final
contract. It still delegates final text acceptance to the existing runtime
validator. Regression tests use the real canonical daemon unwrap function.

Structured multi-line startup errors are now parsed as bounded object frames
and reported by error code without exposing candidate text or replaying input.
No timeout was enlarged. The optional-memory failure was a Python 3.14 Windows
test fixture assuming is_file calls Path.stat; its replacement injects the same
PermissionError independently of call count, preserving all assertions. The
previous committed test bytes are archived unchanged.

The .46 local full-suite failures still being diagnosed are MCP HTTP framing and
three time-route/persistence cases, plus that now-repaired fixture. Real live
chat acceptance on the new committed source, Windows Tk CI diagnosis, complete
studio migration and the remaining original acceptance requirements remain open.

## P0 continuation: operation results and deterministic isolation (.48)

Actual Qt chat on the committed .47 export displayed two accepted real Ollama
replies with a stable session, unique request/turn/trace IDs, matching hashes and
canonical final validation. The interruption/recovery scenario needs a harness
race correction: it attempted to resume after the result had already completed.
This proves the two visible turns, not the entire recovery/failure matrix.

The complete master control reports 2859 passed, 21 skipped and 6 failed in
386.94 s. All five failures from the new .46 run also occur on that base. Three
time/persistence failures were traced to live auto-routing into Ollama despite
the tests selecting a null adapter. Explicit JAZN_LLM_ROUTE=off makes those same
three tests pass without changing any assertion. The factory intentionally
auto-routes null/auto configurations; tests now disable that route explicitly.
Their prior committed bytes are archived unchanged.

The public lifecycle CLI previously returned exit 0 after failed daemon start
or stop. .48 propagates the actual ok status, removes argparse's leading option
separator for start/stop (preserving chat message separators), and makes Studio
also reject an old runtime's ok=false JSON even when its process returns 0.
Nineteen targeted lifecycle/persistence/CLI tests pass after these changes.

The independently dispatched master PowerShell workflow passed its Tcl/Tk GUI
steps; local real Tk tests also passed, as did 200 repeated configuration-window
test cases. No Tk asset absence was reproduced in these controls. The original
red run remains historical evidence; current source CI still requires review.
Local MCP HTTP framing is being investigated separately: raw network capture
contains a chunked header with an unchunked JSON body. Do not claim a local MCP
catalog pass until this transport discrepancy is explained.

## P0 continuation: malformed HTTP diagnostics (.49)

An isolated gateway diagnostic records the h11 server writing Content-Length
and the complete JSON body. The receiving raw socket instead sees
Transfer-Encoding: chunked and that same unchunked body. This independently
locates the malformed framing between server serialization and client receipt.
The exact intermediary is not identified; installed antivirus names alone do
not establish attribution. The original master reproduces the catalog failure.

The catalog probe now returns mcp_catalog_invalid_http_framing rather than an
uncaught IncompleteRead traceback. Studio's service probe finishes as failed
instead of retaining a running state when that HTTP exception occurs. Neither
path accepts malformed content or exposes its raw bytes in the diagnosis.

A fresh .48 public cold start correctly fails with a nonzero exit code when
the daemon does not reach verified liveness within its existing budget. Local
profiling measured a full 3308-file export verification at 5.61 seconds. An
experimental parallel verifier improved that to only 5.02 seconds; the experiment
was removed and no integrity verification, caching or timeout policy changed.
Cold export startup and interrupted-transport real GUI acceptance remain open.

## Native GUI and selection safety (.50)

Native Windows Qt captures (not the offscreen platform) were rendered at
1240x840 and 860x580 in four themes; keyboard Home/Down navigation was exercised.
Visual inspection found horizontal overflow on the service page at minimum
width. .50 uses short control rows and wrapped service/remote-host descriptions;
a regression requires no horizontal scrolling on that page at the supported
minimum width. Selecting another studio also clears its old form and rejects a
delayed schema from the previous selection, preventing unintended old operations.

The active-memory E2E's synthetic subject also explicitly selected null while
leaving automatic routing on. Its fixture now disables that route, preserving
the complete real memory/lineage assertions. Its prior committed bytes are
archived. Focused layout, memory E2E and existing Studio tests: 41 passed.

The complete migration inventory is in STUDIO_MIGRATION.md. It includes the
additional cursor import/restore tools and separates canonical command exposure
from specialized GUI parity. Several rows remain partial and are required work.
The repeat live test's first turn timed out while the full suite was also using
the real model; no multi-turn recovery PASS is claimed from that run. Its durable
request is retained. The two accepted .47 GUI turns remain valid earlier evidence.

## Frozen redirected diagnostics (.51)

The clean .50 full run completed: 2937 passed, 21 skipped, 1 failed in
302.65s. The remaining real MCP HTTP smoke fails on malformed framing; the
independent server/socket evidence above does not establish a passing route.
Doctor and SYSTEM package-smoke both exited 0; package-smoke ok=true.

The .50 console EXE status action exposed a Windows cp1250 UnicodeEncodeError
when output was redirected. Two new regression cases reproduced the failure
before the fix. .51 explicitly sets UTF-8 on available output streams and
child-process pipes, retaining strict encoding. Native rebuild and the same
redirected status action are required before accepting this correction.


## .52 Windows shutdown acknowledgment ordering — PR #410

This is a continuation branch based on the original Studio PR #409, not a declaration that the full original scope is accepted.

**Baseline failure:** final .51 GitHub Actions [package-distribution-cleanroom 39870162434](https://github.com/SmuklyLew/jazn_latka/actions/runs/39870162434) failed in the Windows 3.12, 3.13 and 3.14 cleanroom consumer jobs. The daemon's `stop` result returned `daemon_stop_timeout`; the expected daemon process was still alive, and the HTTP `/shutdown` response timed out. This is evidence of incomplete shutdown, not evidence of a successful stop.

**Changed behavior:** an authenticated `POST /shutdown` immediately requests shutdown and schedules the background shutdown worker **before** responding to the client. The reply is a short, identity-bearing JSON acknowledgment. Heavy marker status construction no longer delays scheduling the stop; the canonical daemon finalizer still writes the actual stopped marker and cleanup evidence. No endpoint/PID stop gate, source integrity check, privilege gate or production timeout has been weakened.

**Regression tests added:** tests for a normal ACK, simulated client disconnect during ACK, and a rejected unauthenticated stop. These unit tests are not substitutes for the native Windows cleanroom.

**Pending verification:** all final-head checks and a clean Windows cleanroom stop on Python 3.12/3.13/3.14. The observed client timeout may be caused by multiple interacting teardown delays; do not claim root-cause closure until native tests pass. Original open gates (real transport-resume acceptance, MCP HTTP framing, specialized Qt Studio parity, DPI/accessibility and Linux offline Qt) remain open.


## .55 operator probe readiness truth — pending final CI

Source changes on `fix/jazn-run-studio-windows-daemon-shutdown-20261023` separate completed endpoint queries from usable capability. Gateway and Cloudflare probes with `ready=false` retain the evidence payload but the Studio operation ends `failed/service_not_ready`; HTTP 200 alone is not operational proof. The Ollama probe marks a configured model missing from `/api/tags` as `failed/selected_model_missing`. A listed model is not proof of generation. New `tests/test_jazn_run_studio_probe_readiness.py` covers HTTP 200/401/503, both readiness states and model match/mismatch. The canonical daemon `/shutdown` logic and memory data were not changed.

**Verification boundary:** the source edits are committed to the feature branch through GitHub. Final-source Pyright, full Windows/Linux cleanroom, GUI smoke, canonical manifest synchronization and end-to-end functional chat have not been independently verified at the time of this source checkpoint. Keep PR Draft until all gates actually pass. No claims are made about the user's local PC.
