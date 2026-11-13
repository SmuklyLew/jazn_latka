# V127.4 SQLite test baseline — immutable archive

- Original path: `tests/test_shard_manifest_fail_closed.py`
- Source branch: `fix/v127-4-ci-isolation-recovery-20261111`
- Source commit: `6cb9d6a7e8f62c1cbb0f0b0b5be4edbeb8e82af5`
- Original Git blob SHA: `8e93198d712d5d7821693e5fe730e3785b8ac897`
- Reason: explicitly distinguish prepared ROOT-local SQLite workspace from historical bare ROOT sibling workspace, without changing the production resolver.

The archived test is preserved byte-for-byte as the active test before the change.
