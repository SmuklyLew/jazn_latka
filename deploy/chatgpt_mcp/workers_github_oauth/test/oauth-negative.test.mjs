import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  selectOAuthDeployment, STAGING_ISSUER, STAGING_RESOURCE, ISSUER, RESOURCE,
  githubIdentityAllowed, tokenRecordToIntrospection, basicCredentialsMatch,
} from '../src/security.mjs';

const staged = {
  JAZN_AUTH_ENVIRONMENT: 'staging',
  JAZN_OAUTH_ISSUER_URL: STAGING_ISSUER,
  JAZN_OAUTH_RESOURCE_URL: STAGING_RESOURCE,
};
const token = () => ({
  audience: STAGING_RESOURCE,
  clientId: 'chatgpt-staging',
  userId: 'github:123',
  scope: ['jazn:mcp:connect', 'jazn:turn:read'],
  expiresAt: Date.now() / 1000 + 3600,
});

test('staging never accepts production audience or missing issuer declaration', () => {
  assert.equal(selectOAuthDeployment(staged)?.issuer, STAGING_ISSUER);
  for (const wrong of [
    { ...staged, JAZN_OAUTH_ISSUER_URL: ISSUER },
    { ...staged, JAZN_OAUTH_RESOURCE_URL: RESOURCE },
    { ...staged, JAZN_OAUTH_ISSUER_URL: undefined },
    { ...staged, JAZN_OAUTH_RESOURCE_URL: undefined },
  ]) assert.equal(selectOAuthDeployment(wrong), null);
});

test('allowlist denies renamed, recycled and non-numeric GitHub accounts', () => {
  assert.equal(githubIdentityAllowed({ login:'SmuklyLew', id:123 }, 'SmuklyLew', '123'), true);
  for (const bad of [
    { login:'SmuklyLew', id:124 },
    { login:'other', id:123 },
    { login:'SmuklyLew', id:'123' },
    { login:'SmuklyLew', id:0 },
  ]) assert.equal(githubIdentityAllowed(bad, 'SmuklyLew', '123'), false);
});

test('introspection never activates expired, scope-less or wrong-audience tokens', () => {
  for (const bad of [
    { ...token(), audience: RESOURCE },
    { ...token(), audience: undefined },
    { ...token(), clientId: '' },
    { ...token(), scope: ['jazn:turn:read'] },
    { ...token(), scope: [] },
    { ...token(), expiresAt: Date.now()/1000 - 10 },
    { ...token(), expiresAt: NaN },
  ]) {
    assert.deepEqual(tokenRecordToIntrospection(bad, {issuer:STAGING_ISSUER,resource:STAGING_RESOURCE}), {active:false});
  }
});

test('introspection Basic credentials reject missing, wrong and bearer schemes', async () => {
  const clientId='staging-resource', secret='fake-only-secret';
  for(const authorization of [
    '',
    'Bearer fake-token',
    'Basic not-base64',
    'Basic ' + btoa(clientId + ':wrong'),
    'Basic ' + btoa('other:' + secret),
  ]) {
    assert.equal(await basicCredentialsMatch(
      new Request('https://example.test/oauth/introspect', {headers:{authorization}}),
      clientId, secret,
    ), false);
  }
});
