// Pure helpers: no secrets, tokens, or user data persist here.
export const ISSUER = 'https://jazn-auth.jazn-lakta.workers.dev';
export const RESOURCE = 'https://jazn-runtime.jazn-lakta.workers.dev/mcp';
// Staging has a separate Worker, issuer, audience, GitHub OAuth app and KV namespace.
// Do not accept arbitrary issuer/resource URLs supplied by a request or a variable.
export const STAGING_ISSUER = 'https://jazn-auth-staging.jazn-lakta.workers.dev';
export const STAGING_RESOURCE = 'https://jazn-runtime-staging.jazn-lakta.workers.dev/mcp';

export function selectOAuthDeployment(env) {
  if (!env || typeof env !== 'object') return null;
  const stage = env.JAZN_AUTH_ENVIRONMENT;
  if (stage !== undefined && stage !== 'production' && stage !== 'staging') return null;
  const expected = stage === 'staging'
    ? { issuer: STAGING_ISSUER, resource: STAGING_RESOURCE, environment: 'staging' }
    : { issuer: ISSUER, resource: RESOURCE, environment: 'production' };
  // Staging MUST opt into its own issuer and resource. Production may omit the
  // new variables for backward-compatible staged rollouts, but any mismatched
  // declaration fails closed. Neither mode trusts client-supplied URLs.
  if ((stage === 'staging' || env.JAZN_OAUTH_ISSUER_URL !== undefined) &&
      env.JAZN_OAUTH_ISSUER_URL !== expected.issuer) return null;
  if ((stage === 'staging' || env.JAZN_OAUTH_RESOURCE_URL !== undefined) &&
      env.JAZN_OAUTH_RESOURCE_URL !== expected.resource) return null;
  return expected;
}
export const SCOPES = Object.freeze([
  'jazn:mcp:connect', 'jazn:turn:submit', 'jazn:turn:read',
  'jazn:turn:finalize', 'jazn:status:read', 'jazn:task:read',
  'jazn:task:update', 'jazn:task:cancel', 'offline_access',
]);
export const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
export function githubIdentityAllowed(profile, expectedLogin, expectedId) {
  if (!profile || !Number.isSafeInteger(profile.id) || profile.id <= 0 || typeof profile.login !== 'string') return false;
  if (!expectedLogin || typeof expectedLogin !== 'string' || !expectedId || !/^\d+$/.test(String(expectedId))) return false;
  if (profile.login.toLowerCase() !== expectedLogin.toLowerCase()) return false;
  if (String(profile.id) !== String(expectedId)) return false;
  return true;
}
export function tokenRecordToIntrospection(record, { issuer = ISSUER, resource = RESOURCE } = {}) {
  if (!record || record.audience !== resource || !Array.isArray(record.scope) ||
      !record.scope.includes('jazn:mcp:connect') || typeof record.clientId !== 'string' ||
      !record.clientId || typeof record.expiresAt !== 'number' ||
      !Number.isFinite(record.expiresAt) || record.expiresAt <= Date.now() / 1000) return { active: false };
  return {
    active: true, client_id: record.clientId, iss: issuer, aud: resource,
    scope: record.scope.join(' '), exp: Math.floor(record.expiresAt),
    ...(record.userId ? { sub: String(record.userId) } : {}),
  };
}
export function consentHtml(d, handle) {
  const scopes = d.scope.map((scope) => `<label><input type="checkbox" name="scope" value="${escapeHtml(scope)}" checked> ${escapeHtml(scope)}</label>`).join('<br>');
  const publisher = d.clientDomain
    ? `Verified document domain: <strong>${escapeHtml(d.clientDomain)}</strong>`
    : 'The client registered its own name; it has not been independently verified.';
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Jaźń OAuth approval</title>
  <h1>Authorize ${escapeHtml(d.clientName)}?</h1><p>${publisher}</p>
  <p>Return to <strong>${escapeHtml(d.redirectHost)}</strong>.</p>
  ${d.redirectIsLoopback ? '<p><strong>This will send access to an application running on your computer.</strong></p>' : ''}
  <form method="POST" action="/authorize"><input type="hidden" name="handle" value="${escapeHtml(handle)}">${scopes}
  <p><button name="decision" value="approve">Allow</button><button name="decision" value="deny">Deny</button></p></form></html>`;
}
export function requiresSafeAuthSettings(env) {
  // Missing credentials are never supplied by MCP, SIWC, or a package manifest.
  const numericUser = String(env?.JAZN_ALLOWED_GITHUB_USER_ID || '');
  const githubSecret = env?.GITHUB_CLIENT_SECRET;
  const introspectionSecret = env?.JAZN_INTROSPECTION_CLIENT_SECRET;
  return Boolean(
    typeof env?.GITHUB_CLIENT_ID === 'string' && env.GITHUB_CLIENT_ID.trim() &&
    typeof githubSecret === 'string' && githubSecret &&
    typeof env?.JAZN_ALLOWED_GITHUB_LOGIN === 'string' && env.JAZN_ALLOWED_GITHUB_LOGIN.trim() &&
    /^[1-9][0-9]*$/.test(numericUser) &&
    typeof env?.JAZN_INTROSPECTION_CLIENT_ID === 'string' && env.JAZN_INTROSPECTION_CLIENT_ID.trim() &&
    typeof introspectionSecret === 'string' && introspectionSecret &&
    githubSecret !== introspectionSecret &&
    env?.OAUTH_KV
  );
}
export function randomVerifier() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
export async function sha256Challenge(verifier) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
  return btoa(String.fromCharCode(...digest)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
// Compare hashes of fixed length without early-exit comparison. Reject oversized input first.
export async function basicCredentialsMatch(request, clientId, clientSecret) {
  const header = request.headers.get('authorization') || '';
  if (!header.startsWith('Basic ') || header.length > 8192 || !clientId || !clientSecret) return false;
  let decoded;
  try { decoded = atob(header.slice(6)); } catch { return false; }
  const colon = decoded.indexOf(':');
  if (colon < 0) return false;
  let supplied;
  try { supplied = `${decodeURIComponent(decoded.slice(0, colon).replace(/\+/g,'%20'))}:${decodeURIComponent(decoded.slice(colon + 1).replace(/\+/g,'%20'))}`; }
  catch { return false; }
  const expected = `${clientId}:${clientSecret}`;
  const a = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(supplied)));
  const b = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(expected)));
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}
