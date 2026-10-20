import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ISSUER, RESOURCE, requiresSafeAuthSettings } from '../src/security.mjs';

const configured = () => ({
  GITHUB_CLIENT_ID: 'public-client-id',
  GITHUB_CLIENT_SECRET: 'github-secret-only-in-mock',
  JAZN_ALLOWED_GITHUB_LOGIN: 'allowed',
  JAZN_ALLOWED_GITHUB_USER_ID: '12345',
  JAZN_INTROSPECTION_CLIENT_ID: 'private-resource-client',
  JAZN_INTROSPECTION_CLIENT_SECRET: 'another-secret-only-in-mock',
  OAUTH_KV: {},
});

test('only the deployed Cloudflare account subdomain is canonical', () => {
  assert.equal(new URL(ISSUER).hostname, 'jazn-auth.jazn-lakta.workers.dev');
  assert.equal(new URL(RESOURCE).hostname, 'jazn-runtime.jazn-lakta.workers.dev');
  assert.notEqual(ISSUER, RESOURCE);
});

test('OAuth remains fail closed until the distinct required credentials are present', () => {
  assert.equal(requiresSafeAuthSettings(configured()), true);
  for (const key of Object.keys(configured())) {
    const bad = configured();
    delete bad[key];
    assert.equal(requiresSafeAuthSettings(bad), false, key);
  }
  assert.equal(requiresSafeAuthSettings({
    ...configured(), JAZN_INTROSPECTION_CLIENT_SECRET: configured().GITHUB_CLIENT_SECRET,
  }), false);
  assert.equal(requiresSafeAuthSettings({
    ...configured(), JAZN_ALLOWED_GITHUB_USER_ID: 'not-a-numeric-id',
  }), false);
  assert.equal(requiresSafeAuthSettings({
    ...configured(), JAZN_ALLOWED_GITHUB_USER_ID: '0',
  }), false);
});
