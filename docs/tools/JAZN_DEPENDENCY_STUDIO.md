# Jaźń Dependency Studio — versioned offline wheelhouse

## Status

`16.3.25.3.9-dependency-studio-offline-wheelhouse` introduces an operator-owned dependency layer for Python packages used by Jaźń. The goal is to make dependency availability explicit, reproducible and usable without PyPI during ordinary runtime activation.

The Studio is not a second package manager. It orchestrates standard Python `venv` and `pip` commands with Jaźń-specific profiles, manifests, SHA-256 verification and activation gates.

## Core invariants

1. The repository never copies or commits a ready-made `site-packages` tree.
2. Managed virtual environments are disposable and recreated locally.
3. Binary wheels live under the ignored local resource root or another explicit wheelhouse path; source Git keeps the tool, profile registry and contracts.
4. `download` is an explicit operator/network action.
5. Runtime autobootstrap never downloads from the network. It may only reuse a verified managed environment or install from a verified local wheelhouse.
6. A wheelhouse bundle is immutable. `update` creates a new resolution when bytes/versions change and keeps the previous bundle available for rollback.
7. `core` + `archive` are activation-required. Optional profiles do not silently become required.
8. `activation_ready=True` requires the activation dependency profiles to be satisfied by the current interpreter or a verified managed environment.
9. SHA-256 and recorded package metadata prove local byte identity relative to the manifest; they do not certify upstream package safety or legal compatibility.

## Canonical local paths

Default root:

```text
<jazn_root>/latka_jazn/local_resources/python/
```

Layout:

```text
python/
├─ wheelhouse/
│  ├─ core+archive__windows-x64__py312__<resolution>/
│  │  ├─ *.whl
│  │  └─ JAZN_WHEELHOUSE_MANIFEST.json
│  └─ ...
├─ environments/
│  └─ <platform>__py<major-minor>__<manifest-sha>/
└─ JAZN_DEPENDENCY_ENVIRONMENT.json
```

`latka_jazn/local_resources/` remains excluded from Git. A portable release may transport that directory or an external wheelhouse separately without changing the source-control contract.

Set `JAZN_DEPENDENCY_WHEELHOUSE` to an explicit external wheelhouse when the bundle should live outside the runtime root.

## Profiles

The canonical registry is:

```text
latka_jazn/resources/dependencies/profiles.json
```

Current profiles:

| Profile | Role | Source |
|---|---|---|
| `core` | runtime required | base `project.dependencies` except archive-only packages |
| `archive` | runtime required | `py7zr`, `pyzipper` |
| `studio` | operator optional | `memory-rebuild-ui` optional dependencies |
| `memory-cloud` | runtime optional | matching `pyproject.toml` optional group |
| `memory-cloud-server` | service optional | matching optional group |
| `polish-nlp` | heavy optional | Morfeusz/Stanza/spaCy/transformer NLP dependency group |
| `all` | aggregate | all profiles above |

This deliberately makes `py7zr` and `pyzipper` real activation dependencies because the archive subsystem already relies on them.

## Terminal commands

Audit declarations, imports and readiness:

```powershell
.\tools\Start-JaznDependencyStudio.ps1 audit
```

Build an offline wheelhouse for Windows x64 / Python 3.12:

```powershell
.\tools\Start-JaznDependencyStudio.ps1 download `
    -Profile core,archive `
    -Python 3.12 `
    -Platform windows-x64
```

Verify manifests, SHA-256, wheel ZIP structure, Name/Version metadata and recorded license metadata:

```powershell
.\tools\Start-JaznDependencyStudio.ps1 verify
```

Install the newest matching verified activation bundle into a managed local environment:

```powershell
.\tools\Start-JaznDependencyStudio.ps1 install `
    -Offline
```

Resolve a new archive dependency set without overwriting the old one:

```powershell
.\tools\Start-JaznDependencyStudio.ps1 update `
    -Profile archive
```

Measure local readiness/verification cost without network access:

```powershell
.\tools\Start-JaznDependencyStudio.ps1 benchmark
```

All commands support `-Json`; `download`, `update`, and `install` support `-DryRun`.

## Download contract

`download` uses pip's wheel-only resolution. For a Windows x64 Python 3.12 target the planned command includes the equivalent of:

```text
python -m pip download
  --dest <staging>
  --only-binary=:all:
  --platform win_amd64
  --python-version 3.12
  --implementation cp
  --abi cp312
  <requirements...>
```

The staging directory is not promoted until every produced file is a wheel and the generated wheelhouse manifest verifies.

If a requested dependency has no compatible wheel, the operation fails closed instead of silently falling back to an sdist/build toolchain.

## Offline install contract

`install -Offline`:

1. verifies the selected bundle;
2. checks that its target platform/Python match the selected interpreter;
3. creates a fresh managed `venv` when needed;
4. runs pip using `--no-index --find-links <verified-bundle>`;
5. runs `pip check`;
6. imports every direct profile package as a smoke test;
7. writes a managed-environment marker only after success;
8. updates the activation marker only when the environment covers all activation-required profiles.

An optional-only environment cannot replace the activation environment marker.

## Runtime bootstrap

Canonical `run.py` performs a bounded local dependency preflight before importing the full CLI:

```text
current interpreter ready?
  -> yes: continue
  -> no: verified managed activation environment?
       -> yes: re-exec with its Python
       -> no: verified local core+archive wheelhouse?
            -> yes: offline install -> re-exec
            -> no: activation command is blocked
```

There is deliberately no network branch in this graph.

Diagnostic/operator commands remain available so an operator can inspect and repair dependency state. Runtime activation commands (`start`, `restart`, `chat`, `chat-gpt`, `runtime-bootstrap`) fail closed if `core+archive` cannot be satisfied.

## `activation_ready`

The canonical readiness evaluator now includes required Python dependency readiness. Therefore installation/activation readiness cannot become true merely because source files and package manifests are valid while `py7zr`, `pyzipper` or another base dependency is absent.

Optional dependency profiles continue to report capability-specific absence without blocking ordinary runtime activation.

## Audit semantics

`audit` parses active Python source with the stdlib AST, excludes the standard library and Jaźń-local imports, and compares remaining imports with base/optional dependency declarations and explicit import-name mappings.

It is an evidence aid, not a perfect static dependency theorem: dynamic imports/plugins may require explicit registry mappings. Unmapped external imports are reported rather than guessed.

## Rollback
Wheelhouse bundle directories are content-resolution named and never overwritten. To roll back, point `install -Offline -Bundle <old-bundle>` at a previously verified bundle. A new environment is keyed by the bundle manifest SHA, so rollback does not mutate the old environment in place.

## Relationship to NLP Resource Studio

Dependency Studio owns Python package provisioning. NLP Resource Studio owns language datasets/models/dictionaries and their semantic acceptance.

For example:

```text
Dependency Studio -> install/verify morfeusz2 + stanza Python packages
NLP Resource Studio -> provision/verify SGJP/plWordNet/Stanza model data
```

Neither layer may silently download resources during a conversation turn.
