# Jaźń Pack Generator 8.9 — cross-platform Studio and portable dependency contract

## Scope

Generator 8.9 is the operator-facing convergence layer for package generation after
`16.3.25.5-package-distribution-convergence`. It keeps the legacy 8.8 implementation
available for compatibility, but portable release packaging is routed through the
canonical `latka_jazn.tools.package_distribution` contract and must produce
`jazn_package_set/v3`.

## UI modes

The settings contract exposes five explicit UI choices:

- `tekstowy`;
- `kursorowy`;
- `studio-terminal` — Studio in a terminal;
- `studio-windows` — desktop Studio guarded to Windows;
- `studio-linux` — desktop Studio guarded to Linux.

Studio packaging uses distribution modes (`system-thin`, `system-portable`,
`memory-only`, `dependencies-only`, `system+memory`,
`system+memory+dependencies`) rather than treating the old `profile=system` ZIP as a
portable release artifact.

## Managed Python dependency state is never system payload

`latka_jazn/local_resources/python/**` is host- and target-specific Dependency Studio
state. Generator 8.9 hard-excludes this tree from the legacy Generator 8.8 filesystem plan.
The canonical repository path is already ignored by Git, while v3 system packaging is
built from canonical release metadata rather than from the operator's local dependency
cache. This prevents local environments or wheelhouse caches from entering a system ZIP
and prevents third-party files from becoming package-integrity inputs.

## Target resolution

`target=current` is resolved before bundle discovery and package construction to the
actual release alias (`windows-x64` or `linux-x64`). Python patch versions are reduced
to the ABI minor, so CPython `3.13.5` selects the `3.13` / `cp313` dependency contract.
A cross-target dependency bundle is never materialized on the wrong OS; it must be
provided as a verified native bundle.

## Linux x86_64 / CPython 3.13 release evidence

The canonical lock
`latka_jazn/resources/dependencies/locks/core+archive/linux-x64-py313.txt` is copied
byte-for-byte from the successful PR #209 native artifact
`jazn-package-linux-x64-py3.13` (workflow run `33780484121`). The lock SHA-256 is:

`81afe3398aba06931c9d7cbc5672eb14d00a11e5c9b6ede1239ccf56e226e0f6`

The artifact describes target `linux-x64`, architecture `x86_64`, implementation
`cp`, ABI `cp313`, libc family `glibc`, and contains the verified `core+archive`
requirements including `py7zr==1.1.3` and `pyzipper==0.4.0`.

Generator-native materialization automatically supplies this canonical lock to
Dependency Studio when it exists. It does not hand-author dependency hashes and it
does not embed a local environment into the system ZIP. The resulting portable set
contains the system ZIP plus a separately verified dependency ZIP referenced by
`JAZN_DEPENDENCY_SET.json`.
