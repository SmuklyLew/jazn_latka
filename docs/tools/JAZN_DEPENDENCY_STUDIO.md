# Jaźń Dependency Studio — versioned offline wheelhouse

## Status

The Pack Generator 10.1.86.0 release promotes Dependency Studio to Wheelhouse Contract v3. It keeps the operator-owned offline layer, but the release transports target-specific verified dependency artifacts and permits a foreign supported target only as an exact replay of a native, SHA-256-locked resolution.

The Studio is not a second package manager. It orchestrates standard Python `venv` and `pip` commands with Jaźń-specific profiles, manifests, SHA-256 verification and activation gates.

## Core invariants

1. The repository never copies or commits a ready-made `site-packages` tree.
2. Managed virtual environments are disposable and recreated locally.
3. Binary wheels live under the ignored local resource root or another explicit wheelhouse path; source Git keeps the tool, profile registry and contracts.
4. `download` is an explicit operator/network action.
5. Runtime autobootstrap never downloads from the network. It may only reuse a verified managed environment or install from a verified local wheelhouse.
6. A wheelhouse bundle is immutable. `update` creates a new resolution when bytes/versions change and keeps the previous bundle available for rollback.
7. `core` is activation-required. `archive` is runtime-optional but remains in the explicit release profile `core+archive`; other optional profiles do not silently become required.
8. `activation_ready=True` requires the activation dependency profiles to be satisfied by the current interpreter or a verified managed environment.
9. SHA-256 and recorded package metadata prove local byte identity relative to the manifest; they do not certify upstream package safety or legal compatibility.

## Canonical local paths

Default root (outside the active/versioned source tree):

```text
<host workspace_runtime>/local_resources/python/
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

The root is resolved by `workspace_runtime_path(<jazn_root>)`; it is shared host state, not versioned source. The historical `<jazn_root>/latka_jazn/local_resources/` location is not the default. Releases transport wheelhouse bundles as immutable dependency sidecar ZIPs described by `JAZN_DEPENDENCY_SET.json`; ready-made `venv`/`site-packages` trees remain non-transportable runtime state.

Set `JAZN_DEPENDENCY_WHEELHOUSE` to an explicit external wheelhouse when the bundle should live outside the runtime root.

## Profiles

The canonical registry is:

```text
latka_jazn/resources/dependencies/profiles.json
```

Current profiles:

| Profile | Role | Source |
|---|---|---|
| `core` | runtime required | base `project.dependencies` |
| `archive` | runtime optional / release sidecar | `py7zr`, `pyzipper`, `rarfile` |
| `studio` | operator optional | `memory-rebuild-ui` optional dependencies |
| `memory-cloud` | runtime optional | matching `pyproject.toml` optional group |
| `memory-cloud-server` | service optional | matching optional group |
| `polish-nlp` | heavy optional | Morfeusz/Stanza/spaCy/transformer NLP dependency group |
| `all` | aggregate | all profiles above |

The archive profile is an optional capability containing `py7zr`, `pyzipper` and `rarfile`. Baseline ZIP remains stdlib-only; enhanced 7z/AES ZIP/RAR readiness is reported separately and does not block core activation.

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

Verify manifest v3, SHA-256, ZIP CRC, filename/metadata Name+Version, `METADATA`, `WHEEL`, complete `RECORD` hashes/sizes, `Requires-Python`, compatibility tags, duplicates/unlisted wheels and license metadata:

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

Native resolution and cross-target materialization are deliberately different operations. A foreign Windows/Linux target requires the corresponding canonical release lock and uses the equivalent of:

```text
python -m pip download
  --dest <staging>
  --only-binary=:all:
  --require-hashes
  --no-deps
  --platform <every accepted target platform tag>
  --python-version <minor>
  --implementation cp
  --abi <cp ABI>
  -r <canonical native lock>
