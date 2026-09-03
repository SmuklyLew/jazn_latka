# Jaźń 16.3.25.5 — Package Distribution Convergence

## Scope

`16.3.25.5-package-distribution-convergence` makes Python dependency transport part of
the release contract. It preserves Memory Rebuild v4 and the `.25.4` generator import
isolation fix. The release does not change private-memory acceptance semantics or
cognitive integration readiness.

## Dependency Contract v2

The project declares `packaging>=24.2,<27` in addition to the existing runtime
dependencies. Bootstrap modules used before managed-environment handoff remain stdlib
only. Full requirement/version/tag validation is lazy and uses PyPA `packaging` only
when it is available in Dependency Studio or the managed environment.

`TargetSpec` separates a friendly alias from the actual wheel contract: Python version,
implementation, ABI, platform family, architecture, libc family and compatibility tags.
The release-supported matrix is Windows x86-64 and Linux glibc x86-64 on Python
3.12/3.13/3.14. Linux musl and ARM are fail-closed until native acceptance exists.

## Wheelhouse Contract v2

`jazn_dependency_wheelhouse/v2` records dependency-contract fingerprint, direct
requirements, resolved distributions, target, compatibility tags, pip/packaging
versions and per-wheel SHA-256/size/metadata. Verification checks ZIP CRC, `METADATA`,
`WHEEL`, complete `RECORD` hashes and sizes, filename versus metadata Name/Version,
`Requires-Python`, target tags, duplicates/unlisted wheels and license metadata.

Each verified bundle contains `JAZN_WHEELHOUSE_REQUIREMENTS.txt` with exact pins and
SHA-256 hashes for all resolved distributions. Offline install is performed with:

```text
python -m pip install --no-index --only-binary=:all: --require-hashes \
  --find-links <verified_bundle> -r JAZN_WHEELHOUSE_REQUIREMENTS.txt
```

`pip check`, direct import smoke and `pip inspect --local` are post-install gates.

## Release artifact contract

`jazn_package_set/v3` has three semantic roles: `system`, `memory`, `dependencies`.
A system ZIP contains `JAZN_DEPENDENCY_SET.json` describing sibling dependency
artifacts and their SHA-256. A dependency sidecar is target-specific and contains one
verified wheelhouse, lock and `JAZN_DEPENDENCY_ARTIFACT.json` descriptor.

Sidecar selection is never filename-only. Bootstrap verifies the dependency-set entry,
outer SHA, descriptor, target, inner wheelhouse manifest and hash lock before install.
Missing or incompatible artifacts fail with `no_compatible_verified_dependency_bundle`;
there is no network-pip fallback.

Supported package planning modes are `system-thin`, `system-portable(target)`,
`memory-only`, `dependencies-only(target)`, `system+memory`, and
`system+memory+dependencies(target)`.

## Managed Environment Contract v2

The marker separates `created_for_runtime_version` from
`dependency_contract_fingerprint`. A pure Jaźń version bump can reuse the environment
when target, profile coverage, dependency fingerprint, wheelhouse manifest and import
smoke remain valid. Dependency/profile/target/wheelhouse changes still require
reinstallation. Cleanup is explicit via Dependency Studio `gc`; bootstrap never runs GC.

## Platform-safe process handoff

`latka_jazn.dependencies.process_handoff` is the single handoff helper. POSIX uses real
`execve`. Windows starts a child process, inherits stdio and propagates exit code. For a
managed venv it follows CPython's redirector-safe pattern by using
`sys._base_executable` and `__PYVENV_LAUNCHER__`.

## Daemon instance identity

Each start generates `daemon_instance_id` and passes it to the daemon. The ID is
published in marker, `/live` and `/ready`. New endpoints are identified by instance ID
plus active root; PID remains secondary evidence. Legacy endpoints without instance IDs
retain PID+root behavior. This removes false Windows redirector failures without making
PID mismatches universally acceptable. Repeated start of the verified active instance
returns `already_running=true`.

## Archive resource policy

ZIP, AES ZIP and 7z share path/resource checks for normalized paths, traversal,
absolute paths, Windows ADS/reserved names, casefold collisions, symlinks/special
files, member count, single/total expanded size and compression ratio. The existing
archive service additionally checks free disk space, extracts to sibling staging and
commits destinations atomically. Binary `.001/.002/...` split/join remains a transport
contract and is not treated as native multipart ZIP/7z semantics.

## Memory Rebuild v4 boundary

Memory Rebuild v4 protocol semantics remain unchanged: Test00→Final,
RAW→SEMANTIC→MEMORY, explicit lossy HTML boundaries, write-once final sealing and no
automatic L2/L3 promotion. Package compatibility readers accept package-set v3 only for
transport/integrity; memory application behavior is not rebuilt by this release.

## Generator 8.8

Generator 8.8 exposes target-aware distribution modes while preserving `.25.4` import
isolation. Its canonical source is under `tools/pack_generator_sources/`; the public
`tools/jazn_pack_generator.py` is deterministically generated. CI checks bundle
freshness so regeneration must leave no diff.

## Release CI v2

Native dependency jobs cover the six required OS/Python combinations. They build and
verify wheelhouses, perform hash-locked offline install, `pip check`, generate audit
reports/SBOM, package target sidecars, record Jaźń SHA and GitHub artifact digest, and
attest release artifacts.

`package-distribution-cleanroom` separates producer and consumer jobs. The consumer has
no source checkout: it downloads only built artifacts, extracts the system ZIP, starts
from an ambient Python without `py7zr/pyzipper`, discovers the sibling sidecar, creates
the managed environment offline, performs handoff, doctor/start/status/stop, and also
verifies the controlled failure when the sidecar is absent.

Dependency Review and `pip-audit` are CI/development gates; neither is a runtime
dependency.

## Integrity layers

Release evidence deliberately has independent layers:

1. `PACKAGE_INTEGRITY_MANIFEST.json` — Jaźń file integrity.
2. `SOURCE_PROVENANCE.json` — Jaźń source provenance.
3. Dependency-sidecar SHA + wheelhouse v2 + hash lock.
4. GitHub artifact digest.
5. GitHub Artifact Attestation.

Canonical package integrity and source provenance are regenerated only from the final
combined tree by the release metadata sync. They are never manually merged.

## Fail-closed boundary

The system must stop explicitly on missing compatible bundle, wrong outer/inner hash,
wrong target/libc/Python, invalid RECORD/tag/Requires-Python, dependency inventory
mismatch, or daemon instance mismatch. It must not silently use network pip and must not
claim a live trusted runtime without the required identity/integrity evidence.

## Canonical native release locks

The required Windows x64 and Linux glibc x64 Python 3.12/3.13/3.14 locks are produced only by their native GitHub runners. The first release-branch matrix materializes exact wheelhouse locks as evidence and persists all six lock files. The next validation run consumes those files as hash-locked `pip download` input and requires the resulting wheelhouse lock to match byte-for-byte. This two-pass gate prevents loose requirements from silently resolving to a different release set while avoiding fabricated cross-platform hashes.
