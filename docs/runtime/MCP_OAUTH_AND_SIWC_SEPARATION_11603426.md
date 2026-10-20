# Jaźń v16.3.25.5.116.0.34.26 — OAuth MCP ≠ Sign in with ChatGPT

**Status:** code-only readiness hardening. The production Cloudflare OAuth server, protected MCP route, SIWC user-login manager and real ChatGPT tool exposure are NOT demonstrated as active. No production secrets or personal MEMORY are included.

## Evidence and canonical hostnames

On 2026-10-21, the connected Cloudflare API reported account Workers subdomain \`jazn-lakta\`, \`jazn-auth\` deployment version \`cd8ce770\` (100%) and \`jazn-runtime\` version \`7ec76752\` (100%). The auth Worker bindings were \`GITHUB_CLIENT_ID\` (plain_text), \`GITHUB_CLIENT_SECRET\` (secret_text), and \`OAUTH_KV\` (kv_namespace); missing were both \`JAZN_INTROSPECTION_CLIENT_*\` credentials and the two GitHub identity allowlist bindings. The runtime Worker exposed \`JAZN_PRIVATE_MCP\` (vpc_service), but not the three \`JAZN_*INGRESS/OAUTH*\` opt-in variables. These are **binding-name observations**, not credential values or proof of live HTTP behavior.

Canonical MCP issuer: \`https://jazn-auth.jazn-lakta.workers.dev\`
Canonical resource: \`https://jazn-runtime.jazn-lakta.workers.dev/mcp\`

Do not silently change \`lakta\` to \`latka\` or mix them. A GitHub login/allowlist is an upstream identity check, not the OpenAI client's OAuth identity. A 503 fail-closed response is not a code proof of a broken archive.

## Three separate permissions

- MCP OAuth: the Cloudflare \`jazn-auth\` authorization server issues scoped MCP resource tokens, introspected by Python at the resource server on every privileged request. Login to GitHub is **only upstream identity verification** for the allowlisted operator.
- MCP client transport: the ChatGPT plugin calls the remote \`/mcp\` over HTTPS or Secure MCP Tunnel. Live \`tools/list\`, \`jazn_status\` and two **accepted** transactionally finalized turns are required to confirm Jaźń conversations.
- SIWC: OpenAI's separate identity and optional ChatGPT plan-usage consent for a locally hosted OSS model backend; it does **not** issue MCP resource bearer tokens. The existing \`siwc_plan_usage_adapter.py\` consumes a separately verified OAuth access token and is opt-in only; the repository does **not** yet implement the full secure browser/callback/JWKS/token store/refresh provider. Ollama remains available independently.

## Read-only check before changing deployment

Run \`python -X utf8 tools/chatgpt_oauth_live_preflight.py\` from a trusted operator host with network access. Its exit code is nonzero until 1) the authorization Worker has all required credentials, 2) the protected resource advertises the exact issuer/resource, 3) the authorization server advertises S256 and a supported registration method, and 4) unauthenticated \`/mcp\` challenges with 401. It does not read any secret nor enable proxying.

Only after all independent live checks pass, deploy the reviewed OAuth candidate using separate secure Cloudflare secret bindings, run the Python MCP server with \`--public-oauth\`, verify introspection and all negative conditions, then **opt in** \`jazn-runtime\` with \`JAZN_INGRESS_MODE=verified_oauth_proxy\`. Test externally with MCP Inspector, authenticated \`tools/list\`, and two accepted turns in ChatGPT, without replay or weakening finalization. Keep Worker fail-closed until those checks pass.

Separate SIWC implementation stage: browser callback on \`127.0.0.1\`, state/nonce/PKCE S256, persistent host ID, issued client ID, verified OpenAI JWKS ID token, independent secure refresh-token rotation and explicit \`chatgpt.tokens.use.direct\` scope, account-specific model catalog and \`store=false, stream=true\` Responses API. Never share SIWC tokens with the MCP Worker; never use unverified SIWC output as a Jaźń finalization. SIWC consent and local token storage are **not included** in this patch.

## Tests

- \`node --test deploy/chatgpt_mcp/workers_github_oauth/test/security.test.mjs deploy/chatgpt_mcp/workers_github_oauth/test/deployment-boundary.test.mjs\`
- \`python -X utf8 -m pytest -q tests/test_chatgpt_oauth_live_preflight.py\`
- \`python -X utf8 -m compileall -q latka_jazn tests main.py run.py\`
- \`python -X utf8 -m pytest -q -m "not live_model and not live_mcp"\`
- \`python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json\`
- inspect CI and independent OAuth live acceptance before any production claim.

Sources:
- https://developers.openai.com/plugins/build/auth
- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
- https://github.com/cloudflare/workers-oauth-provider/blob/main/docs/authorization-server.md
