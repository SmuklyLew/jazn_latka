import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SCOPES, ISSUER, RESOURCE, consentHtml, githubIdentityAllowed,
  tokenRecordToIntrospection, basicCredentialsMatch, randomVerifier, sha256Challenge, requiresSafeAuthSettings,
} from '../src/security.mjs';

test('MCP audience, issuer and the core scopes are not interchangeable', () => {
  assert.notEqual(RESOURCE, ISSUER);
  assert.ok(SCOPES.includes('jazn:mcp:connect'));
  assert.ok(SCOPES.includes('jazn:turn:finalize'));
});
test('GitHub identity must match the explicit login and optional numeric ID', () => {
  assert.equal(githubIdentityAllowed({ id: 123, login: 'SmuklyLew' }, 'smuklylew', '123'), true);
  assert.equal(githubIdentityAllowed({ id: 999, login: 'SmuklyLew' }, 'SmuklyLew', '123'), false);
  assert.equal(githubIdentityAllowed({ id: 123, login: 'Other' }, 'SmuklyLew', ''), false);
  assert.equal(githubIdentityAllowed({ id: '123', login: 'SmuklyLew' }, 'SmuklyLew'), false);
  assert.equal(githubIdentityAllowed({ id: 123, login: 'SmuklyLew' }, ''), false);
});
test('consent page escapes untrusted client metadata and scopes', () => {
  const html = consentHtml({ clientName: '<script>alert(1)</script>', clientDomain: 'evil"><img src=x>',
    redirectHost: '<anything>', scope: ['foo" autofocus'], redirectIsLoopback: true }, '<x>');
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('evil"><img'));
  assert.ok(html.includes('&#60;script&#62;'));
  assert.ok(html.includes('&#60;x&#62;'));
});
test('introspection rejects missing or mismatched audience, expiry, scope and client', () => {
  const valid = { audience: RESOURCE, clientId: 'client', userId: 'github:123', scope: ['jazn:mcp:connect'], expiresAt: Date.now()/1000+30 };
  assert.equal(tokenRecordToIntrospection(null).active, false);
  assert.equal(tokenRecordToIntrospection({ ...valid, audience: ISSUER }).active, false);
  assert.equal(tokenRecordToIntrospection({ ...valid, scope: [] }).active, false);
  assert.equal(tokenRecordToIntrospection({ ...valid, clientId: '' }).active, false);
  assert.equal(tokenRecordToIntrospection({ ...valid, expiresAt: 1 }).active, false);
  const result = tokenRecordToIntrospection(valid);
  assert.equal(result.active, true);
  assert.equal(result.aud, RESOURCE);
  assert.equal(result.iss, ISSUER);
  assert.equal(result.sub, 'github:123');
});
test('Basic authentication requires the exact secret, not GitHub Client Secret', async () => {
  const id='internal-resource-id', secret='test-only-not-a-production-secret';
  const headers = new Headers({authorization: 'Basic '+btoa(`${id}:${secret}`)});
  assert.equal(await basicCredentialsMatch({headers},id,secret),true);
  assert.equal(await basicCredentialsMatch({headers},id,'incorrect'),false);
  assert.equal(await basicCredentialsMatch({headers:new Headers({authorization:'Bearer fake'})},id,secret),false);
});
test('PKCE verifier uses S256 challenge and unpredictable random value', async () => {
  const a=randomVerifier(), b=randomVerifier();
  assert.match(a,/^[A-Za-z0-9_-]{43}$/);
  assert.notEqual(a,b);
  assert.match(await sha256Challenge(a),/^[A-Za-z0-9_-]{43}$/);
});
test('missing introspection secrets keep the auth Worker blocked', () => {
  const base={GITHUB_CLIENT_ID:'id',GITHUB_CLIENT_SECRET:'gsecret',JAZN_ALLOWED_GITHUB_LOGIN:'SmuklyLew',JAZN_ALLOWED_GITHUB_USER_ID:'123',OAUTH_KV:{}};
  assert.equal(requiresSafeAuthSettings(base),false);
  assert.equal(requiresSafeAuthSettings({...base,JAZN_INTROSPECTION_CLIENT_ID:'foo',JAZN_INTROSPECTION_CLIENT_SECRET:'bar'}),true);
});