```

The output inventory must reproduce that lock byte for byte. Without the lock the operation fails before creating a wheelhouse. This avoids treating pip's foreign target switches as a complete replacement for native dependency resolution, particularly for environment markers.

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
current interpreter satisfies activation-required core?
  -> yes: continue
  -> no: verified managed activation environment?
       -> yes: re-exec with its Python
       -> no: verified local core wheelhouse?
            -> yes: offline install -> re-exec
            -> no: activation command is blocked
```

There is deliberately no network branch in this graph.

Diagnostic/operator commands remain available so an operator can inspect and repair dependency state. Runtime activation commands (`start`, `restart`, `chat`, `chat-gpt`, `runtime-bootstrap`) fail closed if `core` cannot be satisfied.

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


## Contract v3 and release artifacts

`jazn_dependency_wheelhouse/v3` adds explicit materialization mode, minimum libc policy and the complete pip-platform selector set to the v2 integrity inventory. It uses PyPA `packaging` after dependency handoff for PEP 440 requirements, wheel filename parsing and compatibility tags. The pre-handoff bootstrap remains stdlib-only, so an ambient interpreter does not need `packaging` merely to discover a managed environment or a transported sidecar.

Each release dependency artifact contains one verified wheelhouse for exactly one target. A target records friendly alias plus Python version, implementation, ABI, platform family, architecture, libc family, minimum libc version, accepted pip platforms and the compatible tag set. `.25.5.17` release support is Windows x86-64 and Linux glibc x86-64 for Python 3.12, 3.13 and 3.14. Linux x64 uses the glibc 2.17 baseline (`manylinux_2_17_x86_64` / `manylinux2014_x86_64`). Linux musl, ARM and macOS cross-targets are not release-supported until a policy and native clean-room acceptance exist.

The system package carries `JAZN_DEPENDENCY_SET.json`; dependency artifacts remain sibling files. Discovery verifies package-set metadata and outer SHA before extracting a sidecar, then verifies the inner wheelhouse and hash lock. A wrong Python/platform/libc bundle is rejected before pip is invoked.

## Managed Environment Contract v2

The managed marker separates `created_for_runtime_version` from `dependency_contract_fingerprint`. A runtime-only version bump does not invalidate an otherwise compatible environment. Changes to dependency declarations/profile registry, target or verified wheelhouse do invalidate it. Cleanup is explicit only:

```text
python -X utf8 -m latka_jazn.tools.dependency_studio gc --dry-run
python -X utf8 -m latka_jazn.tools.dependency_studio gc --apply
```

Bootstrap never performs garbage collection automatically.

## Release locks

Release CI builds wheelhouses on native runners and emits exact target locks under `latka_jazn/resources/dependencies/locks/core+archive/`. Every line is fully pinned and SHA-256 locked, including transitive dependencies. The first native matrix run materializes release evidence for all six required targets. Before persistence, Windows runners replay the three Linux locks and Ubuntu runners replay the three Windows locks with `--require-hashes --no-deps --only-binary=:all:`. The replayed lock and full resolved filename/SHA-256 inventory must match native evidence exactly. Subsequent native runs consume the persisted lock through `dependency-studio download --lock-file ...`.

A release is not considered converged merely because bootstrap resolution succeeded once: native locked consumers, opposite-OS replay and clean-room package consumers must pass for Windows x64 and Linux glibc x64 on Python 3.12, 3.13 and 3.14. Locks are generated from native wheelhouse resolution rather than handwritten or inferred across platforms. `pylock.<target>.toml` may be emitted later as an additional audit/export format, but it is not a bootstrap dependency in `.25.5.17`.


## v16.3.25.5.34 capability split

`activation_profiles=["core"]` controls runtime bootstrap. `release_profiles=["core","archive"]` preserves the existing target-specific release sidecar contract while allowing ordinary Jaźń core activation without optional archive backends. A real `install` always creates a fresh path-stable venv and atomically switches only the activation marker after verification; existing environments are never mutated in place.
