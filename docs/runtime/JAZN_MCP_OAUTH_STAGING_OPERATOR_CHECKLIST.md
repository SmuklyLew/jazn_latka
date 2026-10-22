# Jaźń — isolated OAuth/MCP staging operator checklist

**System release:** 16.3.25.5.116.0.34.39
**Evidence:** source preparation only; NOT OAuth deployment, live MCP readiness or an accepted Jaźń turn.

## Boundaries and default state

Production-named Cloudflare Workers jazn-auth and jazn-runtime MUST remain fail-closed until acceptance.
A healthy cloudflared Tunnel, VPC binding, source test, static package, or ChatGPT plugin does not
prove a live/authenticated Jaźń runtime. No memory/SQLite data or secrets enter GitHub.

## Source-level preflight (offline, read-only)

From deploy/chatgpt_mcp/workers_github_oauth, run:

    npm ci --ignore-scripts --no-audit --no-fund
    npm run check
    npm run preflight:template

The tracked wrangler.staging.example.jsonc is deliberately nondeployable:
its staging KV ID is a placeholder. Create a NEW, separate staging KV namespace,
copy that example to the ignored wrangler.staging.jsonc and insert the staging KV ID.

Run these before considering a staging deployment:

    npm run preflight:staging
    npx --no-install wrangler deploy --dry-run --config wrangler.staging.jsonc

The preflight checks exact staging Worker name, issuer and resource, entrypoint,
compatibility, allowed variables, forbidden bindings, independent KV ID, and
separation from production KV. It never reads secrets or contacts Cloudflare.
PASS is NOT a permit to promote, nor evidence of working OAuth.

## GitHub OAuth staging App (operator action)

Open https://github.com/settings/developers and create a SEPARATE OAuth App:

- Application name: Jaźń OAuth Staging
- Homepage URL: https://jazn-auth-staging.jazn-lakta.workers.dev
- Authorization callback: https://jazn-auth-staging.jazn-lakta.workers.dev/callback
- Device flow disabled; no repository/admin scopes.

Current known allowlisted GitHub user login SmuklyLew, numeric user ID 216485861.
Verify those values before setup. This GitHub App authenticates the operator;
ChatGPT is a distinct MCP OAuth client, using CIMD/DCR. Do not confuse callbacks.

## Isolated Cloudflare bindings

- Worker: jazn-auth-staging, separate from jazn-auth.
- KV binding OAUTH_KV: point to a NEW staging namespace, never production KV.
- JAZN_AUTH_ENVIRONMENT = staging.
- JAZN_OAUTH_ISSUER_URL = https://jazn-auth-staging.jazn-lakta.workers.dev
- JAZN_OAUTH_RESOURCE_URL = https://jazn-runtime-staging.jazn-lakta.workers.dev/mcp
- GITHUB_CLIENT_ID = NEW staging GitHub OAuth App public client ID.
- GITHUB_CLIENT_SECRET = NEW staging GitHub OAuth secret; Cloudflare Secret binding.
- JAZN_ALLOWED_GITHUB_LOGIN = SmuklyLew.
- JAZN_ALLOWED_GITHUB_USER_ID = 216485861.
- JAZN_INTROSPECTION_CLIENT_ID = NEW independent resource-server client ID.
- JAZN_INTROSPECTION_CLIENT_SECRET = NEW unrelated secret; Cloudflare Secret binding.

Use separate GitHub credentials, introspection secret and KV. Never reuse
production tokens, IDs or resource audience. The Python resource server
must receive matching introspection client credentials through trusted host
environment secrets, not committed files, arguments or chat messages.

For the isolated VPC gateway, copy workers_vpc_gateway/wrangler.staging.example.jsonc
into a locally ignored staging configuration, replace the VPC Service placeholder
with the NEW nonproduction VPC Service ID, and provide the actual production
service ID as JAZN_PRODUCTION_VPC_SERVICE_ID (nonsecret) from Cloudflare API.
Run the read-only static preflight before ANY staging gateway dry-run:

    node deploy/chatgpt_mcp/workers_vpc_gateway/staging-preflight.mjs --candidate <local-staging-gateway.jsonc>

This candidate check requires valid distinct service IDs, a single bound VPC
service and NO forwarding/authorization variables. It cannot prove the selected
staging service actually reaches a nonproduction backend; verify that separately.

A separately named jazn-runtime-staging VPC Worker must use a separately
verified NONPRODUCTION backend/VPC Service. Do not proxy staging MCP into
the production daemon or memory. Keep JAZN_INGRESS_MODE unset until OAuth
and resource server have passed real integration checks.

## Windows / Python resource server

From an independently verified SYSTEM root, use the canonical run.py/main.py:

    py -X utf8 run.py --version
    py -X utf8 run.py host-preflight --json
    py -X utf8 run.py start
    py -X utf8 run.py status --json

Once the local MCP gateway is actually running and correctly configured, run:

    py -X utf8 run.py mcp-probe --url http://127.0.0.1:8080/mcp --check-chatgpt-tool-catalog --json

Production/public routing must use run.py mcp-http --public-oauth; NEVER
publish --loopback-dev, 127.0.0.1:8787 or an unauthenticated /mcp.
The loopback address is resolved on the cloudflared host, not in ChatGPT.

## Real staging acceptance: ALL gates required

1. Green Node 24 checks, packaging/release metadata, Pyright and required
   Python/Linux/Windows CI on final SHA. Static checks do not prove deployed OAuth.
2. Independent workerd/Miniflare test using actual OAuth provider and
   test GitHub consent flow; validate consent refusal, redirects, state and PKCE.
3. Verify discovery, issuer, CIMD/DCR, PKCE S256, exact resource audience,
   allowed GitHub numeric user ID and denial of all other identities.
4. Verify refresh/revocation and RFC7662 introspection: valid, absent,
   wrong audience, expired token, wrong introspection Basic credentials.
5. Private resource GET /.well-known/oauth-protected-resource and anonymous
   /mcp 401 Bearer challenge must identify the public staging resource.
   Runtime /readyz must prove a fresh, compatible, ready daemon.
6. External authenticated tools/list must contain jazn_status,
   jazn_generate_visible_reply, jazn_resume_visible_reply,
   jazn_finalize_reply. A static plugin manifest does not satisfy this check.
7. Execute TWO real sequential ChatGPT turns with stable session_id,
   unique request_id, verified turn_id/trace_id and accepted display_exact
   finalization/MessageEnvelope. Never replay already consumed messages.
8. Inject tunnel outage, restart, lost postcommit reply, invalid grant,
   revoked token and transient upstream failure; require fail-closed.
9. Before enabling production, record rollback Worker versions/binding types,
   get operator approval and verify zero private-memory exposure.
10. Attach and verify private MEMORY independently. Optional MEMORY missing
    does not block core; autobiographical recall needs local provenance.

Promotion gate: only after all checks pass, authorize reviewed production
configuration including verified_oauth_proxy, then update the private
ChatGPT MCP plugin, refresh its tools, and verify in a fresh conversation.

## Official references

- https://developers.openai.com/plugins/build/auth
- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://developers.cloudflare.com/workers/wrangler/environments/
- https://developers.cloudflare.com/kv/reference/environments/
- https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app
