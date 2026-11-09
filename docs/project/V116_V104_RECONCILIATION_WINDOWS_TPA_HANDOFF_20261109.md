# Jaźń V116 — V104/V115 reconciliation and Windows TPA handoff

STATUS: IMPLEMENTATION CHECKPOINT. Full CI and Windows operator acceptance have NOT been run. DO NOT MERGE.

Source branch: audit/v114-v104-gap-reconciliation-tpa-20261109
Prior verified source HEAD (V115): a9a80c8af4c22abca26cad6abc2ac52e94d9ba3c
V104 source: b98ff9599e2f7d6f75d4528d3baa0e935993735c
Version: 16.3.25.5.116.0.34.94.6.116

## Reconciliation decisions

- PORT: HTML memory importer now uses central SQLite connections for writable staging, maintenance, and source backup. Forced WAL mode removed.
- PORT: Unified memory rebuild now uses central read-only/writable SQLite connections with the existing closing connection factory.
- SUPERSEDED: central runtime_sqlite.py already had the V104 policy for vulnerable WAL and existing-WAL refusal.
- PORT: feminine first-person guidance for rejected host finalization, preserving original quoted text.
- PORT: supervisor inactivity confirmed only with explicit inactive, dead PID, identity not alive, and exact schema.
- PORT: bounded 127.0.0.1 Ollama API base for live TPA CLI and probes. Nondefault-port model discovery from the Qt picker still requires operator verification.
- PORT: Polish time question variants, legacy route, protected intent.
- PORT/ADAPT: Dependency Studio CLI supports explicit project or managed layout. Project layout rejects environmental and explicit root overrides; managed environments are separate from ROOT/.venv.
- PORT: Test Studio generated catalog version field recognized in version consistency audit.
- DEFER pending real caller: V104 SafePathRoot class was not copied without evidence of a needed batch consumer. Do not merge all V104 files wholesale.

Official references: https://www.sqlite.org/wal.html ; https://docs.python.org/3.14/library/sqlite3.html ; https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows

## Canonical TPA integration

Keep the existing 22 IDs, TPARunner and RunStore; no duplicate runner.

Existing cases now include added regressions:
- studio-memory, studio-memory-rebuild, studio-chat-import: tests/test_memory_sqlite_v116_ingest_policy.py
- studio-dependencies: tests/test_dependency_studio_layout_contract_v116.py
- studio-start: tests/test_jss_supervisor_inactive_evidence_v116.py
- ollama-two-turns: tests/test_tpa_local_ollama_endpoint.py and tests/test_runtime_time_routing.py
- chat-resume: existing tests/test_runtime_feminine_voice_gate.py

No V116 operator receipt has been verified. Every scenario needs its own current-SHA source evidence, TXT/JSON/JUnit, cleanup result and full-gate operator receipt. A regression PASS is NOT a full-gate PASS. Missing prerequisites remain BLOCKED, not PASS. Preserve old evidence append-only.

Use an isolated Windows checkout / verified release candidate with Python 3.14 and own ports. Select the candidate branch, not origin/master. Do not touch live MEMORY, daemon or production workspace. For synthetic test MEMORY only. Begin with the memory, dependency, startup, Ollama and chat-resume cases; then run the rest of the canonical 22 cases including offline VM and native DPI.

## Canonical artifact synchronization order for Windows checkout

1. Verify branch, clean worktree and pull with fast-forward only.
2. Run: py -3.14 -X utf8 tools/jazn_tests_studio/sync_contract_catalog.py --write
3. Run: py -3.14 -X utf8 tools/jazn_tests_studio/sync_contract_catalog.py --check
4. Stage ONLY tools/jazn_tests_studio/test_contracts.json; diff --cached --check; commit only if actually changed.
5. On clean worktree run: py -3.14 -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json
6. Run the same command with --check instead of --write. Require synchronized=true, manifest_matches=true, provenance_matches=true.
7. Stage ONLY PACKAGE_INTEGRITY_MANIFEST.json and SOURCE_PROVENANCE.json; commit if changed; check again; push same branch without force.
8. Verify remote SHA and clean worktree. Run targeted tests and all required CI against the exact final source SHA.
9. After completed CI and real operator receipts for all 22 cases, prepare a final PR to master. Do not merge automatically.

No manually edited manifest/provenance. If source or tests change later, regenerate catalog -> code/catalog commit -> metadata sync -> metadata-only commit in the same order.

## Checkpoint truth

V115 Windows targeted MCP/SQLite regressions (pre-V116): 45 PASS, 1 SKIPPED. Not a V116 result.
V116 new regressions: NOT_RUN / NOT_VERIFIED.
Test Studio generated catalog: PENDING.
V116 release metadata: PENDING.
Full CI exact final SHA: NOT_RUN / NOT_VERIFIED.
All 22 Windows TPA full gates: NOT_RUN / NOT_VERIFIED.
Final PR: NOT CREATED.
