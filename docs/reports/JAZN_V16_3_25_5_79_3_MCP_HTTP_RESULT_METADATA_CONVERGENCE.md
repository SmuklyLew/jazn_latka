# Jaźń v16.3.25.5.79.3 — MCP HTTP result metadata convergence

## Failure observed

`release-hardening / verify (ubuntu-latest)` reached the full deterministic
suite with compile, Pyright, Pack Generator freshness, semantic route audit and
cognitive architecture audit already green. Exactly one test failed:
`test_public_status_is_redacted_even_when_backend_status_is_private`.

The assertion required `result.meta is None`, but the current MCP Python SDK
serving the 2026-07-28 revision stamps
`io.modelcontextprotocol/serverInfo` into response `_meta`.

## Fix

The active regression now preserves the actual security contract:

- private backend metadata such as `private_operator_detail` must not cross the
  public gateway;
- runtime-root and daemon internals remain absent from structured public status;
- protocol-owned MCP `io.modelcontextprotocol/serverInfo` is permitted and
  verified as the only public metadata key;
- the public server identity must identify `jazn-runtime`.

Production gateway code is unchanged because it was already correctly redacting
backend-private metadata; only the stale test expectation changed.

The v79.2 active test is preserved byte-for-byte in
`tests/archive/v16.3.25.5.79.2-host-executor-epoch-recovery-ci-convergence/`.

## External contract

MCP 2026-07-28 says servers SHOULD identify themselves in each result's
`_meta['io.modelcontextprotocol/serverInfo']`. The official Python SDK v2
implements that stamping automatically.
