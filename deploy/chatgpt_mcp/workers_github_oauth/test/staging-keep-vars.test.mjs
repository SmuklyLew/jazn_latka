import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { auditStaging, parseConfig } from '../staging-preflight.mjs';

const production = parseConfig(readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8'));
const template = parseConfig(readFileSync(new URL('../wrangler.staging.example.jsonc', import.meta.url), 'utf8'));

function candidate() {
  return { ...structuredClone(template), kv_namespaces: [{ binding: 'OAUTH_KV', id: 'abcdef0123456789abcdef0123456789' }] };
}

test('reviewed staging template requires Cloudflare dashboard variable preservation', () => {
  assert.equal(template.keep_vars, true);
  assert.deepEqual(auditStaging(production, candidate()), { ok: true, errors: [] });
});

test('missing or false keep_vars rejects a deploy candidate', () => {
  for (const change of ['missing', false, 'true', 1]) {
    const cfg = candidate();
    if (change === 'missing') delete cfg.keep_vars;
    else cfg.keep_vars = change;
    const result = auditStaging(production, cfg);
    assert.equal(result.ok, false);
    assert.ok(result.errors.includes('staging_keep_vars_required'));
  }
});
