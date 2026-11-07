# Aktualizacja robocza V108 (PR #464)

Oddzielono zarządzany stan instalacji ROOT/.venv, ROOT/local_resources/python i ROOT/local_resources/wheelhouse od inwentarza niezmiennych plików SYSTEM. Kontrola wszystkich chronionych plików oraz odmowa nieznanego kodu pozostają obowiązujące. Testy TPA wymagają kompletnej aktualnej checklisty i dowodu dla bieżącego SHA; nie zmieniono historycznych wyników operatora.

# Aktualizacja robocza V107 (PR #464)

Zasady 22 scenariuszy i wymogi dowodowe pozostają obowiązujące. Wersja V107 poprawia walidację zależności i testy; historyczne wyniki dla poprzednich SHA/wersji nie oznaczają odbioru V107. Wszystkie nieuruchomione próby operatora nadal mają status `NOT_RUN`.

# TPA — Windows acceptance after V74 → V105/V106 convergence

Status: **OPERATOR ACCEPTANCE PENDING**. This file is guidance, **not evidence
that any Windows acceptance was performed**. Do not use a previous version's
PASS to approve the current candidate. The existing 22-case catalogue is
canonical and remains exactly 10 shared + 12 migration gates.

## Preparation

1. Keep the working V74 installation and MEMORY untouched. Use a separately
   extracted, SHA/manifest-verified SYSTEM release candidate or an isolated
   checkout of the exact integration commit. Record complete version and SHA.
2. Open JSS → **TPA — Testy przepuszczania aktualizacji**. First run the
   read-only source / provenance / marker preflight; never take PID, URL or
   "Python installed" alone as proof of daemon readiness.
3. Prepare a **separate** operator state / workspace / port. Test
   `ROOT/local_resources`, `ROOT/.venv` and dependency lock/wheelhouse
   on the candidate, not in the existing V74 directory. Use official
   Python 3.14 and Ollama distributions.
4. Keep all historical reports with their original source identity.
   TPA derives **NIEAKTUALNE** when the old version or SHA differs;
   it does not overwrite or silently promote old results. A prior
   outcome `PASS` is still historically meaningful, but not V105/V106
   acceptance. Review/archival use the existing manual history.
5. If the model, GUI, permission, Python, port, wheelhouse or executable is
   missing, record `BLOCKED` with a redacted log, **not** `PASS` or a
   fabricated test. An automated pytest regression `PASS` is not
   `full_gate PASS`. If test prerequisites cannot be met, stop this case
   rather than attempting to mutate the live V74 daemon.

## Scope of the 22 existing TPA cases

| TPA ID | Windows evidence to capture | Result before current-SHA operator execution |
|---|---|---|
| `gui-daemon` | Private ROOT, startup-preflight, matching /live instance, endpoint, heartbeat, cleanup | NOT_RUN |
| `ollama-two-turns` | Official Ollama + Gemma 3 generation, two accepted turns, exact session and response lineage | NOT_RUN |
| `chat-reconnect` | Same session after GUI transport reconnect, no duplicate responses | NOT_RUN |
| `chat-resume` | Same request_id, no replay, accepted finalization and ACK after display | NOT_RUN |
| `daemon-restart` | Authorized restart of *test-owned* daemon only; new instance_id and session continuity | NOT_RUN |
| `smoke-isolation` | Unchanged foreign workspace, MEMORY and sentinel hashes before/after | NOT_RUN |
| `config-persistence` | Candidate-only ROOT config, .venv and local_resources discovery, save/reload | NOT_RUN |
| `studios-parity` | Twelve separate studio-* full-gate results on identical candidate SHA | NOT_RUN |
| `offline-exe` | Windows VM offline, verified wheelhouse, .venv, EXE, logs and signed source identity | NOT_RUN |
| `ui-accessibility` | Windows DPI 100/150/200%, 860×580, keyboard and installation wizard focus | NOT_RUN |
| `studio-system` | Source/version/provenance review, read-only diagnostics and rejection behavior | NOT_RUN |
| `studio-start` | Python/Ollama detection, own daemon start/status/stop, process ownership | NOT_RUN |
| `studio-configuration` | Preview, save/reload, CAS collision, backup/restore and unsaved edit protection | NOT_RUN |
| `studio-memory` | Synthetic database roles, provenance and memory diagnostics without private data | NOT_RUN |
| `studio-memory-rebuild` | Synthetic source plan/validate/cancel/report/export | NOT_RUN |
| `studio-test-studio` | Run history, selected pytest, cancel, JUnit/TXT/JSON and result identity | NOT_RUN |
| `studio-generator` | Candidate package plan, verify, split/join, bad-part rejection | NOT_RUN |
| `studio-dependencies` | Python 3.14 core+run-studio hash-locked offline .venv install, pip check/imports | NOT_RUN |
| `studio-python-runtime` | Official CPython 3.14 detect/install, interpreter/ABI validation, reuse | NOT_RUN |
| `studio-version-rebuild` | AST source identity, canonical metadata generation, backup/diff/rollback | NOT_RUN |
| `studio-chat-import` | Synthetic import plan/verify/deduplication and search | NOT_RUN |
| `studio-memory-restore` | Synthetic baseline, scan/plan/compare/backup/restore after confirmation | NOT_RUN |

`NOT_RUN` here means **no candidate-specific operator receipt has been
verified by this document**, not that older evidence never existed. The live
TPA list must compute results from its own RunStore and current source
evidence, never from this table.

## Recording and archiving

Use canonical TPA RunStore under the **external operator state**. Preserve
each run's `case_id`, source commit, version hash, synthetic execution root,
mode, execution status, `full_gate`, redacted TXT/JSON/JUnit, observation,
and any cleanup result. Keep historical files append-only. If a historical
test is no longer relevant, label its evidence *NIEAKTUALNE* based on
source SHA/version; do not delete it, force-archive a failing result,
or change a prior `FAIL` into `PASS`.

Do not use the existing V74 workspace or copy its live .venv. The
release candidate must pass CI **and** this separate Windows acceptance
before a release claim. Any scenario impossible to launch must have a
specific `BLOCKED` receipt with the prerequisite and reproducible steps.

## Official references

- CPython venv portability: https://docs.python.org/3.14/library/venv.html
- pip offline and hash checking: https://pip.pypa.io/en/stable/cli/pip_install/
- Ollama Windows: https://docs.ollama.com/windows
- GitHub current-SHA required status checks:
  https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
