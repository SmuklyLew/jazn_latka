# Jaźń v16.3.25.5.116.0.2 — repair of strict Pyright release gates

Date: 2026-10-13. Starting point: `update/v16.3.25.5.116-runtime-ingress-security-convergence` at `5f4f3e3fce37744c7dbc0f35e46c31f6ffe41048`.
Integration PR: #359; predecessor: #358. This is a **release-gate repair**, not completion of all v116 protocol/Tasks features.

## Source of failure

The preceding GitHub Actions run `38344086242` reported **6 errors and 1 warning** under Pyright 1.1.411; the Ubuntu static type audit in release-hardening `38344086200` failed for the same reason.

Errors:
- `latka_jazn/mcp/http_tasks_bridge.py`: an arbitrary backend response `object | dict[str, Any]` passed to the JSON sender.
- `tests/test_mcp_http_resources.py`: nullable task record dereferenced.
- `tests/test_mcp_modern_protocol.py`: mocked `get` lacked the new keyword-only owner parameters.
- `tests/test_mcp_task_principal_isolation.py`: two nullable records dereferenced.
- `tests/test_mcp_task_protocol_authorization.py`: nullable task record dereferenced.

Warning:
- `latka_jazn/core/chatgpt_host_pre_response_gate/_core.py`: dynamic `__all__` comprehension incompatible with strict Pyright exports analysis.

## Corrections

- Fail closed if a non-dictionary backend response would reach `_send_json`.
- Replace dynamic exports with a static list retaining every previously exported binding.
- Narrow optional task records with explicit `is not None` assertions, without weakening tests.
- Update the test mock signature to match `McpTaskResumeAdapter.get`.
- Bump `latka_jazn/version.py` to `16.3.25.5.116.0.2` and synchronize version-bound startup/deployment contracts and active tests.
- Preserve exact pre-change test bytes in `tests/archive/v16.3.25.5.116.0.1-pyright-gate-source/`.
- Regenerate the Test Studio contract catalog with `sync_contract_catalog.py --write`; `--check` passes for 2267 active definitions.
- Generate `SOURCE_PROVENANCE.json` and `PACKAGE_INTEGRITY_MANIFEST.json` only through the canonical `release-hardening / manifest_sync` CI workflow, never manual hashes.

## Verified gates

- Local selected regression suites: **58 passed, 1 skipped**.
- Local active Python source compile: **1145 files compiled**.
- GitHub Actions `pyright-active-tree-audit` run `38348328684`: **1187 files analyzed, 0 errors, 0 warnings**.
- GitHub Actions `Stable test contracts` run `38348328416`: success.
- GitHub Actions `javascript-node24-contract` run `38348328587`: success.
- GitHub Actions `MCP container build and Compose deployment smoke` run `38348328515`: success.
- GitHub Actions `host-spawn-memory-convergence` run `38348328456`: success.
- Canonical `manifest_sync` job: success, `manifest_matches=true`, source provenance tied to the immutable code commit.
- Ubuntu/Windows full release-hardening, official MCP conformance, and live ChatGPT connector acceptance remain separate gates; do not infer completion from this report.

## Further release blockers (unchanged)

Implement and verify task `inputResponses` ACK/idempotency, full MCP Tasks conformance, final release package tests and a real two-turn ChatGPT connector E2E. No private MEMORY or live runtime files have been edited.

Sources: GitHub Actions job logs, repository `AGENTS.codex.md`, and Pyright type narrowing guidance: https://github.com/microsoft/pyright/blob/main/docs/type-concepts-advanced.md
