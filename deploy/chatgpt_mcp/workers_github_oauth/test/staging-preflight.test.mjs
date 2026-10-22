import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { auditStaging, parseConfig, checkFiles } from '../staging-preflight.mjs';

const production = parseConfig(readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8'));
const sample = parseConfig(readFileSync(new URL('../wrangler.staging.example.jsonc', import.meta.url), 'utf8'));
const candidate = () => ({
  ...structuredClone(sample),
  kv_namespaces: [{ binding: 'OAUTH_KV', id: 'abcdef0123456789abcdef0123456789' }],
});
const errors = config => auditStaging(production, config).errors;

test('tracked source template is safe and deliberately NOT deployable', () => {
  assert.deepEqual(checkFiles('template'), { ok: true, errors: [] });
  assert.equal(auditStaging(production, sample).ok, false);
  assert.ok(errors(sample).includes('staging_kv_id_invalid_or_placeholder'));
});
test('isolated candidate with a unique staging KV passes static checks only', () => {
  assert.deepEqual(auditStaging(production, candidate()), { ok: true, errors: [] });
});
test('production OAuth KV namespace can never be reused for staging', () => {
  const wrong = candidate();
  wrong.kv_namespaces[0].id = production.kv_namespaces[0].id;
  assert.ok(errors(wrong).includes('production_kv_reused'));
});
test('production Worker name and resources cannot become staging', () => {
  for (const property of ['name', 'main', 'workers_dev', 'preview_urls']) {
    const wrong = candidate(); wrong[property] = production[property];
    assert.equal(auditStaging(production, wrong).ok, false, property);
  }
  for (const variable of ['JAZN_AUTH_ENVIRONMENT', 'JAZN_OAUTH_ISSUER_URL', 'JAZN_OAUTH_RESOURCE_URL']) {
    const wrong = candidate();
    wrong.vars[variable] = production.vars?.[variable] || 'production';
    assert.equal(auditStaging(production, wrong).ok, false, variable);
  }
});
test('unwanted production bindings, embedded credentials and routes are rejected', () => {
  for (const field of ['routes', 'route', 'vpc_services', 'services', 'd1_databases', 'r2_buckets', 'env']) {
    const wrong = candidate(); wrong[field] = [];
    assert.ok(errors(wrong).includes('forbidden_staging_binding_' + field), field);
  }
  const wrong = candidate();
  wrong.vars.GITHUB_CLIENT_SECRET = 'would-be-secret';
  assert.ok(errors(wrong).includes('unexpected_staging_variable'));
});
test('missing and malformed configurations fail closed', () => {
  assert.equal(auditStaging(null, candidate()).ok, false);
  assert.equal(auditStaging(production, null).ok, false);
  const invalid = candidate(); invalid.kv_namespaces = [];
  assert.ok(errors(invalid).includes('staging_kv_binding_invalid'));
  const wrong = candidate(); wrong.compatibility_flags = [];
  assert.ok(errors(wrong).includes('compatibility_flags_mismatch'));
  assert.throws(() => parseConfig('{not valid json}'));
});
