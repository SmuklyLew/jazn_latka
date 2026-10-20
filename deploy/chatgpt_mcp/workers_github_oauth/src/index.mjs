// Separate MCP authorization server. GitHub authenticates a single allowlisted identity.
// The library issues MCP-specific OAuth tokens; GitHub tokens are never passed to Jaźń.
import { OAuthAuthorizationServer, AuthorizationError, authorizationErrorRedirect } from '@cloudflare/workers-oauth-provider';
import { WorkerEntrypoint } from 'cloudflare:workers';
import {
  ISSUER, RESOURCE, SCOPES, consentHtml, githubIdentityAllowed,
  tokenRecordToIntrospection, requiresSafeAuthSettings, randomVerifier,
  sha256Challenge, basicCredentialsMatch,
} from './security.mjs';

const auth = new OAuthAuthorizationServer({
  issuer: ISSUER,
  resources: [RESOURCE],
  scopesSupported: SCOPES,
  clientIdMetadataDocumentEnabled: true,
  clientRegistrationEndpoint: '/oauth/register',
});
const noStore = { 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' };
function textError(message, status = 400) {
  return new Response(message, { status, headers: { ...noStore, 'content-type': 'text/plain; charset=utf-8' } });
}
async function authorize(request, env) {
  const oauth = auth.getOAuthApi(env);
  try {
    if (request.method === 'GET') {
      const parsed = await oauth.parseAuthRequest(request); // PKCE/resource/redirect validated by SDK
      const description = await oauth.describeConsent(parsed);
      const { headers, handle } = await oauth.beginConsent(parsed);
      headers.set('Content-Type', 'text/html; charset=utf-8');
      return new Response(consentHtml(description, handle), { headers });
    }
    if (request.method === 'POST') {
      if (Number(request.headers.get('content-length') || 0) > 8192) return textError('Form too large', 413);
      const form = await request.formData();
      const handle = String(form.get('handle') || '');
      if (form.get('decision') !== 'approve') {
        const { headers } = await oauth.denyConsent(request, handle);
        return new Response(null, { status: 302, headers });
      }
      const approved = await oauth.approveConsent(request, handle, { scope: form.getAll('scope').map(String) });
      const verifier = randomVerifier();
      const { state, headers } = await oauth.beginUpstream(approved.request, { data: { verifier }, headers: approved.headers });
      const github = new URL('https://github.com/login/oauth/authorize');
      github.searchParams.set('client_id', env.GITHUB_CLIENT_ID);
      github.searchParams.set('redirect_uri', `${ISSUER}/callback`);
      github.searchParams.set('state', state);
      github.searchParams.set('code_challenge', await sha256Challenge(verifier));
      github.searchParams.set('code_challenge_method', 'S256');
      github.searchParams.set('allow_signup', 'false');
      // We only verify GitHub's /user identity; no repository or email scopes.
      headers.set('Location', github.href);
      return new Response(null, { status: 302, headers });
    }
    return textError('Method not allowed', 405);
  } catch (error) {
    if (error instanceof AuthorizationError) {
      if (error.redirectTo) return Response.redirect(error.redirectTo, 302);
      return textError('Authorization request rejected', 400);
    }
    throw error; // do not conceal SDK or KV errors as accepted authorizations
  }
}
async function callback(request, env) {
  if (request.method !== 'GET') return textError('Method not allowed', 405);
  const oauth = auth.getOAuthApi(env);
  const { request: original, data, headers } = await oauth.finishUpstream(request);
  const query = new URL(request.url).searchParams;
  if (query.has('error')) {
    headers.set('Location', authorizationErrorRedirect(original, 'access_denied'));
    return new Response(null, { status: 302, headers });
  }
  const code = query.get('code');
  if (!code || typeof data?.verifier !== 'string') return textError('Incomplete callback', 400);
  const tokenReply = await fetch('https://github.com/login/oauth/access_token', {
    method: 'POST', headers: { 'accept': 'application/json', 'content-type': 'application/json' },
    body: JSON.stringify({ client_id: env.GITHUB_CLIENT_ID, client_secret: env.GITHUB_CLIENT_SECRET,
      code, redirect_uri: `${ISSUER}/callback`, code_verifier: data.verifier }),
    redirect: 'manual',
  });
  if (!tokenReply.ok) return textError('GitHub token exchange failed', 502);
  const credentials = await tokenReply.json();
  if (credentials.error || typeof credentials.access_token !== 'string' || credentials.token_type?.toLowerCase() !== 'bearer') {
    return textError('GitHub did not issue a usable token', 403);
  }
  const profileReply = await fetch('https://api.github.com/user', {
    headers: { 'authorization': `Bearer ${credentials.access_token}`, 'accept': 'application/vnd.github+json',
      'user-agent': 'jazn-github-oauth', 'x-github-api-version': '2022-11-28' }, redirect: 'manual',
  });
  if (!profileReply.ok) return textError('GitHub identity check failed', 403);
  const profile = await profileReply.json();
  if (!githubIdentityAllowed(profile, env.JAZN_ALLOWED_GITHUB_LOGIN, env.JAZN_ALLOWED_GITHUB_USER_ID)) {
    headers.set('Location', authorizationErrorRedirect(original, 'access_denied'));
    return new Response(null, { status: 302, headers });
  }
  const completed = await oauth.completeAuthorization({
    request: original,
    userId: `github:${profile.id}`,
    metadata: { githubLogin: profile.login },
    scope: original.scope,
    props: { userId: `github:${profile.id}` },
  });
  headers.set('Location', completed.redirectTo);
  return new Response(null, { status: 302, headers });
}
async function introspect(request, env) {
  if (request.method !== 'POST') return textError('Method not allowed', 405);
  if (!(await basicCredentialsMatch(request, env.JAZN_INTROSPECTION_CLIENT_ID, env.JAZN_INTROSPECTION_CLIENT_SECRET))) {
    return new Response(null, { status: 401, headers: { ...noStore, 'www-authenticate': 'Basic realm="Jaźń MCP introspection"' } });
  }
  if (Number(request.headers.get('content-length') || 0) > 8192) return textError('Form too large', 413);
  const body = await request.text();
  if (body.length > 8192) return textError('Form too large', 413);
  const token = new URLSearchParams(body).get('token');
  let verified = null;
  if (token && token.length <= 4096) {
    try { verified = await auth.validateToken(RESOURCE, token, env); }
    catch { return textError('Token verification unavailable', 503); }
  }
  return new Response(JSON.stringify(tokenRecordToIntrospection(verified)), {
    status: 200, headers: { ...noStore, 'content-type': 'application/json; charset=utf-8' },
  });
}
async function serve(request, env, ctx) {
  const url = new URL(request.url);
  if (url.origin !== ISSUER) return textError('Unexpected host', 403);
  // A public /healthz reports deployment configuration, NOT OAuth or MCP readiness.
  // This endpoint must never return tokens, binding values or a synthetic ready=true.
  if (request.method === 'GET' && url.pathname === '/healthz') {
    const configured = requiresSafeAuthSettings(env);
    return new Response(JSON.stringify({
      service: 'jazn-auth', deployment_configured: configured,
      end_to_end_verified: false,
    }), {
      status: configured ? 200 : 503,
      headers: { ...noStore, 'content-type': 'application/json; charset=utf-8' },
    });
  }
  if (!requiresSafeAuthSettings(env)) return textError('OAuth deployment incomplete', 503);
  if (url.pathname === '/authorize') return authorize(request, env);
  if (url.pathname === '/callback') return callback(request, env);
  if (url.pathname === '/oauth/introspect') return introspect(request, env);
  return auth.fetch(request, env, ctx); // well-known discovery, registration, token/refresh/revoke
}
export class AuthServer extends WorkerEntrypoint {
  fetch(request) { return serve(request, this.env, this.ctx); }
  validateToken(resource, token) { return auth.validateToken(resource, token, this.env); }
}
export default { fetch(request, env, ctx) { return serve(request, env, ctx); } };
