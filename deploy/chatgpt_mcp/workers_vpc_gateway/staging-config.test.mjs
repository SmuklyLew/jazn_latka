import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const p = new URL('./wrangler.staging.example.jsonc', import.meta.url);
const raw = readFileSync(p, 'utf8');
const sample = JSON.parse(raw.split(/\r?\n/).filter(line => !line.trimStart().startsWith('//')).join('\n'));

test('staging VPC gateway template is separate, nondeployable and fail closed', () => {
  assert.equal(sample.name, 'jazn-runtime-staging');
  assert.equal(sample.main, 'worker.mjs');
  assert.equal(sample.workers_dev, true);
  assert.equal(sample.preview_urls, false);
  assert.equal(sample.vpc_services?.length, 1);
  assert.equal(sample.vpc_services[0].binding, 'JAZN_PRIVATE_MCP');
  assert.equal(sample.vpc_services[0].service_id, 'REPLACE_WITH_ISOLATED_STAGING_VPC_SERVICE_ID');
  for (const field of ['vars','env','routes','route','kv_namespaces','services']) {
    assert.equal(Object.hasOwn(sample, field), false, field);
  }
  assert.ok(!raw.includes('verified_oauth_proxy'));
});
