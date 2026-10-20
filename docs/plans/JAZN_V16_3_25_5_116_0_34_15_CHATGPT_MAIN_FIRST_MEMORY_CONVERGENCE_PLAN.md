# Jaźń v16.3.25.5.116.0.34.15 — main-first ChatGPT bootstrap and MEMORY path convergence

Base: `master` commit `e8df20af8c5f41b377ceced9977394d7bf267b83`. This is a source-level patch on a new branch, not proof of ChatGPT executor access or a live accepted turn.

## Invariants

- ChatGPT Project loader is thin and unchanged. Remote callable MCP status is preferred; missing MCP does not gate a verified local SYSTEM. One primary executor probe and at most one independent alternative; no retries after pre-spawn ClientError.
- Standalone stdlib ZIP bootstrap does path/CRC/SHA checks; `materialized_operator_ready` requires `run.py`, `main.py`, `AGENTS.md`, `AGENTS.chatgpt.md`, version and provenance/integrity manifests. After bootstrap the host reads AGENTS and runbook and delegates to `run.py -> main.py`. Never reconstruct lifecycle by reading the entire source tree.
- `main.py` is sole dispatcher; no extra lifecycle/parser in `run.py`. Read-only diagnostics do not silently install packages; authorized activation retains verified local offline-wheelhouse behavior. The host can set `JAZN_DEPENDENCY_AUTOBOOTSTRAP=0` to forbid installs.
- MEMORY is a separate capability. Do not inspect the large provisional MEMORY ZIP. Document native, legacy, transactional and core operational SQLite paths and verify using existing resolvers. Core `optional` mode remains available; autobiographical claims require native unified readiness, continuity and provenance.
- No private data writes; no false role/identity/turn claims. Preserve `request_id` across poll and phase-2 finalization. No replay after an accepted submit.

## Implementation

1. Tighten earliest SYSTEM ZIP root-file contract; update existing synthetic ZIP fixtures and append-only snapshots of the four changed tests.
2. Restrict dependency auto-install entrypoint to activating commands only; add host operator guidance for disabling auto bootstrap when unapproved.
3. Add this plan and a code-linked, detailed memory DB/runbook document; reinforce AGENTS.chatgpt.md main-first boundary without duplicating runtime algorithms in the Project loader.
4. Add lightweight regression tests for structural ZIP contract, non-install diagnostics, MEMORY root paths, absent vs candidate MEMORY, unified database readiness, and correct CI glob; include isolated Python bootstrap in Pyright.
5. Correct GitHub Actions event path filter to match the new `chatgpt_host_pre_response_gate/` package and the new test. Bump version; do not manually forge package manifests.

## Verification and delivery

Expected in CI: compileall, Pyright 1.1.411, deterministic pytest, package profile checks, Windows/Linux host-spawn tests, GitHub Actions workflow filters, release metadata sync/idempotence. Separate real-host acceptance: ChatGPT host executor, verified archive materialization, daemon readiness, two different turns and exact phase-2 accepted finalization. If a CI pass belongs to a previous SHA, do not attribute it to this commit.

Sources: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt ; https://www.sqlite.org/pragma.html ; https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax .
