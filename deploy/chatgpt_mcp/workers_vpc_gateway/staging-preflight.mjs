// Offline staging VPC guard. Does not probe the gateway or contact Cloudflare.
// A passing config preflight cannot authorize a staging or production deployment.
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const PLACEHOLDER = 'REPLACE_WITH_ISOLATED_STAGING_VPC_SERVICE_ID';
const ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function parseJsonc(source) {
  return JSON.parse(source.split(/\r?\n/).filter(s => !s.trimStart().startsWith('//')).join('\n'));
}
export function auditGateway(config, productionServiceId, { template = false } = {}) {
  if (!config || typeof config !== 'object' || Array.isArray(config))
    return { ok: false, errors: ['invalid_gateway_configuration'] };
  const errors = [];
  const refuse = (condition, code) => { if (condition) errors.push(code); };
  refuse(config.name !== 'jazn-runtime-staging', 'worker_name_invalid');
  // Non-secret console variables are managed separately from the VPC binding.
  // A deploy must not silently remove them from an existing staging Worker.
  refuse(config.keep_vars !== true, 'keep_vars_required');
  refuse(config.main !== 'worker.mjs', 'worker_entrypoint_invalid');
  refuse(config.workers_dev !== true || config.preview_urls !== false, 'worker_exposure_flags_invalid');
  refuse(config.compatibility_date !== '2026-10-14', 'compatibility_date_invalid');
  const forbidden = ['vars','env','route','routes','services','kv_namespaces',
    'r2_buckets','d1_databases','durable_objects','assets'];
  for (const k of forbidden) refuse(Object.hasOwn(config,k), 'unexpected_gateway_binding_' + k);
  const bindings = config.vpc_services;
  refuse(!Array.isArray(bindings) || bindings.length !== 1 ||
    bindings[0]?.binding !== 'JAZN_PRIVATE_MCP' ||
    Object.keys(bindings[0] || {}).some(key => !['binding','service_id'].includes(key)),
  'isolated_vpc_binding_invalid');
  const id = bindings?.[0]?.service_id;
  if (template) {
    refuse(id !== PLACEHOLDER, 'template_id_placeholder_missing');
  } else {
    refuse(!ID_PATTERN.test(String(productionServiceId || '')), 'production_service_reference_missing');
    refuse(!ID_PATTERN.test(String(id || '')), 'staging_service_id_invalid');
    refuse(id === productionServiceId, 'production_vpc_service_reused');
  }
  return { ok: errors.length === 0, errors };
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const mode = process.argv[2], candidate = process.argv[3];
  if (!['--template','--candidate'].includes(mode) ||
      (mode === '--template' && process.argv.length !== 3) ||
      (mode === '--candidate' && process.argv.length !== 4)) {
    process.stdout.write(JSON.stringify({ ok:false, errors:['invalid_usage'] }) + '\n');
    process.exitCode = 2;
  } else {
    try {
      const input = mode === '--template'
        ? resolve(root, 'wrangler.staging.example.jsonc') : candidate;
      const cfg = parseJsonc(readFileSync(input, 'utf8'));
      const result = auditGateway(cfg, process.env.JAZN_PRODUCTION_VPC_SERVICE_ID,
        { template: mode === '--template' });
      process.stdout.write(JSON.stringify(result) + '\n');
      if (!result.ok) process.exitCode = 2;
    } catch {
      process.stdout.write(JSON.stringify({ ok:false, errors:['gateway_config_unreadable_or_invalid'] }) + '\n');
      process.exitCode = 2;
    }
  }
}
