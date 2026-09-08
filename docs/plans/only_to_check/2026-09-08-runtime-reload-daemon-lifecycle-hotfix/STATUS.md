# STATUS — v16.3.25.5.50 runtime reload + daemon lifecycle hotfix

State: implementation-complete / local-validation-complete / awaiting GitHub manifest_sync + CI.

Implemented:
- current pack-generator `jazn_pack_generator_package/v2` accepted by runtime-bootstrap;
- direct ZIP, split ZIP and host-renamed sidecar support;
- process fingerprint bound to PID for new daemon markers;
- monotonic startup/stop deadlines and owned child cleanup after failed readiness;
- owned PID-file cleanup on shutdown;
- `restart` moved to transactional lifecycle;
- new `reload --target-root` cross-version handoff;
- target preflight, lifecycle lock, marker transition and rollback;
- runtime-bootstrap reuses the same handoff after materialization;
- expected daemon version is read from the target root, enabling rollback to an older verified runtime.

Local evidence:
- critical lifecycle/bootstrap/status/operator suite: 73/73 PASS;
- persistent lifecycle/bootstrap/recovery regression suite: 91/91 PASS;
- code-health/version/release-contract suite: 63/63 PASS;
- broad daemon/bootstrap/lifecycle/recovery selection: 142/142 PASS;
- compileall PASS;
- `run.py doctor --json`: rc=0, `ok=true`, `installation_ok=true` (activation prerequisites remain environment-dependent because the isolated system worktree has no attached transactional memory);
- live isolated root A -> root B handoff PASS (`active_trusted`, new PID, new `daemon_instance_id`, correct root, fresh heartbeat);
- live isolated running runtime -> real uploaded generator-v2 ZIP -> runtime-bootstrap -> new active root PASS;
- live tests ended with canonical stop; the A -> B E2E explicitly confirmed `process_exit_observed=true`.

Release metadata are intentionally not hand-edited. GitHub `release-hardening/manifest_sync` must synchronize `PACKAGE_INTEGRITY_MANIFEST.json` and `SOURCE_PROVENANCE.json` after branch push.
