# Jaźń Dependency Studio — versioned offline wheelhouse

## Status

`16.3.25.5-package-distribution-convergence` promotes Dependency Studio to the release dependency contract. It keeps the operator-owned offline layer, but the release now transports target-specific verified dependency artifacts instead of assuming a pre-existing local wheelhouse.

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
│  │  ├─ JAZN_WHEELHOUSE_MANIFEST.json
│  │  └─ JAZN_WHEELHOUSE_REQUIREMENTS.txt
│  └─ ...
├─ environments/
│  └─ <platform>__py<major-minor>__<manifest-sha>/
└─ JAZN_DEPENDENCY_ENVIRONMENT.json
```

`latka_jazn/local_resources/` remains excluded from Git. Releases transport wheelhouse bundles as immutable dependency sidecar ZIPs described by `JAZN_DEPENDENCY_SET.json`; ready-made `venv`/`site-packages` trees remain non-transportable runtime state.

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

Verify manifest v2, SHA-256, ZIP CRC, filename/metadata Name+Version, `METADATA`, `WHEEL`, complete `RECORD` hashes/sizes, `Requires-Python`, compatibility tags, duplicates/unlisted wheels and license metadata:

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
4. verifies `JAZN_WHEELHOUSE_REQUIREMENTS.txt` and runs pip with `--no-index --only-binary=:all: --require-hashes --find-links <verified-bundle> -r JAZN_WHEELHOUSE_REQUIREMENTS.txt`;
5. runs `pip check`;
6. imports every direct profile package as a smoke test;
7. records `pip inspect --local` and requires installed distribution inventory to match the resolved manifest;
8. writes a managed-environment v2 marker only after success;
9. updates the activation marker only when the environment covers all activation-required profiles.

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


## Contract v2 and release artifacts

`jazn_dependency_wheelhouse/v2` uses PyPA `packaging` after dependency handoff for PEP 440 requirements, wheel filename parsing and compatibility tags. The pre-handoff bootstrap remains stdlib-only, so an ambient interpreter does not need `packaging` merely to discover a managed environment or a transported sidecar.

Each release dependency artifact contains one verified wheelhouse for exactly one target. A target records friendly alias plus Python version, implementation, ABI, platform family, architecture, libc family and the compatible tag set. `.25.5` release support is Windows x86-64 and Linux glibc x86-64 for Python 3.12, 3.13 and 3.14. Linux musl and ARM targets are represented by the API/schema but are not release-supported until native clean-room acceptance exists.

The system package carries `JAZN_DEPENDENCY_SET.json`; dependency artifacts remain sibling files. Discovery verifies package-set metadata and outer SHA before extracting a sidecar, then verifies the inner wheelhouse and hash lock. A wrong Python/platform/libc bundle is rejected before pip is invoked.

## Managed Environment Contract v2

The managed marker separates `created_for_runtime_version` from `dependency_contract_fingerprint`. A runtime-only version bump does not invalidate an otherwise compatible environment. Changes to dependency declarations/profile registry, target or verified wheelhouse do invalidate it. Cleanup is explicit only:

```text
python -X utf8 -m latka_jazn.tools.dependency_studio gc --dry-run
python -X utf8 -m latka_jazn.tools.dependency_studio gc --apply
```

Bootstrap never performs garbage collection automatically.

## Release locks

Release CI builds wheelhouses on native runners and emits exact target locks under `latka_jazn/resources/dependencies/locks/core+archive/`. Every line is fully pinned and SHA-256 locked, including transitive dependencies. The first native matrix run materializes release evidence for all six required targets and persists those exact locks on the release branch. Subsequent matrix runs consume the persisted lock through `dependency-studio download --lock-file ...`, so `pip download` itself runs with `--require-hashes --only-binary=:all:` and the regenerated bundle lock must be byte-identical to the committed target lock.

A release is not considered converged merely because the bootstrap resolution succeeded once: the canonical-lock consumer run must also pass on Windows x64 and Linux glibc x64 for Python 3.12, 3.13 and 3.14. The locks are therefore generated from native wheelhouse resolution rather than handwritten or inferred across platforms. `pylock.<target>.toml` may be emitted later as an additional audit/export format, but it is not a bootstrap dependency in `.25.5`.
