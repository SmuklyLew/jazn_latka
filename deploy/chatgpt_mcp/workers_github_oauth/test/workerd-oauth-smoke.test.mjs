// Real workerd/Miniflare integration smoke; no Cloudflare deploy or GitHub calls.
// Wrangler bundles the exact Worker source before Miniflare dispatchFetch tests.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Miniflare } from 'miniflare'; // pinned as a Wrangler transitive dependency in package-lock
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const issuer = 'https://jazn-auth-staging.jazn-lakta.workers.dev';
const resource = 'https://jazn-runtime-staging.jazn-lakta.workers.dev/mcp';

function jsFiles(directory) {
  const paths = [];
  for (const name of readdirSync(directory)) {
    const full = join(directory, name);
    if (statSync(full).isDirectory()) paths.push(...jsFiles(full));
    else if (/\.(mjs|js)$/.test(name)) paths.push(full);
  }
  return paths;
}

function bundledWorker(directory) {
  const outdir = join(directory, 'bundle');
  const cli = resolve(root, 'node_modules/wrangler/bin/wrangler.js');
  const result = spawnSync(process.execPath,
    [cli, 'deploy', '--dry-run', '--config', resolve(root, 'wrangler.staging.example.jsonc'), '--outdir', outdir],
    {cwd:root, encoding:'utf8', timeout:90000,
      env:{...process.env, WRANGLER_SEND_METRICS:'false'}});
  assert.equal(result.status, 0, (result.stderr || '') + (result.stdout || ''));
  const candidates = jsFiles(outdir).filter(x => !x.endsWith('.map'));
  assert.ok(candidates.length > 0, 'Wrangler emitted no runnable bundle');
  return candidates.find(x => /index\.(js|mjs)$/.test(x)) || candidates[0];
}

function worker(bundle, extraBindings = {}) {
  return new Miniflare({
    modules:[{type:'ESModule',path:bundle}],
    compatibilityDate:'2026-10-18',
    compatibilityFlags:['global_fetch_strictly_public'],
    kvNamespaces:['OAUTH_KV'],
    bindings:{
      JAZN_AUTH_ENVIRONMENT:'staging',
      JAZN_OAUTH_ISSUER_URL:issuer,
      JAZN_OAUTH_RESOURCE_URL:resource,
      ...extraBindings,
    },
  });
}

test('workerd enforces fail-closed OAuth and introspection with isolated KV', {timeout:120000}, async () => {
  const tmp = mkdtempSync(join(tmpdir(), 'jazn-staging-workerd-'));
  let mf;
  try {
    const bundle = bundledWorker(tmp);
    mf = worker(bundle);
    await mf.ready;
    let response = await mf.dispatchFetch(issuer + '/healthz');
    assert.equal(response.status, 503);
    assert.equal((await response.json()).deployment_configured, false);
    response = await mf.dispatchFetch(issuer + '/oauth/introspect', {method:'POST'});
    assert.equal(response.status, 503);
    await mf.dispose();
    mf = undefined;

    const fakeId = 'fake-resource-server';
    const fakeSecret = 'fake-introspection-secret-different-from-github';
    mf = worker(bundle, {
      GITHUB_CLIENT_ID:'fake-github-app',
      GITHUB_CLIENT_SECRET:'fake-github-secret',
      JAZN_ALLOWED_GITHUB_LOGIN:'test-operator',
      JAZN_ALLOWED_GITHUB_USER_ID:'12345',
      JAZN_INTROSPECTION_CLIENT_ID:fakeId,
      JAZN_INTROSPECTION_CLIENT_SECRET:fakeSecret,
    });
    await mf.ready;
    response = await mf.dispatchFetch(issuer + '/healthz');
    assert.equal(response.status, 200);
    assert.equal((await response.json()).end_to_end_verified, false);
    response = await mf.dispatchFetch(issuer + '/oauth/introspect', {method:'POST'});
    assert.equal(response.status, 401);
    response = await mf.dispatchFetch(issuer + '/oauth/introspect', {
      method:'POST',
      headers:{
        'authorization':'Basic ' + Buffer.from(fakeId + ':invalid').toString('base64'),
        'content-type':'application/x-www-form-urlencoded',
      },
      body:'token=fake',
    });
    assert.equal(response.status, 401);
    response = await mf.dispatchFetch(issuer + '/oauth/introspect', {
      method:'POST',
      headers:{
        'authorization':'Basic ' + Buffer.from(fakeId + ':' + fakeSecret).toString('base64'),
        'content-type':'application/x-www-form-urlencoded',
      },
      body:'token=invalid-test-token',
    });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {active:false});
  } finally {
    if (mf) await mf.dispose();
    rmSync(tmp, {recursive:true,force:true});
  }
});
