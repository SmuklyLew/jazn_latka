# Jaźń v16.3.25.5.115.9 — Host finalization notification idempotency recovery

## Observed failure

A ChatGPT host finalization may first produce `regeneration_requested` and
later `accepted` for the *same* daemon request, after the response is corrected.
`SecureHostRuntimeGateway.note_host_finalization` previously claimed the
operation registry key `host-finalization:<daemon_request_id>` for both events.
The operation registry correctly rejects reusing an id with a differing payload
(`operation_id_payload_conflict`), so the second notification was not delivered
although the host's accepted visible response had already been committed.

## Change

- Preserve the canonical `daemon_request_id` and immutable turn bindings.
- Scope each operation identity to a canonical SHA-256 digest of the *entire*
  notification JSON, with sorted keys and stable separators. Identical
  retries retain one ID and are deduplicated by `OperationRegistry`; different
  finalization events no longer collide.
- Do not suppress `OperationConflictError`, relax payload integrity checks,
  replay the user's chat turn or create an alternative finalization authority.
- In case of a lost daemon ACK, persist `outcome_unknown`; the same event may
  be retried with the same key. The daemon validates turn, trace and contract
  bindings, and recognizes repeated accepted notifications.

## Validation

New regression tests cover regeneration → acceptance, identical notification
replay, lost-ACK recovery after gateway restart, distinct turns and distinct
attempt reasons. The existing persistent-runtime E2E CI matrix (Linux/Windows)
now collects the new tests on both `push` and `pull_request`.

Do not interpret a green unit test as proof of a live ChatGPT connector,
active daemon readiness or completion of the end-user's earlier turn.

## Design references

- AWS EC2 API idempotency, including rejecting the same client token with
  changed parameters: https://docs.aws.amazon.com/ec2/latest/devguide/ec2-api-idempotency.html
- Stripe API idempotent requests, including parameter matching and retries:
  https://docs.stripe.com/api/idempotent_requests
- Microsoft Azure Retry pattern, including ambiguity after lost responses:
  https://learn.microsoft.com/en-us/azure/architecture/patterns/retry
- GitHub Actions workflow and Python testing documentation:
  https://docs.github.com/en/actions/tutorials/build-and-test-code/python
