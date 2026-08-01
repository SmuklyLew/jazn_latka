# ChatGPT host finalization protocol rollout

1. Merge only after compilation, regression tests, doctor, package smoke, and metadata synchronization succeed.
2. Build a new versioned system package; do not overwrite an active runtime in place.
3. Stop the old daemon, materialize the new package, verify its manifest, and start the new daemon.
4. Confirm authenticated live status, endpoint reachability, heartbeat freshness, runtime-write readiness, and transactional memory readiness.
5. Run one `display_exact` turn and one `generate_then_finalize` turn through the private MCP tools.
6. Verify that the intermediate result is not displayed, the final result is exact, and a second use of the continuation token is rejected.
7. Inspect pending-store counts; no unexpected `claimed` records should remain. Expired records may be retained for audit according to operator policy.
8. Keep the previous versioned runtime as rollback material until the new runtime has completed the operator acceptance checks.

Rollback means stopping the new daemon and reactivating the previous verified runtime root. Do not copy mutable pending-token state between runtime workspaces.
