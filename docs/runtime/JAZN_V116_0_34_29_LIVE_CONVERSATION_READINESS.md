# Jaźń 16.3.25.5.116.0.34.29 — live conversation readiness

## Trigger and evidence

On the previous .28 patch, `CapabilityStatusHandler` correctly verified the daemon PID
and `daemon_instance_id` through `status_daemon`, but read `conversation_ready`
from the same `/live` response. The daemon's `/live` endpoint intentionally
exposes only liveness, process identity and heartbeat; it does not publish
`conversation_ready`. As a result, a healthy daemon could be reported with
`conversation_ready=not_verified`.

This is a diagnostic issue. It is not evidence that Jaźń failed to handle
a conversation. It does not authorize the host to claim a successful user turn.

## Implementation

For **explicit live-daemon diagnostic field requests only**:

1. `status_daemon(cfg)` attests PID, marker/root, process fingerprint,
   provenance, version, endpoint identity, fresh heartbeat; degraded clock
   trust alone is not a process failure.
2. Use the same canonical `status_payload(cfg.root, probe_endpoint=True)`
   as the CLI operator status path, including its independent `/ready` probe.
3. Require matching daemon PID, instance ID, release version, resolved runtime
   root, endpoint/marker identity, integrity and heartbeat across both reads.
   A restart between reads never licenses a cross-instance readiness claim.
4. Apply `apply_status_convergence` (the canonical optional-MEMORY policy
   reconciliation). Read `conversation_ready` from
   `capability_matrix.conversation_ready`, `runtime_ready` from
   `runtime_core_ready`, and `daemon_ready` from explicit
   `/ready.readiness_ok`. Do not conflate these independently scoped flags.
5. If any mandatory evidence is missing, mismatched, or malformed,
   return `not_verified` for readiness. A verified false is shown as
   `False`, not silently converted to `not_verified`.
6. No bootstrap, daemon restart, message replay, new mutable side effect or
   private MEMORY export is authorized by this diagnostic path.

The first status result is always an *identity* observation; the second is
a *readiness* observation. The handler only joins them on identical instance,
version, root and process identity.

## Tests

Active regression coverage is
`tests/test_daemon_result_transport_live_diagnostics.py`.
The previous test body has a byte-for-byte checkpoint in `tests/archive/`
before editing the active test.

Acceptance cases:
- valid status + `/ready` + canonical capability matrix => explicit True
- verified unready runtime => explicit False
- no `/ready` evidence, missing readiness fields => not_verified
- daemon changed instance between probes => not_verified
- broken readiness endpoint => not_verified
- unrelated package and ordinary health intents remain unchanged

## PowerShell / CI status boundary

Existing workflow `powershell-terminal-regressions` belongs to GitHub Actions.
A previously cancelled run (for example due to a later push and workflow
concurrency policy) is **not** a passing or failing test result. Check the
complete latest run on the current source commit, including its PowerShell
deterministic suite and clean checkout guard, before merging. This patch
does not disable, shorten or skip the Windows test matrix.

## Primary references

- Runtime's canonical source:
  `latka_jazn/cli_commands/diagnostics.py`,
  `latka_jazn/cli_commands/diagnostics_convergence.py`,
  `latka_jazn/runtime/capability_matrix.py`,
  `latka_jazn/core/runtime_daemon.py`.
- Kubernetes probes (liveness vs readiness):
  https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- Python mock isolation:
  https://docs.python.org/3.12/library/unittest.mock.html
- GitHub Actions workflow and job conclusions:
  https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
