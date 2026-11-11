# V127.4 restart continuity checkpoint path regression baseline

- Active test source: `tests/test_runtime_session_restart_continuity.py`
- Branch: `fix/v127-4-root-venv-single-interpreter-20261111`
- Source HEAD: `b3ef1f0f9dff6ff096f3da13e66ddacdbebf6644`
- Git blob SHA: `4d01c57b51b5cd103dc38fe479c6be601e51a1dd`
- Archived snapshot: `test_runtime_session_restart_continuity.py`
- Root cause: stale checks for `tmp_path/workspace_runtime` despite `RuntimeSessionStateStore.latest_path` respecting a ROOT-relative acceptance workspace from pytest fixture.
- Scope: tests only. Production checkpoint writer, wake binding, integrity and no-carryover behavior remain unchanged.

The archived file reproduces the original source verbatim.
