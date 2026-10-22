import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { auditGateway, parseJsonc } from './staging-preflight.mjs';

const template = parseJsonc(readFileSync(
  new URL('./wrangler.staging.example.jsonc', import.meta.url), 'utf8'));
const stagingService = '22222222-2222-4222-8222-222222222222';
const productionService = '11111111-1111-4111-8111-111111111111';
const candidate = () => ({
  ...structuredClone(template),
  vpc_services: [{ binding: 'JAZN_PRIVATE_MCP', service_id: stagingService }],
});

test('staging VPC template preserves dashboard-managed variables', () => {
  assert.equal(template.keep_vars, true);
  assert.deepEqual(auditGateway(candidate(), productionService), { ok: true, errors: [] });
});

test('missing, false and nonboolean keep_vars are rejected before deploy', () => {
  for (const value of [undefined, false, 'true', 1, null]) {
    const cfg = candidate();
    if (value === undefined) delete cfg.keep_vars;
    else cfg.keep_vars = value;
    const result = auditGateway(cfg, productionService);
    assert.equal(result.ok, false);
    assert.ok(result.errors.includes('keep_vars_required'));
  }
});

test('dashboard preservation never allows inline OAuth secrets or active forwarding', () => {
  const cfg = candidate();
  cfg.vars = { JAZN_INGRESS_MODE: 'verified_oauth_proxy' };
  assert.ok(auditGateway(cfg, productionService).errors.includes('unexpected_gateway_binding_vars'));
  delete cfg.vars;
  cfg.vpc_services[0].service_id = productionService;
  assert.ok(auditGateway(cfg, productionService).errors.includes('production_vpc_service_reused'));
});
