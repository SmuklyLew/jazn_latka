# P0 fix: MCP probe protocol-era safety — v16.3.25.5.115.20.2

Stacked parent: upgrade/v16.3.25.5.115.20-studios-mcp-ingress-convergence
Patch branch: fix/v16.3.25.5.115.20.2-mcp-probe-p0

## Verified defect and narrow scope

The previous diagnostic labeled an MCP initialize handshake as protocol 2026-07-28. That revision removed initialize in favor of server/discover with per-request _meta and headers. Also, urllib.request.urlopen followed HTTP redirects, potentially sending a preflight POST to an unvalidated destination.

## Fix

- Probe modern 2026-07-28 first: server/discover, body _meta with protocolVersion, clientInfo and clientCapabilities, and matching MCP-Protocol-Version and Mcp-Method HTTP headers.
- A valid discovery result needs resultType=complete, capabilities object and supportedVersions containing 2026-07-28. HTTP 200 alone never proves readiness.
- Permit one read-only legacy initialize probe (2025-11-25) to the exact same endpoint only after an unrecognized modern HTTP 4xx. Never downgrade on 401/403/429, redirects or recognized modern JSON-RPC errors.
- Explicitly disable automatic redirects for all diagnostic HTTP requests (including same-host and POST-preserving 307/308).
- Preserve existing CLI (run.py mcp-probe) and diagnostic truth boundary. Neither this probe nor a legacy initialize response proves tools/list, tool exposure in ChatGPT, OAuth validity, MessageEnvelope or accepted visible turns.
- Retain original versions of the six edited active test files in tests/archive/v16.3.25.5.115.20.1-pre-mcp-probe-p0/ (byte-identical Git blobs).

## Official protocol references

- https://modelcontextprotocol.io/specification/2026-07-28/server/discover
- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
- https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/protocol-versions.md

## Release gates

- python -X utf8 -m pytest -q tests/test_mcp_ingress_diagnostics.py
- python -X utf8 tools/jazn_tests_studio/sync_contract_catalog.py --check
- python -X utf8 -m compileall -q latka_jazn tests main.py run.py
- python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
- Pyright, doctor, package-smoke and GitHub Actions Windows/Linux regression gates.
- Canonical tools/workflow must regenerate test_contracts.json and package/provenance metadata after code commit; do not author generated hashes manually.

P0 integration and deployment to ChatGPT are separate acceptance dimensions. This patch does not enable or deploy a real public OAuth MCP server, modify runtime daemon jobs, change MEMORY/SQLite, or implement Studio P1–P3. Do not merge the patch while required checks remain unverified.
