# Jaźń 16.3.25.5.116.0.34.5 — ChatGPT MCP catalog and host tool exposure parity

## Scope and source evidence (2026-10-16)

Existing `run.py mcp-probe --check-chatgpt-tool-catalog` accepted a catalog
containing the four expected tool names, descriptions and input schemas,
even when they were app-only/hidden from the model, lacked safety annotations,
or advertised no authentication on a public HTTPS bridge. That is a
**catalog false positive**, not proof of any actual host installation failure.
The ChatGPT platform's current-message exposure still requires independent
verification via a real `jazn_status` invocation.

Primary sources:

- https://developers.openai.com/plugins/reference — explicit
  `_meta.ui.visibility`, safety annotations, securitySchemes
- https://developers.openai.com/plugins/build/mcp-server — defined tool
  metadata, operation descriptions, safety and auth enforcement
- https://developers.openai.com/plugins/deploy/connect-chatgpt —
  server tests first, real ChatGPT app/turn acceptance separately
- https://blog.modelcontextprotocol.io/posts/2026-07-28/ — stateless
  MCP transport, traceability and protocol parity
- https://arxiv.org/abs/2609.01660 — long-horizon reliability requires
  end-to-end evaluation; this is supporting motivation, not a bug proof

## Implementation

1. Public FastMCP descriptor declares model+app visibility for the four
   canonical Jaźń turn tools and app-only visibility for health/memory
   diagnostics. This is discoverability metadata, not a permission grant.
2. Read-only MCP catalog probe rejects missing/incorrect `ui.visibility`,
   mismatched read-only/destructive/open-world/idempotence annotations,
   invalid authentication metadata, and `noauth` on public HTTPS.
3. Local, explicit loopback development still permits `noauth`.
   Public runtime still enforces OAuth scopes in its own adapter.
4. Preserve pagination, no redirects, bounded data, no tool execution,
   no secrets in results, no fake current-message capability.
5. Existing active catalog-probe test is preserved byte-for-byte under
   `tests/archive/v16.3.25.5.116.0.34.4/chatgpt_bridge_tool_catalog_probe.py`,
   as required by `AGENTS.codex.md`. New regression cases test hidden
   tools, annotations, HTTPS noauth and localhost noauth.
6. Release identity is bumped to 16.3.25.5.116.0.34.5.

## Acceptance and limitations

- On CI: compileall, Pyright, deterministic pytest including
  `tests/test_chatgpt_bridge_tool_catalog_probe.py`,
  `tests/test_chatgpt_oauth_tool_metadata.py` and
  `tests/test_mcp_http_gateway.py`; run canonical metadata sync.
- On a deployed authenticated MCP: `tools/list`, read-only
  `run.py mcp-probe --check-chatgpt-tool-catalog --json`;
  then test a **current ChatGPT message** with all four tools,
  actual `jazn_status`, two accepted turns and `display_exact`.
- Does not start the user's Windows daemon, configure OAuth,
  make an app callable in this session, bypass pre-spawn ClientError,
  or restore MEMORY. No user data are read or modified.
