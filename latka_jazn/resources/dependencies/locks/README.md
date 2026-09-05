# Release dependency locks

Canonical release locks are generated on native GitHub Actions runners from a verified
`jazn_dependency_wheelhouse/v3` bundle. They are target-specific because wheel tags,
Python ABI and Linux libc compatibility are part of the contract. Linux x64 uses the
glibc 2.17 baseline represented by `manylinux_2_17_x86_64` and its legacy equivalent
`manylinux2014_x86_64`.

Required `.25.5` targets:

- `core+archive/windows-x64-py312.txt`
- `core+archive/windows-x64-py313.txt`
- `core+archive/windows-x64-py314.txt`
- `core+archive/linux-x64-py312.txt`
- `core+archive/linux-x64-py313.txt`
- `core+archive/linux-x64-py314.txt`

Do not hand-author hashes. The `dependency-artifacts` workflow materializes the native
wheelhouse, verifies it, and publishes the exact `JAZN_WHEELHOUSE_REQUIREMENTS.txt` as
release evidence. The clean-room workflow then replays each Linux lock on Windows and
each Windows lock on Ubuntu with hashes, no dependency resolution and wheel-only target
selectors. Locks are persisted only after the replayed lock and wheel inventory match
the native artifact exactly. Runtime bootstrap does not depend on experimental
`pylock.toml` support.
