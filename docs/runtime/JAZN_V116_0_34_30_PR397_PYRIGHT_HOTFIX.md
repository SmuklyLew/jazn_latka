# Jaźń v16.3.25.5.116.0.34.30 — post-merge Pyright regression

## Origin

PR #397 was merged at commit `60f839eab50dd9a94c9bc123c0049eb24b0cba51`
while the Pyright gate for the .29 live-readiness regression tests was failing.
The fixes committed later on the previous fix branch were not part of the merge.

The failing run `39536981720` (Pyright 1.1.411, 1259 files analyzed) reported
two `reportArgumentType` errors in
`tests/test_daemon_result_transport_live_diagnostics.py`:
- line 64: assigning a bool to an inferred string-valued readiness mapping
- line 77: assigning a bool to an inferred mapping-valued result

## Changes

- Preserve the merged test bytes in `tests/archive/` before editing them.
- Explicitly type `checked_daemon`, `readiness` and `result` as
  `dict[str, Any]`, so mixed readiness fields are valid without changing
  test semantics or weakening Pyright.
- No runtime, MCP transport, MEMORY, JavaScript, daemon lifecycle or
  `conversation_ready` policy changes.
- Synchronize the distribution, startup and deployment version to `.30`.
- Let the canonical release workflow regenerate the manifest and source
  provenance; do not create hashes manually.

## Acceptance

- [ ] Pyright active tree reports 0 errors
- [ ] New regression test and full deterministic test suites pass
- [ ] Full PowerShell workflow succeeds; `in_progress` and `cancelled`
      are not equivalent to success
- [ ] `release-hardening`, MCP and package cleanroom pass
- [ ] Canonical manifest and Test Studio catalog synchronization complete

Do not merge while these gates are incomplete.

## References

- https://github.com/SmuklyLew/jazn_latka/pull/397
- https://github.com/SmuklyLew/jazn_latka/actions/runs/39536981720
- https://microsoft.github.io/pyright/
- https://docs.python.org/3/library/typing.html
- https://docs.github.com/en/pull-requests/reference/status-checks
