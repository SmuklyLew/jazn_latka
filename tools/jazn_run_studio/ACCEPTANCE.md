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
