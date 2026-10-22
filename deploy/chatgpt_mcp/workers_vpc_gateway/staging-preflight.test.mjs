import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { auditGateway, parseJsonc } from './staging-preflight.mjs';

const template = parseJsonc(readFileSync(new URL('./wrangler.staging.example.jsonc', import.meta.url), 'utf8'));
const production = '11111111-1111-4111-8111-111111111111';
const candidate = () => ({
  ...structuredClone(template),
  vpc_services:[{ binding:'JAZN_PRIVATE_MCP', service_id:'22222222-2222-4222-8222-222222222222' }],
});
test('staging gateway source template is intentionally nondeployable', () => {
  assert.equal(auditGateway(template, null, {template:true}).ok, true);
  assert.equal(auditGateway(template, production).ok, false);
});
test('isolated VPC candidate accepts only a distinct well-formed service ID', () => {
  assert.deepEqual(auditGateway(candidate(), production), {ok:true, errors:[]});
  const wrong = candidate(); wrong.vpc_services[0].service_id = production;
  assert.ok(auditGateway(wrong, production).errors.includes('production_vpc_service_reused'));
  assert.ok(auditGateway(candidate(), null).errors.includes('production_service_reference_missing'));
});
test('no production binding or activation var can sneak into VPC candidate', () => {
  const wrong = candidate(); wrong.vars={JAZN_INGRESS_MODE:'verified_oauth_proxy'};
  assert.ok(auditGateway(wrong, production).errors.includes('unexpected_gateway_binding_vars'));
  const duplicated = candidate(); duplicated.vpc_services.push(duplicated.vpc_services[0]);
  assert.ok(auditGateway(duplicated, production).errors.includes('isolated_vpc_binding_invalid'));
  const badName = candidate(); badName.name='jazn-runtime';
  assert.ok(auditGateway(badName, production).errors.includes('worker_name_invalid'));
});
