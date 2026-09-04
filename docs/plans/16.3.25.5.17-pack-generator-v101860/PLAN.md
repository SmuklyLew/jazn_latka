# Jaźń 16.3.25.5.17 / Pack Generator 10.1.86.0

## Objective

Replace the accumulated versioned generator modules with one deterministic,
self-contained public launcher and a small version-neutral source set. Preserve
the canonical Jaźń package-distribution boundary, make dependency
materialization target-aware and reproducible, and prove the same native lock
can be replayed on the opposite operating system.

## Release identities

- generator: `10.1.86.0`;
- Jaźń package: `16.3.25.5.17`;
- release name: `pack-generator-cross-target-dependency-materialization`;
- Wheelhouse Contract: `jazn_dependency_wheelhouse/v3`;
- dependency artifact: `jazn_dependency_artifact/v2`.

## Design decisions

1. The public `tools/jazn_pack_generator.py` embeds only generator modules as
   deterministic zlib/Base85 payloads and imports them as private in-memory
   modules. This recovers the useful portability property of v8.6.
2. Runtime/system code is never embedded. The launcher resolves an explicit or
   adjacent-settings Jaźń source root and imports the current canonical system
   contracts from it.
3. Mutable dependency data defaults to the host workspace returned by
   `workspace_runtime_path(root)`, never to a tracked or versioned code path.
4. Native resolution may create a lock. A foreign target may only replay an
   existing fully pinned SHA-256 lock; it never resolves a dependency graph.
5. Locked replay invokes `pip download` with `--require-hashes`, `--no-deps`,
   `--only-binary=:all:` and all target selectors. The produced lock must be
   byte-identical to its input lock.
6. The supported Linux x64 release policy is glibc 2.17 or newer, represented by
   `manylinux_2_17_x86_64` plus its legacy equivalent
   `manylinux2014_x86_64`. Musl/ARM/macOS remain fail-closed without a separately
   accepted policy and native clean-room evidence.
7. All six release locks are authored by native GitHub runners. Windows replays
   Linux locks and Ubuntu replays Windows locks before CI may persist them.
8. `PACKAGE_INTEGRITY_MANIFEST.json` and `SOURCE_PROVENANCE.json` are generated
   only by `latka_jazn.tools.release_metadata_sync`.

## Verification plan

- deterministic builder write + independent `--check`;
- focused generator, dependency, sidecar and package-contract tests;
- compile all active Python;
- Pyright gates used by release CI;
- complete non-live pytest suite;
- `doctor`, `package-smoke` and relevant package generation checks;
- canonical metadata `--write`, then independent `--check`;
- clean committed tree and pushed branch;
- native six-target build, opposite-OS replay, clean-room consumption and
  persisted-lock readback in GitHub Actions;
- pull request to `master`, with no merge performed.

## Authoritative references

- pip download target controls:
  <https://pip.pypa.io/en/stable/cli/pip_download/>;
- pip secure/repeatable installation and hash rules:
  <https://pip.pypa.io/en/stable/topics/secure-installs/>;
- PyPA platform compatibility tags and manylinux policy:
  <https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/>;
- GitHub Actions workflow artifacts:
  <https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts>;
- Python `zipfile` behavior used by the deterministic launcher/package layer:
  <https://docs.python.org/3/library/zipfile.html>.

The pip target-selector limitation for environment-marker evaluation is also
tracked upstream at <https://github.com/pypa/pip/issues/13442>. This design does
not treat foreign `pip` resolution as authoritative: native CI creates the
resolved lock, and foreign hosts perform only hash-locked, no-dependency replay.
