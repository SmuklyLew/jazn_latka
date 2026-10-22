# Jaźń GitHub OAuth authorization server — review stage (not enabled)

This deployment is separate from the persistent Jaźń runtime and from `jazn-runtime`,
the existing fail-closed Workers VPC proxy. No private MEMORY enters Cloudflare.

## Important current state

This directory contains a *candidate implementation*, NOT proof of OAuth readiness.
The live `jazn-auth` Worker currently returns HTTP 503 and the live `jazn-runtime`
Worker keeps MCP forwarding disabled. Deploy neither until the explicit acceptance
below passes. No server credentials or tokens are included in this repository.

## Architecture

```
ChatGPT -> HTTPS /mcp (jazn-runtime) -> VPC -> 127.0.0.1:8080 Python --public-oauth -> daemon :8787
                          |                                           |
                          |                                          HTTPS RFC7662 POST
                          |                                           v
                  (resource metadata)                   jazn-auth /oauth/introspect
                                                              |
                                             GitHub identity + issued MCP tokens
```

`jazn-auth` uses `@cloudflare/workers-oauth-provider` v1 for OAuth discovery,
CIMD/DCR, authorization-code+PKCE, token issuance, refresh and revocation.
The library's consent and upstream helpers bind approvals and GitHub state to
the browser. The GitHub OAuth App is used ONLY to authenticate one allowlisted
GitHub account, *not* as ChatGPT's MCP OAuth client. It requests no repository
scopes. The corresponding GitHub callback is exactly
`https://jazn-auth.jazn-lakta.workers.dev/callback`.

The Auth Worker additionally exposes a Basic-authenticated RFC 7662-compatible
`POST /oauth/introspect` endpoint for Jaźń's existing Python verifier. The
introspection client ID and secret are separate from GitHub's Client ID/secret.
The SDK token's audience, scopes and expiry are validated before returning
`active:true`. Invalid tokens receive `active:false`, an unavailable verifier
fails closed. Do not create an anonymous MCP bypass.

## Cloudflare configuration

Pre-existing: Worker `jazn-auth`, KV binding `OAUTH_KV`, plain text
`GITHUB_CLIENT_ID`, secret `GITHUB_CLIENT_SECRET` and route `workers.dev`.
Before any real auth deployment, add these NEW variables/secrets:

- `JAZN_INTROSPECTION_CLIENT_ID`: separate, unique, non-sensitive identifier.
- `JAZN_INTROSPECTION_CLIENT_SECRET`: **new high-entropy secret**, distinct from
  `GITHUB_CLIENT_SECRET` and set only via Cloudflare's secure secret management.
- `JAZN_ALLOWED_GITHUB_LOGIN` and `JAZN_ALLOWED_GITHUB_USER_ID`: required
  allowlist values, both checked by the authentication callback. Use the
  immutable numeric account ID so a renamed/recycled login cannot gain access.

`wrangler.jsonc` binds the account's existing KV namespace and public client ID.
Review resource identifiers and permissions before using it on another account.
Do not commit or print either secret. The tracked `package-lock.json` was
created by the isolated GitHub Actions Node 24 staging build and fixes the
resolved OAuth provider version at `1.2.3` (93 package records). Run `npm ci`
and `npm run check` to use these exact resolved dependencies.
Also run `npm run test:workerd` (bundled Worker inside local Miniflare/workerd)
for invalid-credential and incomplete-staging fail-closed smoke. This does not
verify a real GitHub login or ChatGPT callback. Do not silently
upgrade them in production. The staging build also runs Wrangler `deploy --dry-run`
and does **not** publish to Cloudflare.

**Warning:** `wrangler deploy` replaces Worker code and can affect bindings.
The isolated staging template deliberately requires `keep_vars: true` so a
subsequent Wrangler deployment preserves dashboard-only TEXT variables;
`staging-preflight.mjs` rejects candidates without this flag. Use Cloudflare
Secret bindings for both credentials and verify binding names/types after deploy.
Save a rollback deployment/version, record all binding *names and types* and
review the diff. Verify that `GITHUB_CLIENT_SECRET` and `OAUTH_KV` remain
present afterward without reading the secret value. Never deploy the candidate
straight to the live Worker before these checks and OAuth integration tests.

## Windows / Python resource-server configuration

Do NOT expose `--loopback-dev` through Cloudflare. The local no-auth test on
127.0.0.1:8080 is not a production configuration. Stop it before switching.
Run the same pinned `mcp-http` Python profile in `--public-oauth` mode using:

```powershell
# Prerequisite: env.JAZN_MCP_OAUTH_CLIENT_ID and ..._SECRET set securely on the host.
# Those values MUST match the separate introspection client credentials in jazn-auth.
& $MCP_PY -X utf8 run.py mcp-http --public-oauth `
    --host 127.0.0.1 --port 8080 --daemon-url 'http://127.0.0.1:8787' `
    --oauth-issuer-url 'https://jazn-auth.jazn-lakta.workers.dev' `
    --oauth-resource-server-url 'https://jazn-runtime.jazn-lakta.workers.dev/mcp' `
    --oauth-introspection-url 'https://jazn-auth.jazn-lakta.workers.dev/oauth/introspect' `
    --allowed-host 'jazn-runtime.jazn-lakta.workers.dev' `
    --allowed-origin 'https://chatgpt.com'
```

