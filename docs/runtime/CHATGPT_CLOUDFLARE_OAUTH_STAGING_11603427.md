# Jaźń OAuth MCP stage→production release gate v16.3.25.5.116.0.34.27

Source: Cloudflare Workers environments (https://developers.cloudflare.com/workers/wrangler/environments/), isolated KV (https://developers.cloudflare.com/kv/reference/environments/), Cloudflare Previews comparison (https://developers.cloudflare.com/workers/previews/compare-workflows/), OpenAI auth (https://developers.openai.com/plugins/build/auth), official workers-oauth-provider (https://github.com/cloudflare/workers-oauth-provider/blob/main/docs/authorization-server.md).

## Stage A: independent preview and authorization service
- Leave prod `jazn-auth` deployment `cd8ce770` and prod `jazn-runtime` in fail-closed mode (HTTP 503).
- Staging is its own Worker `jazn-auth-staging`, KV, GitHub OAuth app, two separate secrets, issuer, resource and login allowlist. Treat the checked-in staging Wrangler config as **template** only; it contains an intentionally invalid placeholder for KV ID.
- Do not infer security from `/healthz`. Stage `/.well-known/oauth-authorization-server` must return matching issuer, authorization/token endpoints, CIMD or DCR and PKCE S256.
- Check deny, wrong redirect, mismatched GitHub identity/ID, state/cookie tamper, non-matching audiences and scopes, token expiry/refresh/revoke, invalid Basic introspection, wrong resource token, anonymous public HTTP.
- Test the actual library with workerd/Miniflare and controlled browser consent, not just unit tests.

## Stage B: switch local Python to protected MCP
- On Windows retain the verified core daemon. Stop ONLY the separately launched loopback `run.py mcp-http --loopback-dev` listener using Ctrl+C.
- Host uses host-protected introspection credentials matching production AS; never copy them into GitHub, this runbook, scripts or prompt.
- Start `run.py mcp-http --public-oauth` with **production** issuer/resource/introspection URL, loopback bind and correct public Host/Origins. Check backend daemon readiness and VPC tunnel reachability.
- A production stage is **not** authorized merely because staging OAuth works. Run independent live acceptance for the exact production issuer/resource.

## Stage C: production Cloudflare gate
- Save the currently deployed Worker version and binding names/types for rollback. Review `wrangler deploy --dry-run`; production deploy requires existing secrets and KV preserved.
- Deploy reviewed `jazn-auth` and repeat discovery/PKCE/credential/introspection tests against production account.
- Only after validated `--public-oauth` backend and VPC transport, explicitly enable `JAZN_INGRESS_MODE=verified_oauth_proxy` with the exact URLs for production `jazn-runtime`.
- Require `POST /mcp` without token to return 401 with correct Bearer `resource_metadata` challenge, not 503/200.
- Authenticated `tools/list` must expose four ChatGPT turn tools. Install and select the MCP plugin in ChatGPT and verify fresh `jazn_status` with challenge nonce and two sequential `display_exact` accepted finalizations.
- Loss of tunnel, bad token, failed introspection, mismatched resource or unknown ChatGPT current-turn toolset = blocked, never anonymously proxy, do not replay accepted turns.

**Not performed by a source code commit**: creation of staging KV/App/secrets, deployment, OAuth consent, tunnel verification, ChatGPT binding, or final accepted turn. These require live operator-controlled environment and credentials.
