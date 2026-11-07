# Jaźń / JSS — ROOT-local prerequisites and self-contained first-run installer

Status: **IMPLEMENTATION IN PROGRESS; NOT RELEASE-READY** (2026-11-06).
Base `master`: `5adef1d6e3c911f9ccd0bf884b32c0364c866481`.
Branch: `codex/jss-root-local-resources-venv-ollama-20261106`.
No tests or release sync may be recorded as PASS without a real executor/CI log.

## User requirements and intended truth boundaries

A new verified SYSTEM root must keep `local_resources/` and the locally
created `.venv/` immediately beside `run.py`, `main.py`, and `latka_jazn/`.
The JSS installer must detect/install Python 3.14, create/verify/repair the
ROOT-local environment, install all CLI+JSS required packages offline or
online, detect/install/start Ollama using an official Windows installer or
CLI/application, discover existing models, default to `gemma3:latest`, allow
multiple user-selected models, stream download progress, and confirm a real
model generation. No manual pip/terminal commands should be required for a
normal GUI installation after a trusted bootstrap entrypoint becomes available.

No installer action makes Ollama the owner of Jaźń's memory, lifecycle,
conversation finalization or truth gate. No installer should replay turns,
move MEMORY, edit SQLite/WAL/SHM or stop a live daemon.

## Intended directory contract

```text
<verified SYSTEM ROOT>/
  run.py
  main.py
  latka_jazn/
  .venv/                         # target-machine-generated; never in Git / SYSTEM ZIP
  local_resources/
    README.md                    # versioned guidance
    python/                      # marker, optional runtime installers and metadata
    wheelhouse/                  # SHA-256-locked core+run-studio wheels
    ollama/                      # optional installer resources
    models/                      # optional user-controlled OLLAMA_MODELS storage
    nlp/                         # optional dictionaries/models
    manifests/                   # installer receipts
  workspace_runtime/             # independent operational daemon state, if configured
```

For existing installations without `ROOT/local_resources`, the old
host-workspace dependency state remains discoverable. A fresh ROOT with
`local_resources/` chooses the new layout. A legacy environment marker may
be read as fallback; no data migration or deletion occurs automatically.

## Implementation checkpoint

- [x] Branch created from verified master SHA.
- [x] ROOT-local layout resolver with read-only legacy marker fallback.
- [x] New installer controller (explicit approval; Python 3.14 and venv).
- [x] Dependency Studio online wheelhouse download delegated to canonical resolver.
- [x] Verified offline wheelhouse consumption into ROOT/.venv with pip check.
- [x] Explicit Python/Ollama WinGet install options, CLI/app Ollama launch.
- [x] Ollama /api/tags inspection, default gemma3:latest pull and model selection.
- [x] Nonblocking QProcess integration in JSS first-run wizard.
- [x] Initial unit/Qt regression tests committed, awaiting execution.
- [ ] Complete root-.venv activation marker/inventory parity with Dependency Studio v2.
- [ ] Verified offline core+run-studio **binary wheelhouse included in packaged distribution** for supported targets; source repo must NOT ship random wheels or portable venv.
- [ ] Python bootstrap entrypoint works on a machine without Python/PySide6 and remains compatible with packaged JSS.
- [ ] Explicit, safe repair/update/rollback of existing ROOT/.venv, including live-daemon coordination.
- [ ] Configure optional ROOT/local_resources/models location via OLLAMA_MODELS without changing already running external Ollama.
- [ ] End-to-end model generation acceptance after installation.
- [ ] Test on clean Windows x64 Python 3.14 (CLI, JSS GUI, WinGet, Ollama, two turns, reconnect/resume).
- [ ] Linux/Windows compatibility and full regression gates.
- [ ] Canonical package version bump and release_metadata_sync from a real executor.
- [ ] Release manifests, provenance, dependency sidecar hashes, CI and distribution acceptance.

## Required acceptance evidence (none claimed as PASS yet)

1. No downloads/installs during normal chat or read-only status.
2. No changes to existing host-workspace MEMORY, SQLite, checkpoints or live daemon.
3. Clean Windows 10/11 x64 installation with no existing Python, JSS or Ollama.
4. Python 3.14 `-I` probe, `ROOT/.venv/Scripts/python.exe` verification.
5. All CLI+JSS packages in ROOT/.venv after verified offline install, `pip check`,
   direct import smoke, `pip inspect` inventory equal to manifest.
6. Online mode regenerates version/target-locked wheelhouse; offline mode does
   not contact any package index. Wheelhouse SHA/RECORD verification must fail
   closed on corruption.
7. Official WinGet package IDs and publisher/source; interpreter and
   binary versions verified after installation.
8. Both `ollama serve` and Windows app launch have separate readiness checks;
   occupied/foreign port must not be silently adopted.
9. `gemma3:latest` default; selected multiple models, download progress,
   interrupted download recovery, and real `/api/chat` `done:true`.
10. No upgrade of a venv in use by a live daemon; rollback retains old env.
11. Mandatory pytest + Qt, JUnit and individual TXT/JSON evidence with
    NO implicit PASS for skipped/blocked tests; final full matrix on HEAD.
12. `run.py host-preflight`, `run.py start`, `run.py status --json`,
    two accepted Ollama turns, reconnect and phase-2 finalization.
13. Canonical release metadata sync, package smoke and clean-room Windows/Linux
    verification; release not ready until all this evidence exists.

## Upstream references

- CPython 3.14 venv: https://docs.python.org/3.14/library/venv.html
- Microsoft WinGet Python: https://learn.microsoft.com/en-us/windows/python/beginners
- Microsoft WinGet install: https://learn.microsoft.com/en-us/windows/package-manager/winget/install
- pip offline/wheels: https://pip.pypa.io/en/stable/cli/pip_install/
- Qt QProcess asynchronous lifecycle: https://doc.qt.io/qtforpython-6/PySide6/QtCore/QProcess.html
- Ollama Windows: https://docs.ollama.com/windows
- Ollama models: https://ollama.com/library/gemma3/tags
- Ollama API: https://docs.ollama.com/api
