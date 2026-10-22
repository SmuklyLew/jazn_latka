// Offline and read-only pre-deployment guard. Never prints config values or secrets.
// A PASS is static configuration evidence, NOT deployed OAuth/MCP readiness.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { STAGING_ISSUER, STAGING_RESOURCE } from './src/security.mjs';

const directory = dirname(fileURLToPath(import.meta.url));
const TEMPLATE_KV = 'REPLACE_WITH_NEW_ISOLATED_STAGING_KV_ID';
const VARIABLE_NAMES = Object.freeze([
  'JAZN_AUTH_ENVIRONMENT', 'JAZN_OAUTH_ISSUER_URL', 'JAZN_OAUTH_RESOURCE_URL',
]);
const FORBIDDEN_BINDINGS = Object.freeze([
  'env', 'route', 'routes', 'services', 'vpc_services', 'd1_databases',
  'r2_buckets', 'durable_objects', 'queues', 'assets',
]);

export function parseConfig(source) {
  // The tracked JSONC templates use whole-line // comments only.
  // Refuse unsupported inline comments rather than accidentally rewriting URLs.
  return JSON.parse(source.split(/\r?\n/).filter(line => !line.trimStart().startsWith('//')).join('\n'));
}

export function auditStaging(production, staging, { template = false } = {}) {
  const errors = [];
  const reject = (condition, code) => { if (condition) errors.push(code); };
  if (!production || typeof production !== 'object' || Array.isArray(production) ||
      !staging || typeof staging !== 'object' || Array.isArray(staging)) {
    return { ok: false, errors: ['invalid_configuration_shape'] };
  }
  const prodKv = Array.isArray(production.kv_namespaces) ? production.kv_namespaces : [];
  const stageKv = Array.isArray(staging.kv_namespaces) ? staging.kv_namespaces : [];
  const vars = staging.vars;
  reject(production.name !== 'jazn-auth', 'production_reference_name_invalid');
  reject(prodKv.length !== 1 || prodKv[0]?.binding !== 'OAUTH_KV' ||
    !/^[a-f0-9]{32}$/.test(prodKv[0]?.id || ''), 'production_kv_reference_invalid');
  reject(staging.name !== 'jazn-auth-staging', 'staging_worker_name_invalid');
  reject(staging.main !== production.main || staging.main !== 'src/index.mjs', 'worker_entrypoint_mismatch');
  reject(staging.workers_dev !== true, 'staging_workers_dev_required');
  reject(staging.preview_urls !== false, 'staging_previews_must_be_disabled');
  reject(staging.compatibility_date !== production.compatibility_date, 'compatibility_date_mismatch');
  reject(JSON.stringify(staging.compatibility_flags || []) !==
    JSON.stringify(production.compatibility_flags || []), 'compatibility_flags_mismatch');
  for (const key of FORBIDDEN_BINDINGS) {
    reject(Object.hasOwn(staging, key), 'forbidden_staging_binding_' + key);
  }
  reject(!vars || typeof vars !== 'object' || Array.isArray(vars), 'staging_vars_missing');
  if (vars && typeof vars === 'object' && !Array.isArray(vars)) {
    reject(Object.keys(vars).some(key => !VARIABLE_NAMES.includes(key)), 'unexpected_staging_variable');
    reject(Object.keys(vars).length !== VARIABLE_NAMES.length, 'staging_variable_set_incomplete');
    reject(vars.JAZN_AUTH_ENVIRONMENT !== 'staging', 'staging_environment_invalid');
    reject(vars.JAZN_OAUTH_ISSUER_URL !== STAGING_ISSUER, 'staging_issuer_invalid');
    reject(vars.JAZN_OAUTH_RESOURCE_URL !== STAGING_RESOURCE, 'staging_resource_invalid');
  }
  reject(stageKv.length !== 1 || stageKv[0]?.binding !== 'OAUTH_KV', 'staging_kv_binding_invalid');
  const stageId = stageKv[0]?.id;
  if (template) {
    reject(stageId !== TEMPLATE_KV, 'template_placeholder_changed');
  } else {
    reject(typeof stageId !== 'string' || !/^[a-f0-9]{32}$/.test(stageId),
      'staging_kv_id_invalid_or_placeholder');
    reject(stageId === prodKv[0]?.id, 'production_kv_reused');
  }
  return { ok: errors.length === 0, errors };
}

export function checkFiles(mode, candidatePath) {
  const production = parseConfig(readFileSync(resolve(directory, 'wrangler.jsonc'), 'utf8'));
  const configPath = mode === 'template'
    ? resolve(directory, 'wrangler.staging.example.jsonc')
    : candidatePath;
  const staging = parseConfig(readFileSync(configPath, 'utf8'));
  return auditStaging(production, staging, { template: mode === 'template' });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const mode = process.argv[2] === '--template' ? 'template'
    : process.argv[2] === '--candidate' ? 'candidate' : null;
  const path = process.argv[3];
  if (!mode || (mode === 'candidate' && (!path || process.argv.length !== 4)) ||
      (mode === 'template' && process.argv.length !== 3)) {
    process.stdout.write(JSON.stringify({ ok: false, errors: ['usage_template_or_candidate'] }) + '\n');
    process.exitCode = 2;
  } else {
    try {
      const result = checkFiles(mode, path);
      process.stdout.write(JSON.stringify({ mode, ...result }) + '\n');
      if (!result.ok) process.exitCode = 2;
    } catch {
      // Never echo potentially private path, parsing content or secret values.
      process.stdout.write(JSON.stringify({ mode, ok: false, errors: ['config_unreadable_or_invalid'] }) + '\n');
      process.exitCode = 2;
    }
  }
}
