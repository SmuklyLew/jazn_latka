// Jaźń Cloudflare gateway — staging release, explicit fail-closed transport.
// This Worker MUST NOT forward any MCP request until an OAuth-protected
// upstream and end-to-end authenticated runtime readiness are validated.
// Cloudflare Workers VPC attaches JAZN_PRIVATE_MCP to one service, but the
// existence of a binding is not proof that the service is reachable.
const HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
  "x-content-type-options": "nosniff",
};
export default {
  async fetch(request, _env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/healthz") {
      return new Response(JSON.stringify({
        gateway: "jazn-runtime",
        route: "cloudflare-workers-vpc",
        transport: "https",
        mcp_available: false,
        reason: "oauth_configuration_required",
      }), { status: 200, headers: HEADERS });
    }
    if (url.pathname === "/mcp" || url.pathname.startsWith("/.well-known/")) {
      return new Response(JSON.stringify({
        error: "mcp_unavailable",
        reason: "oauth_configuration_required",
        must_not_resubmit_user_message: true,
      }), {
        status: 503,
        headers: { ...HEADERS, "retry-after": "60" },
      });
    }
    return new Response(JSON.stringify({ error: "not_found" }), {
      status: 404,
      headers: HEADERS,
    });
  },
};
