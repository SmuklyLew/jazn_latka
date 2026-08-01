# Operator verification checklist

- [ ] CI compilation passed.
- [ ] Non-live pytest suite passed.
- [ ] Doctor passed with live endpoint probing.
- [ ] System package smoke passed.
- [ ] Manifest/provenance synchronization completed through the canonical workflow.
- [ ] New versioned runtime was materialized without overwriting the previous runtime.
- [ ] Authenticated daemon status is reachable and heartbeat is fresh.
- [ ] Runtime-write and transactional-memory readiness are both confirmed.
- [ ] A direct `display_exact` turn returned exact runtime text.
- [ ] A `generate_then_finalize` turn returned no intermediate visible answer.
- [ ] Finalization returned `display_exact` and consumed the token.
- [ ] Reusing the consumed token was rejected.
- [ ] Pending/claimed store contains no unexpected abandoned requests.
- [ ] Previous verified runtime remains available for rollback.
