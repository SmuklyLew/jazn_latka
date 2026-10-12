# Plan — v16.3.25.5.50 runtime reload + daemon lifecycle hotfix

## Observed failures

1. `start`/`restart` resolve the host-level active marker before honoring the explicitly supplied root, so a new operator can restart the old runtime instead of switching to the requested root.
2. `restart` is a loose `stop` + `start`; it does not stop on stop failure and has no atomic marker switch or rollback.
3. `runtime-bootstrap` rejects the generator's current `jazn_pack_generator_package/v2` sidecar although the generator and release packages use that schema.
4. PID liveness alone can be fooled by PID reuse after process exit when the endpoint is unavailable.
5. Startup deadlines use wall time and failed startup can leave a just-spawned process behind.
6. The legacy daemon PID file is not removed on an owned clean shutdown.

## Target lifecycle

`verify target → acquire lifecycle lock → capture current identity/marker → stop verified current instance → verify exact process exit → atomically activate target marker → start target → verify endpoint/root/instance/heartbeat → commit; otherwise restore marker + restart previous root`

Same-root `restart` uses the same transaction. Cross-version `reload --target-root ...` performs the handoff. `runtime-bootstrap` uses the transaction after materializing and validating a package.

## Process identity

PID is retained for compatibility but is not a durable identity. The daemon marker records a process fingerprint:

- POSIX/Linux: PID + boot id (when available) + `/proc/<pid>/stat` starttime;
- Windows: PID + creation FILETIME from `GetProcessTimes`;
- all platforms: existing `daemon_instance_id` remains the runtime launch identity.

A stale marker whose PID is alive but fingerprint differs is not allowed to become `active_degraded`. Endpoint `daemon_instance_id + root` remains authoritative when reachable.

## Package compatibility

The canonical v50 `runtime-bootstrap` accepts both legacy `jazn_package_set/v1..v3` and current generator `jazn_pack_generator_package/v2`. A bounded compatibility adapter verifies the generator-v2 transport and materializes a private legacy-shaped transport for the mature extractor; it derives:

- package identity from `archive.logical_filename`;
- full archive size/SHA from `archive`;
- split parts from `split.parts` when split;
- direct single-ZIP transport when not split;
- profile from `content` (`system`, `memory`, `system+memory`).

Memory-only packages remain forbidden as system `active_root`.

## Validation

- focused package-v2 loader tests;
- process fingerprint/PID reuse tests;
- start-failure cleanup + PID-file ownership tests;
- transactional reload success/stop-failure/start-failure rollback/same-root restart tests;
- runtime-bootstrap handoff integration in isolated workspace;
- existing daemon-instance and lifecycle regression suites;
- `compileall`, code-health/static checks, segmented pytest, `doctor`, and package-smoke where the environment permits.

Release metadata are never hand-edited; the repository `manifest_sync` workflow owns their synchronized commit after push.
