# Safe checkpoint status

Checkpoint captured after implementation and CI diagnosis, before publication
of the final local corrections. The authoritative continuation record is
`RESUME_STATE.md`.

## Git identity

- branch: `upgrade/package-generator-v10.1.86.0-rewrite`;
- base/master: `635e9674abe8163a943b922a84b4fe4fb258143f`;
- implementation HEAD before this documentation-only checkpoint commit:
  `020b60ca7e10b4f10a04078e06dcd3e34e966b0a`;
- last pushed branch head: `b8bc63ffd5fc103f16d6ae8c4e8855288dda177b`;
- pre-checkpoint working tree: clean, with no staged or unstaged tracked files;
- local branch was two commits ahead of its remote-tracking branch before this
  documentation commit;
- no push, new PR or merge is authorized as part of this checkpoint.

## Work state

| Area | Status | Evidence |
|---|---|---|
| audit and three-way file classification | DONE | `FILE_CLASSIFICATION.md` |
| generator-only rewrite | DONE | version-neutral sources plus bundled public launcher |
| old generator archive | DONE | exact `R100` moves under `archive/pre-v10.1.86.0/` |
| generator/system contracts | DONE | wheelhouse v3 and dependency artifact v2 |
| cross-target policy | DONE locally | native lock creation plus foreign hash-locked replay |
| CI portability fixes | DONE locally | compatible manylinux tags, canonical LF lock bytes, raw deterministic Base85 |
| local validation | PARTIAL | focused suites pass; final full suite/smoke still required |
| release metadata | PARTIAL | passed before checkpoint docs; must be regenerated after them |
| publication | PARTIAL | earlier push and PR #214 exist; latest local commits are unpushed |
| merge to master | NOT RUN | explicitly outside authorization |

## Latest validation evidence

- deterministic builder check — PASS, `bundle_fresh=true`, source-set SHA-256
  `fcead7c054fbf29f68eb69d8211d19e9f48e7ff1f43f88462b0722b08f4b4871`;
- active compileall — PASS;
- five changed-area test files — PASS, `46 passed`, one expected duplicate-ZIP
  warning;
- active generator/dependency/distribution selection — PASS, `95 passed,
  1 skipped`, one expected duplicate-ZIP warning;
- three additional dependency boundary files — PASS, `6 passed`;
- metadata check — PASS for source commit `25c68b4...`, `1098` files, before
  the checkpoint documentation changes.

Direct PowerShell test attempts produced `WinError 50`/previously `WinError 6`
while Python created child processes. Running the same tests through a clean
`cmd.exe` child passed. This is an executor/handle limitation, not a confirmed
code regression. No test was disabled or weakened.

## Remote evidence already obtained

- existing PR: <https://github.com/SmuklyLew/jazn_latka/pull/214>;
- package workflow run `33839296643`: native builds succeeded; opposite-OS
  replay exposed CRLF/LF lock drift. The local fix is in `25c68b4` and is not
  pushed;
- release-hardening run `33839296416`: Ubuntu bundle freshness exposed
  zlib-version-dependent output. The local raw-Base85 fix is also in `25c68b4`
  and is not pushed;
- these failed runs motivated the local fixes; they are not final green CI.

## Stop boundary

Do not infer completion from this checkpoint. Regenerate metadata, rerun the
listed final gates, publish the existing branch, verify new CI and update the
existing PR. Do not create a replacement branch, rebase, force-push or merge.

## Historical pre-publication implementation status

The section below is retained as pre-first-push evidence. Its `NOT RUN` rows do
not describe the later checkpoint; the current state above and
`RESUME_STATE.md` take precedence.

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
