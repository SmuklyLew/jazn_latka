# Jaźń v16.3.25.5.50 — runtime reload and daemon lifecycle hotfix

## Problem

The active marker was resolved before an explicitly requested new runtime root. As a result, `start`/legacy `restart` could restart the old runtime instead of switching to a newly materialized release. `restart` was also a non-transactional loose stop/start sequence. Separately, runtime-bootstrap did not accept the pack generator's current `jazn_pack_generator_package/v2` sidecar. PID liveness was not strong enough to distinguish a stale marker from PID reuse when the endpoint was unavailable.

## Package transport convergence

`run.py runtime-bootstrap` now accepts the generator's current `jazn_pack_generator_package/v2` without weakening the mature package extractor. A bounded v50 adapter verifies logical identity, size and SHA from `archive`, split volumes from `split.parts`, and profile from `content`, then copies the verified bytes into a private compatibility transport consumed by the existing `jazn_package_set/v3` extractor. The real host active marker is isolated during materialization and is changed only by the transactional lifecycle handoff. Host-renamed generator sidecars retain their declared logical archive identity.

## Process identity

New v50 daemon markers carry `process_fingerprint` through the lifecycle hotfix installed before the daemon process imports the legacy runtime module. PID remains a compatibility field, not a durable identity.

- Linux/POSIX with `/proc`: PID + boot id + process `starttime`;
- Windows: PID + creation FILETIME from `GetProcessTimes`;
- all platforms: `daemon_instance_id` + runtime root remains the live endpoint identity.

A live numeric PID whose stable fingerprint differs from the marker is classified as PID reuse and cannot promote an unreachable endpoint to active/degraded runtime state. Legacy markers without fingerprints retain bounded compatibility.

## Transactional lifecycle

`latka_jazn/core/runtime_lifecycle.py` owns restart/reload, while `runtime_daemon_lifecycle_hotfix.py` installs bounded process-identity/start-stop wrappers before both CLI and daemon subprocess execution:

1. verify target start file, package integrity and provenance;
2. acquire canonical runtime workspace lifecycle lock;
3. capture exact previous marker and current live identity;
4. stop only a confirmed current daemon;
5. require observed process exit;
6. clear the stopped old marker, then publish the explicit target marker;
7. start the target using the target root's own version identity;
8. verify endpoint/root/instance/heartbeat;
9. commit the handoff;
10. on target failure, restore exact previous marker bytes and restart the previous root if it had been active.

Same-root `restart` and cross-root `reload --target-root` use this one transaction. `runtime-bootstrap` uses it after extraction instead of publishing a new active marker while an old daemon is still alive.

## Process cleanup and deadlines

Startup and shutdown wait budgets use `time.monotonic()`. A spawned daemon that fails readiness is explicitly terminated and, if necessary, killed after a bounded grace period. A PID file is removed only when its recorded PID belongs to the instance being cleaned up. The daemon also removes its owned PID file during normal shutdown.

## Validation

Local automated checks passed for package-v2 loading, process fingerprint helpers, transactional stop/handoff/rollback, CLI routing, daemon identity, existing persistent lifecycle contracts, code health and single-source versioning. `compileall` passed.

Two isolated live tests were also executed on non-production ports and workspaces:

- verified runtime root A -> transactional handoff -> verified root B -> canonical stop;
- running verified runtime -> real uploaded v49 generator-v2 system ZIP -> runtime-bootstrap -> newly installed active root -> canonical stop.

Both live handoffs reached `active_trusted` with a new PID and `daemon_instance_id`, correct root and fresh heartbeat.

The unpacked development worktree has no `.git`, so package-staging tests that require synchronized release metadata correctly fail until GitHub `manifest_sync` updates the two canonical metadata files. These files are not hand-edited by this hotfix.

## External basis

The implementation follows OS/runtime contracts rather than assuming PID uniqueness forever: Windows documents that process identifiers are valid for a process lifetime and can be reused, `GetProcessTimes` exposes process creation time, Linux `/proc/<pid>/stat` exposes process starttime, and Python documents monotonic clocks and explicit child cleanup after subprocess timeouts.

## Verified references

- Microsoft Learn — Process Handles and Identifiers: https://learn.microsoft.com/en-us/windows/win32/procthread/process-handles-and-identifiers
- Microsoft Learn — GetProcessTimes: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes
- Linux man-pages — `/proc/<pid>/stat`, field 22 `starttime`: https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html
- Python documentation — `time.monotonic()`: https://docs.python.org/3/library/time.html#time.monotonic
- Python documentation — subprocess timeout cleanup: https://docs.python.org/3/library/subprocess.html#subprocess.Popen.communicate
