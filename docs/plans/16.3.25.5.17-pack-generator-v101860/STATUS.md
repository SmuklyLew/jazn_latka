# Pre-publication implementation status

This is the local evidence checkpoint captured before the first branch push.
Status values are `PASS`, `FAIL`, `SKIPPED`, `NOT RUN` or `BLOCKED`; a planned
gate is never reported as passed. Authoritative post-push GitHub states belong in
the pull request/checks rather than being predicted here.

| Gate | Status | Evidence |
|---|---|---|
| clean master/base preflight | PASS | local and remote master at `635e9674abe8163a943b922a84b4fe4fb258143f`; tracked tree clean before work |
| file classification before rewrite | PASS | `FILE_CLASSIFICATION.md` |
| immutable pre-change test snapshots | PASS | `tests/archive/v16.3.25.5.16-python-runtime-bundle-ci-hardening/` |
| deterministic generator build/check | PASS | local builder write and independent `--check` |
| changed-module compile | PASS | local `py_compile` |
| focused generator/dependency tests | PASS | `72 passed` |
| distribution/dependency/runtime test superset | PASS | PTY run: `146 passed, 2 skipped`, one intentional corrupt-ZIP warning |
| full active compileall | PASS | `latka_jazn`, active tests, entry points and generator sources compiled |
| Pyright | NOT RUN | unavailable locally (`No module named pyright`, no `npx`); release CI retains the gate |
| full non-live pytest | FAIL | `1374 passed, 7 skipped, 4 failed`; three failures re-passed outside the checkout, while the remaining isolated-doctor failure reports the locally missing declared dependency `rarfile` |
| direct checkout doctor | FAIL | expected local-environment boundary: ignored `.pytest-tmp`, Windows checkout line-ending differences and missing global `rarfile`; no release claim is made from this checkout |
| isolated current-tree package smoke | PASS | with `rarfile==4.5` supplied from an ignored test-only target: `14 passed, 0 required failed, 1 optional failed`; the optional source-manifest check is expected before the final metadata synchronization |
| package-smoke transport isolation regression | PASS | `12 passed`; the ChatGPT integrity turn now receives its own free port and marker instead of observing a trusted runtime on port 8787 |
| canonical metadata write/check | NOT RUN | must run after final tracked changes |
| branch push | NOT RUN | pending clean local commit |
| six native lock builds | NOT RUN | GitHub Actions after branch push |
| six opposite-OS lock replays | NOT RUN | GitHub Actions after branch push |
| six clean-room consumers | NOT RUN | GitHub Actions after branch push |
| canonical lock persistence/readback | NOT RUN | GitHub Actions after successful matrix |
| pull request | NOT RUN | created only after publication checks |
| merge to master | NOT RUN | outside this request; requires separate authorization |

Two non-PTY attempts of the 148-test distribution superset ended with the same
six Windows `WinError 6` subprocess-handle errors after `140 passed, 2 skipped`.
The identical selection in a real PTY passed `146/146` with two declared skips.
No test was disabled or weakened to obtain that result.

The first clean-release smoke before the transport-isolation correction produced
`13 passed, 2 required failed`: `doctor` because the host interpreter lacked
the declared `rarfile` dependency, and `chat_gpt_turn_and_integrity_consensus`
because fixed port 8787 belonged to another trusted runtime. A second current-
tree smoke with `rarfile==4.5` isolated under `.pytest-tmp` and a free per-check
port passed every required gate. The final release-profile smoke remains gated
on the source commit plus canonical metadata commit.
