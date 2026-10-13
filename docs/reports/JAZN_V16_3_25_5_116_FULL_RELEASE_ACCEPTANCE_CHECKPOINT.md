# Jaźń v16.3.25.5.116 — full functional release acceptance checkpoint

**Status: BLOCKED / NO MERGE / NO FINAL SYSTEM ZIP.**
**Scope owner:** one branch `release/v16.3.25.5.116-full-functional-convergence`.
**Starting baseline:** `fc5bff807e7229e7b90176ad50212062c31e6b45` (v116.0.4).
**WIP implementation version:** `16.3.25.5.116.0.5`.

## Implemented in this checkpoint

- Official frozen MCP 2026-07-28 server conformance is now a required push/PR gate on Linux and Windows, not an operator-only diagnostic.
- Claimed Tasks acceptance is a separate required job step; optional extensions must be gated by project policy even when upstream leaves them unscored.
- Both optional cloud-memory dependency profiles are verified against real PyNaCl / PostgreSQL / S3 client dependencies on Linux and Windows, not a skipped import.
- Public daemon PID liveness probe extracted to `latka_jazn/core/daemon_process_control.py`; the canonical runtime module continues exposing `pid_is_alive` as its compatibility facade.
- Conformance logs now publish through nonhidden CI artifacts rather than silently disappearing.
- Release identity advanced to 16.3.25.5.116.0.5; five previous version-bound active tests archived byte-for-byte before updating.

## Verified new evidence

From GitHub Actions `38364207985`, archived protocol evidence `mcp-conformance-ubuntu-latest`:
- Core + extensions: **116 passed, 56 failed** across the 50 reported scenarios.
- The extension scenarios are currently unscored upstream: **13 run, 11 failing**. These cannot be silently treated as PASS in Jaźń.
- Production server lacks the conformance harness's synthetic `greet`, `slow_compute`, `test_input_required_result_*` and other fixture names. Do NOT add those artificial tools to the public Jaźń API. Implement a dedicated isolated test-only fixture exercising Jaźń's protocol layer alongside genuine production-app contract tests.
- Official conformance `requirements 2026-07-28` has failed on Linux and Windows. Those are blockers, not test flakes.

From GitHub Actions `38364208088`: **4/4** optional memory-cloud jobs passed on Linux/Windows for `memory-cloud` and `memory-cloud-server`.

## Remaining mandatory functional gates

1. Runtime-owned `TaskInputGateway`: actual daemon consumer and continuation for existing request, durable ACK without original-message replay, idempotent input response handling, exact request/turn/trace lineage, denial on cancellation and restart.
2. Protocol: isolated conformance fixture for all required synthetic scenarios **plus** full direct tests of Jaźń's actual production MCP tools, stateless discovery, auth, resources, cache and advertised Tasks extension.
3. Extract and wire coordinator capabilities through narrow runtime ports without giving each component the whole `JaznEngine`.
4. Continue decomposing `runtime_daemon.py` (models, durable store, process control, heartbeat, security, handler, finalization gate) with facade parity.
5. Complete source/branch-sensitive `compileall`, Pyright 0 errors/0 warnings, deterministic pytest, full Windows/Linux E2E, clean package, and canonical manifest/provenance synchronization on the final SHA.
6. Real authenticated remote MCP from ChatGPT: four callable `jazn_*` tools and **two consecutive** accepted `display_exact` turns. This host currently exposes no callable four-tool remote runtime; absence cannot be replaced with a mocked test.
7. Only after all checks are green: merge **one** final PR to master, then build SYSTEM ZIP from the released master's exact verified SHA and produce SHA-256/provenance and cross-platform acceptance evidence.

## Safety

No modification to private MEMORY, no secret inclusion, no broad Pyright suppression, no skipped protocol failures, no merge until evidence supports it.

Upstream references:
- https://modelcontextprotocol.io/specification/2026-07-28
- https://github.com/modelcontextprotocol/ext-tasks/blob/main/specification/2026-07-28/tasks.md
- https://github.com/modelcontextprotocol/conformance
- https://github.com/modelcontextprotocol/python-sdk/blob/main/ROADMAP.md
