# Jaźń 16.3.25.5.116.0.34.94.6.13 — Studio startup and operator diagnostics

**Scope:** Incremental patch atop PR #429, revision `f10b633b`. Draft; not deployed.
No modification to private MEMORY, SQLite, active daemon, existing worktrees or public MCP deployment.

## Verified local incident (operator screenshots/report)

Operator started GUI from `D:\.AI\jazn_latka_pr429`, Python 3.15; the system's official requirements report said core/GUI available but optional MCP/HTTP imports missing (0/4). The GUI showed:
- Readiness locked in the guided runtime → Ollama → chat workflow.
- `gemma3:latest` selected in a settings dropdown **without confirmed model availability**.
- Two probe failures reported as `URLError`, not the actual network class/recovery instructions.
- Runtime status returned exit 0 yet detected an existing **different** .10 master runtime at `D:\.AI\jazn_latka_master`. This is a root/version mismatch for a .12/.13 staging worktree, not proof that the master daemon has failed.
- Status/finalization and canonical MEMORY readiness are independent. The master runtime's memory archive is searchable while normalization/wake-state are stale. No local model generation or canonical ChatGPT turn was observed.
- In some screenshots, a duplicate log viewer and operator dock stacked at the bottom; very long JSON records became unreadable single-line text.
- Old TPA items still displayed .10, separate from the currently selected code branch; displaying a previous acceptance result must not be promoted to a new release PASS.
- GUI user observed `process_exit:1` for status and stop. This is insufficient by itself to infer that daemon state changed. No automatic retry or stop is performed.

## Implemented remediation

1. **Read-only local readiness scan:** one button checks canonical runtime status and available Ollama models. It launches neither a daemon nor a model download.
2. **Safe Ollama start-or-probe:** if loopback port 11434 is already listening, verify `GET /api/tags`; do not adopt, kill or restart that process. If the port is free, the existing Studio-managed `ollama serve` path is available. Readiness still requires a genuine API/model response and a separate generation test.
3. **Reasoned network errors:** classify `URLError` for refusal, timeout or unknown transport failure from `exc.reason`; avoid persisting raw exception URLs, headers or secrets. Each failure code has a short Polish explanation and a suggested operator next step.
4. **Actionable problem panel:** selecting a failure reveals recovery guidance; source and code remain visible. An optional MCP failure never implies a broken local runtime.
5. **Output legibility:** an error no longer automatically expands a second bottom pane. The operator dock and legacy log pane are mutually exclusive when explicitly opened. Displayed lines longer than 600 characters are shortened *only in the view*; raw bounded in-memory event data and sanitized full report are not mutated.

## Independent verification and unresolved gates

- New tests: `tests/test_heart_studio_operator_diagnostics.py` and `tests/test_heart_studio_operator_diagnostics_qt.py`.
- Do **not** assert production readiness until Windows Qt smoke, local Ollama model generation, ChatGPT OAuth/MCP tool discovery and accepted phase-2 completion succeed.
- The Python 3.15 environment is not the same as the project's validated 3.12–3.14 CI matrix. Install missing optional packages only through the project's approved Dependency Studio and independently selected compatible interpreter; do not run blind `pip install` commands in the daemon environment.
- Treat memory recovery, normalization and wake-state generation as separate authorized maintenance; never mutate `memory/` automatically to unlock chat.
- Confirm metadata synchronization and idempotency with `python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json` **only in a verified isolated build worktree**; this commit does not hand-edit `PACKAGE_INTEGRITY_MANIFEST.json` or `SOURCE_PROVENANCE.json`.
- As of patch writing, runtime and private-memory changes were **not** executed on the user's Windows machine. Unit/Qt CI results must be inspected after PR creation.

## Primary sources

- Qt for Python QMainWindow/QDockWidget state and user layouts: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QMainWindow.html
- Python urllib exceptions (URLError.reason): https://docs.python.org/3/howto/urllib2.html
- Ollama local API, list models and chat: https://docs.ollama.com/api
- Jaźń canonical commands, memory and lifecycle: `AGENTS.md`, `AGENTS.codex.md` and `run.py` at this branch.

This document describes a code change and its intended acceptance path, **not** a successful local Jaźń turn.
