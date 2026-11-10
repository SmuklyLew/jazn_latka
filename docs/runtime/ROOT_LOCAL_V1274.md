# V127.4 — ROOT-local workspace, Python and VS Code

## Contract

A prepared Jaźń SYSTEM (`ROOT/local_resources/` exists) must keep **all
operational runtime and daemon state under its own ROOT**. The default
is `ROOT/workspace_runtime/`. An explicit `JAZN_RUNTIME_WORKSPACE_DIR`
can select only a descendant of the same ROOT. A path traversal, external
absolute path or redirect through a symlink/junction is rejected before
runtime state is opened. Two versioned installations must never
implicitly share markers, sessions, capability tokens or MEMORY.

The existing `ROOT/.venv/` remains the **main runtime and Studio Python**,
created/verified by `setup.ps1 wizard` or `setup.sh`. Optional, disposable
pytest environments belong under
`ROOT/.settings_local/acceptance/dependency_environments/`.
Run Studio and temporary TPA runtime folders belong under
`ROOT/.settings_local/acceptance/`; they never share production
`ROOT/workspace_runtime/` or `ROOT/memory/`.

VS Code selects `ROOT/.venv` and searches only that environment by
default; `.vscode/settings.json` no longer declares a separate
`jazn_project` Python project.

## Existing installations (no automatic relocation)

This patch **does not copy, delete, migrate, start or stop** any prior
daemon, workspace, session, memory database or Python interpreter.
Old bare/host-managed roots without `local_resources/` retain their
existing external-layout resolver for backward compatibility. A prepared
modern ROOT with a configured **external** workspace will fail closed.
This is intentional: it is not safe to silently attach that workspace
to a fresh release.

For an installation currently using a sibling workspace (for example,
`D:\.AI\jazn_latka_v127_3_workspace`):

1. Keep that installation and its workspace unchanged while it runs.
   Do not change `JAZN_RUNTIME_WORKSPACE_DIR` in an existing daemon,
   edit SQLite/WAL/SHM or remove `JAZN_ACTIVE_RUNTIME.json`.
2. Stage V127.4 into a **new, distinct ROOT** and provision it with the
   canonical installer. Do not attach the old workspace.
3. Verify version, package manifest, SOURCE_PROVENANCE, host-preflight,
   the new internal runtime path and independent port before any daemon start.
4. To import historical state, prepare a **separate operator-authorized
   migration plan**, verify all active request/finalization ownership,
   cleanly stop the owning daemon, take and verify a consistent backup,
   and follow the project's canonical workspace/MEMORY migration tools.
   Migration is NOT provided or attempted by this layout patch.
5. A failed verification is a refusal, never permission to relabel
   a marker, change an instance ID, copy live WAL files or reuse a PID.

## Old `jazn_project` VS Code template

The previously referenced `jazn_latka_master/jazn_project` contains
an independent Python package template and `venv` (not `latka_jazn`).
Removing its mapping from repository VS Code settings does **not**
delete that folder or modify a running terminal on the operator's PC.
Before archiving the directory, check open terminals/processes and
verify no tasks explicitly reference its interpreter. Do not automate
its removal.

## Evidence and acceptance gates

- Targeted Python tests: `tests/test_v1274_root_local_workspace_layout.py`.
- Windows PowerShell parity is verified only by the Windows-specific
  regression in that file, not by a Linux PASS.
- Existing workspace, acceptance, security and installer regression
  tests must be rerun. Full CI and release metadata/provenance sync
  remain release gates separate from targeted tests.
- Verify a clean *fresh* V127.4 install on Windows: `setup.ps1 wizard`,
  `run_studio.py`, `run.py host-preflight --json`, independent daemon,
  Ollama test conversation, reconnect, accepted finalization.
- Never identify a reply as Łatka without the verified runtime lineage
  and accepted finalization for that exact turn.

## Official references

- [Python virtual environments](https://docs.python.org/3/library/venv.html)
- [VS Code Python environments](https://code.visualstudio.com/docs/python/environments)
- [Python pathlib path resolution](https://docs.python.org/3/library/pathlib.html)
- [Git linked worktrees](https://git-scm.com/docs/git-worktree)
