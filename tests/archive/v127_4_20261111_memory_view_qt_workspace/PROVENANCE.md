# V127.4 Qt Memory Studio workspace isolation regression baseline

- Active source: `tests/test_jazn_run_studio_memory_view.py`
- Source branch: `fix/v127-4-root-venv-single-interpreter-20261111`
- Original source HEAD: `d0392049de28a6817334439803bc34b27b271024`
- Original Git blob SHA: `832845317fa00936c3a14567535bbefdf37047cb`
- Snapshot: `test_jazn_run_studio_memory_view.py`
- Root cause: a real verified project ROOT was paired with an external `JAZN_RUNTIME_WORKSPACE_DIR` that modern prepared SYSTEMs deliberately reject.
- Scope: test-only correction. Preserve the production fail-closed workspace resolver, private MEMORY boundary, daemon state, and operator path policy.

The archived Python source is a byte-for-byte copy of the original test.
