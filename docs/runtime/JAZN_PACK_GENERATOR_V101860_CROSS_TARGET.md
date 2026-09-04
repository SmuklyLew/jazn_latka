# Jaźń Pack Generator 10.1.86.0 — deterministic target-aware distribution

Pack Generator 10.1.86.0 is a generated, self-contained Python launcher. Its
maintained sources have version-neutral names under
`tools/pack_generator_sources/`; the builder compresses and Base85-encodes them
into `tools/jazn_pack_generator.py`, then `--check` proves that the committed
launcher matches those sources byte for byte.

The bundle contains generator code only. It selects a Jaźń source root from
`JAZN_SOURCE_ROOT`, an adjacent settings file, an enclosing repository, the
current directory or documented local defaults. Runtime and package behavior is
then imported from that selected system tree. Copying the launcher plus an
adjacent `jazn_pack_generator_settings.json` therefore preserves the useful
two-file portability of v8.6 without freezing duplicate system modules inside
the generator.

## Dependency selection

The generator searches only the canonical host workspace wheelhouse:

```text
<host workspace_runtime>/local_resources/python/wheelhouse/
```

`JAZN_DEPENDENCY_WHEELHOUSE` remains an explicit override. The generator never
uses `latka_jazn/local_resources` in the source repository as its default and
never includes managed environments or mutable `site-packages` trees.

Materialization has three explicit modes:

| Mode | Target | Input lock | Meaning |
|---|---|---|---|
| `native-resolve` | current OS/architecture/Python | absent | resolve on the authoritative native host and emit a lock |
| `native-locked` | current OS/architecture/Python | present | replay the canonical release lock natively |
| `cross-target-locked` | foreign supported target | required | download exact locked wheels; dependency resolution is forbidden |

A foreign target without a regular canonical lock fails before the wheelhouse
is created. Locked downloads use `--require-hashes --no-deps
--only-binary=:all:` and explicit platform, Python, implementation and ABI
selectors. The resolved wheel inventory must regenerate the input lock exactly.

## Supported release matrix

- Windows x86-64, CPython 3.12, 3.13 and 3.14: `win_amd64`;
- Linux glibc x86-64, CPython 3.12, 3.13 and 3.14:
  `manylinux_2_17_x86_64` / `manylinux2014_x86_64`.

The Linux descriptor records `libc_family=glibc` and
`minimum_libc_version=2.17`. The two platform names are equivalent policy names
defined by the Python packaging compatibility-tag specification. Unsupported
musl, ARM and macOS cross-target requests fail closed until their own policy and
native CI matrix are accepted.

## CI proof

For every target/Python pair, a native runner builds and verifies the wheelhouse,
offline installation, dependency audit and portable package set. A runner on the
opposite operating system then downloads that native artifact, replays its exact
lock for the foreign target, verifies the new bundle, compares the lock byte for
byte and compares the full name/version/filename/SHA-256 distribution inventory
with the native sidecar manifest. Only after all replays pass may CI persist the
six release locks and synchronize canonical release metadata.

This separates two claims that must not be conflated: native resolution decides
the dependency graph, while cross-target replay proves transportability of that
already-authorized graph.