The Python code in `latka_jazn/mcp/oauth_introspection.py` already requires HTTPS,
checks `active`, matching issuer, exact resource audience and scopes, and
receives the credentials from environment variables. Keep the inner daemon
at 127.0.0.1:8787. The Workers VPC service targets the machine running
`cloudflared`; verify that it really reaches port 8080 there.

## Mandatory staged acceptance (all required)

1. Build the JS module with actual provider v1 and test it using workerd/Miniflare
   plus the GitHub OAuth sandbox or a controlled live login. `node --test`
   helper tests alone are **not sufficient**.
2. Verify OAuth discovery advertises S256, the correct issuer and resource,
   and CIMD or DCR registration, per OpenAI's documentation.
3. Test consent rejection, bad client redirects, GitHub refusal, state/cookie
   mismatch, wrong GitHub numeric user ID and missing/expired tokens.
4. Test refresh/revocation; test introspection with invalid token (`active:false`),
   wrong Basic credential (401), valid token (correct `iss`, `aud`, scopes, `exp`),
   and token from a different resource (inactive).
5. Restart Python as `--public-oauth`; GET private
   `/.well-known/oauth-protected-resource` should identify the exact public
   resource and issuer, and unauthenticated `/mcp` should return **401 with
   a Bearer challenge** (not 200, not 503). Ensure `/readyz` reflects runtime.
6. Only then set `JAZN_INGRESS_MODE=verified_oauth_proxy`,
   `JAZN_PUBLIC_MCP_URL=https://jazn-runtime.jazn-lakta.workers.dev/mcp`,
   `JAZN_OAUTH_ISSUER_URL=https://jazn-auth.jazn-lakta.workers.dev` on the
   separate `jazn-runtime` Worker. Keep the fail-closed private OAuth boundary
   verification in `worker.mjs`.
7. Test from an external client: initial 401/metadata, ChatGPT OAuth,
   authenticated `tools/list`, all four canonical tools and **two sequential
   generate/resume/finalize turns** with accepted `display_exact` and no replay.
8. Test denial conditions, tunnel loss, daemon restart, expiry, revocation and
   failed upstream response. Restore the prior Worker deployment if any gate fails.

Current state is strictly **predeployment**; do not claim production readiness.

## References

- https://developers.cloudflare.com/changelog/post/2026-10-01-workers-oauth-provider-1x/
- https://github.com/cloudflare/workers-oauth-provider/blob/main/docs/upstream-sign-in.md
- https://github.com/cloudflare/workers-oauth-provider/blob/main/docs/consent-page.md
- https://github.com/cloudflare/workers-oauth-provider/blob/main/docs/authorization-server.md
- https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
- https://developers.openai.com/plugins/build/auth
- https://datatracker.ietf.org/doc/html/rfc7662
## Isolated staging v116.0.34.27 (never auto-deploy)

Before production, validate the candidate from a separate GitHub branch and a separate Cloudflare Worker. Cloudflare Wrangler environments or a separately named staging Worker use independent KV/secret bindings (see https://developers.cloudflare.com/workers/wrangler/environments/ and https://developers.cloudflare.com/kv/reference/environments/). Version URLs alone do not provide storage isolation.

**Canonical staging endpoints**:
- issuer: `https://jazn-auth-staging.jazn-lakta.workers.dev`
- resource: `https://jazn-runtime-staging.jazn-lakta.workers.dev/mcp`

Create a NEW staging KV namespace (do not use production KV ID `b48aac7986a44fd98b905c12a1cea86a`). Create a separate GitHub OAuth App with callback `https://jazn-auth-staging.jazn-lakta.workers.dev/callback`. Use different Client ID/Secret than production. Copy `wrangler.staging.example.jsonc` to the ignored `wrangler.staging.jsonc` and substitute only the new staging KV ID.

Stage Worker requires `GITHUB_CLIENT_ID` (nonsecret variable), `GITHUB_CLIENT_SECRET` (secret), `JAZN_ALLOWED_GITHUB_LOGIN`, `JAZN_ALLOWED_GITHUB_USER_ID` (both variables), `JAZN_INTROSPECTION_CLIENT_ID` (variable), `JAZN_INTROSPECTION_CLIENT_SECRET` (secret), and `OAUTH_KV` (separate KV). In staging, the two URL vars must exactly match the staging constants; wrong host, issuer, audience or unrecognized environment is refused. **Never reuse production secrets or tokens**, and never forward production MCP through the staging resource identifier.

Before deployment: stage credentials securely and run `npm ci && npm run check && npx wrangler deploy --dry-run --config wrangler.staging.jsonc` from this directory. The dry run does not prove working OAuth. Deploy only with `npx wrangler deploy --config wrangler.staging.jsonc` after review, and perform real staging discovery, PKCE, denial and error cases, GitHub login/consent, token refresh/revoke, and introspection (valid/invalid token) with isolated KV. All failures must leave production unchanged. The staging resource is not yet a live MCP server; test full end-to-end only after separately securing and bringing up a staging resource server.

Production must stay on the existing fail-closed `jazn-auth` stub and `jazn-runtime` staging VPC Worker until the runbook's mandatory live gates pass. A green GitHub Actions Node check is source-level/staging-build evidence only. Do not claim any live OAuth activation, ChatGPT tool availability or accepted Jaźń turn from it.
