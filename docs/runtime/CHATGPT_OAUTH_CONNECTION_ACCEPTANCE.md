# ChatGPT OAuth → Jaźń MCP: connection acceptance v16.3.25.5.116.0.34.25

This extends the *merged* #393 executor change. It does not inject an executor
into ChatGPT or create an authenticated cloud connection automatically.

## Required architecture

ChatGPT (selected custom MCP plugin in a supported conversation)
→ public HTTPS \`/mcp\` (or OpenAI Secure MCP Tunnel)
→ OAuth 2.1 authorization-code + PKCE S256
→ validated scoped access token (issuer, audience, expiry, scopes)
→ existing Python \`PublicMcpGateway\`
→ one persistent Jaźń daemon.

The existing production gateway uses RFC 7662 introspection and keeps MEMORY
separate. The identity provider/authorization server must be deployed and
configured externally; \`deploy/chatgpt_mcp/workers_github_oauth/\` is a
predeployment candidate, not production OAuth readiness. Do not deploy
directly to a live Cloudflare Worker without staging acceptance and rollback.

## Gate A: Safe unauthenticated OAuth preflight

PowerShell:

    py -X utf8 run.py mcp-auth-preflight --endpoint "https://YOUR-HOST/mcp" --json

Unix:

    python3 -X utf8 run.py mcp-auth-preflight --endpoint "https://YOUR-HOST/mcp" --json

The command makes exactly one **unauthenticated** read-only MCP \`tools/list\`
request and retrieves public RFC 9728 resource and RFC 8414 authorization
server metadata. It checks a real HTTP 401 Bearer challenge, same-resource
audience, HTTPS, authorization-code endpoints, PKCE S256 and CIMD/DCR.
It cannot test OAuth login, token introspection, or actual ChatGPT selection.
If using a pre-registered OAuth client without CIMD/DCR, configure it in
ChatGPT before treating connection setup as completed. Reject public no-auth.
Use no production token in command-line arguments.

Run separately:

    py -X utf8 run.py mcp-probe --url "https://YOUR-HOST/mcp" --token-env JAZN_MCP_PROBE_TOKEN --check-chatgpt-tool-catalog --json

The \`mcp-probe\` checks authenticated tools/list and the four canonical
conversation actions; the environment variable must be configured securely
on the operator machine. This is a distinct gate, not a current-turn tool call.

## Gate B: Register and authorize inside ChatGPT

1. In ChatGPT Plugins, choose **Add custom MCP server**.
2. Set HTTPS \`https://YOUR-HOST/mcp\`, choose OAuth and follow the
   account-link flow. Never put a bearer token or client secret in the ZIP.
3. Confirm tool catalog names and operation scopes; use Refresh after
   metadata changes.
4. Install the created plugin, start a **new supported conversation** (the
   official quickstart verifies Work mode), type \`@\` and select Jaźń.
5. Ask for \`jazn_status\` with a newly selected 32-character lowercase
   hexadecimal \`probe_nonce\`. Confirm that the actual ChatGPT tool-call
   transcript contains the invocation and returned \`challenge_nonce_echo\`
   matches *that same turn's* nonce. An echoed nonce is an anti-stale
   diagnostic, not a cryptographic attestation or a substitute for the host
   tool-call event.
6. Verify server-provided version/instance/freshness and all four actions
   callable on the **current** surface. Only then submit the exact user
   message once through \`jazn_generate_visible_reply\`, using a stable
   request_id, and resume the same request if required.
7. Accept only canonical \`jazn_finalize_reply\` confirmation with
   \`action=display_exact\`, correct lineage and final text. Repeat with
   a second distinct message to verify continuity.
8. Recheck from a *fresh* conversation. Plugin installation, /readyz and
   static JSON do not prove subsequent tool callability.

## Gate C: Completion criteria

- Local/remote preflight: discovery PASS does *not* mean ChatGPT ready.
- OAuth: actual user authorization with valid scoped token, not only 401.
- Host: one tool call with a fresh nonce *observed in ChatGPT in that message*.
- Runtime: fresh jazn_status for the canonical daemon/version/instance.
- Turns: two different sequential accepted display_exact finals, stable
  session lineage, no duplicate submit.
- Optional MEMORY: separately attached and validated, never implied by core.

Stop with an explicit blocking reason if any gate is absent. Do not claim
ChatGPT ordinary-chat auto-routing or a "Jaźń" response without accepted
host finalization.

## Primary sources (2026-10-20)

- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://developers.openai.com/plugins/build/auth
- https://developers.openai.com/plugins/build/plugins
- https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- https://www.rfc-editor.org/rfc/rfc9728.html
- https://www.rfc-editor.org/rfc/rfc8414.html
