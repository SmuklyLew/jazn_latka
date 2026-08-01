# Acceptance criteria

The change is acceptable only when all of the following are true:

- the private gateway authenticates every daemon call;
- `generate_then_finalize` is returned as a non-visible intermediate success;
- the finalizer accepts no host-controlled identity or timestamp fields;
- finalization consumes exactly one non-expired pending request;
- a consumed or expired token is rejected;
- only `display_exact` returns visible Łatka text;
- a valid phase-one turn is not counted as a runtime failure;
- live memory readiness is reported from verified daemon data;
- the offline snapshot is not used as activation proof;
- compilation, non-live tests, doctor, package smoke, diff checks, and canonical metadata synchronization pass.

Any failed item blocks merge. Undiscovered defects remain possible; this checklist certifies only the reproduced and covered defect set.
