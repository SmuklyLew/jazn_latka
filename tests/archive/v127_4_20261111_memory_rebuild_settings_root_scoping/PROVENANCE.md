# V127.4 Memory Rebuild settings path regression baseline

- Original active path: `tests/test_memory_rebuild_settings_persistence.py`
- Source branch: `fix/v127-4-root-venv-single-interpreter-20261111`
- Source HEAD: `0793cda2b70a255dd598021c2f8ac6dcf2ce4445`
- Original Git blob SHA: `763e499aca6db2dcf5e045b2aec54c528ea9f952`
- Verbatim archived source: `test_memory_rebuild_settings_persistence.py`
- Reason: an unrecognized synthetic `tool_root` fell back to the prepared code checkout, then supplied an external workspace override forbidden by the current path policy.
- Scope: tests only. Preserve strict prepared-root containment, operator-path protections, private MEMORY and daemon state.

No production files or user MEMORY are included in the snapshot.
