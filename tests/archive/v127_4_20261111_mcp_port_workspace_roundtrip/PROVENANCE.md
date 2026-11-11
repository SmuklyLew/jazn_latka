# V127.4 MCP gateway port settings roundtrip test baseline

- Source branch: `fix/v127-4-root-venv-single-interpreter-20261111`
- Source HEAD: `a655eaa255fab8f8ee8bf2cd564a4605bf5d8bad`
- Original active path: `tests/test_jazn_run_studio_mcp_events.py`
- Original Git blob SHA: `75415782b4a242247dcdb5e8642553e96859a442`
- Source snapshot: `test_jazn_run_studio_mcp_events.py`
- Change scope: test-only; replace a hard-coded historical `workspace_runtime` directory assertion with checks of the canonical resolved settings path and persisted MCP port.
- Isolation requirement: never create or adopt a legacy sibling workspace, live daemon, or MEMORY during the test.

The archived Python file is a verbatim copy of the pre-change version.
