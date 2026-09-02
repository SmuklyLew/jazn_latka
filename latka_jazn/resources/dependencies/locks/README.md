# Release dependency locks

Canonical release locks are generated on native GitHub Actions runners from a verified
`jazn_dependency_wheelhouse/v2` bundle. They are target-specific because wheel tags,
Python ABI and Linux libc compatibility are part of the contract.

Required `.25.5` targets:

- `core+archive/windows-x64-py312.txt`
- `core+archive/windows-x64-py313.txt`
- `core+archive/windows-x64-py314.txt`
- `core+archive/linux-x64-py312.txt`
- `core+archive/linux-x64-py313.txt`
- `core+archive/linux-x64-py314.txt`

Do not hand-author hashes. The `dependency-artifacts` workflow materializes the native
wheelhouse, verifies it, and publishes the exact `JAZN_WHEELHOUSE_REQUIREMENTS.txt` as
release evidence. Once native jobs pass, those exact outputs become the release locks.
Runtime bootstrap does not depend on experimental `pylock.toml` support.
