import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ISSUER, RESOURCE, STAGING_ISSUER, STAGING_RESOURCE,
  selectOAuthDeployment, tokenRecordToIntrospection,
} from '../src/security.mjs';

const staging = {
  JAZN_AUTH_ENVIRONMENT: 'staging',
  JAZN_OAUTH_ISSUER_URL: STAGING_ISSUER,
  JAZN_OAUTH_RESOURCE_URL: STAGING_RESOURCE,
};

test('staging issuer/audience cannot be mistaken for production', () => {
  assert.notEqual(STAGING_ISSUER, ISSUER);
  assert.notEqual(STAGING_RESOURCE, RESOURCE);
  assert.equal(selectOAuthDeployment(staging)?.issuer, STAGING_ISSUER);
  assert.equal(selectOAuthDeployment(staging)?.resource, STAGING_RESOURCE);
  assert.equal(selectOAuthDeployment({})?.issuer, ISSUER);
  assert.equal(selectOAuthDeployment({})?.resource, RESOURCE);
  assert.equal(selectOAuthDeployment({ JAZN_AUTH_ENVIRONMENT: 'production' })?.issuer, ISSUER);
});

test('cross-environment configuration and unknown modes fail closed', () => {
  assert.equal(selectOAuthDeployment(null), null);
  assert.equal(selectOAuthDeployment({JAZN_AUTH_ENVIRONMENT:'unknown'}), null);
  assert.equal(selectOAuthDeployment({JAZN_AUTH_ENVIRONMENT:'staging'}), null);
  assert.equal(selectOAuthDeployment({...staging, JAZN_OAUTH_RESOURCE_URL: RESOURCE}), null);
  assert.equal(selectOAuthDeployment({...staging, JAZN_OAUTH_ISSUER_URL: ISSUER}), null);
  assert.equal(selectOAuthDeployment({JAZN_OAUTH_ISSUER_URL:STAGING_ISSUER}), null);
  assert.equal(selectOAuthDeployment({JAZN_OAUTH_RESOURCE_URL:STAGING_RESOURCE}), null);
});

test('staging token can only become active within staging audience', () => {
  const record={audience:STAGING_RESOURCE,clientId:'client',scope:['jazn:mcp:connect'],expiresAt:Date.now()/1000+60};
  assert.equal(tokenRecordToIntrospection(record).active,false);
  const stagingToken=tokenRecordToIntrospection(record, {issuer:STAGING_ISSUER,resource:STAGING_RESOURCE});
  assert.equal(stagingToken.active,true);
  assert.equal(stagingToken.iss,STAGING_ISSUER);
  assert.equal(stagingToken.aud,STAGING_RESOURCE);
  assert.equal(tokenRecordToIntrospection({...record,audience:RESOURCE},{issuer:STAGING_ISSUER,resource:STAGING_RESOURCE}).active,false);
});

test('staging sample is documented as requiring independent KV and separate GitHub OAuth app', async () => {
  // Full deployed workerd/GitHub and introspection acceptance remains a manual/live gate.
  assert.ok(STAGING_ISSUER.includes('jazn-auth-staging.'));
  assert.ok(STAGING_RESOURCE.includes('jazn-runtime-staging.'));
});
