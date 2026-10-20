# PR #392 — Windows CI Test Studio catalog race correction

Version: 16.3.25.5.116.0.34.17

## Evidence

On source commit `3a68f28a2c6584097168d3f9728d7754fa189710`, GitHub Actions `powershell-terminal-regressions`, run [39431832032](https://github.com/SmuklyLew/jazn_latka/actions/runs/39431832032), failed at **Verify committed Test Studio catalog in PR checkout**. The exact diagnostic was `test contract catalog is stale; run python -X utf8 tools/jazn_tests_studio/sync_contract_catalog.py --write`. Other checks including Pyright, MCP, host-spawn MEMORY, dependency review and container smoke succeeded; that does not erase the Windows failure.

## Root cause and correction

The PR workflow validated the catalog in an ephemeral pull-request checkout with `--check` before regenerating the catalog for the specific checkout. It may race with the source branch `manifest_sync` job, which automatically commits catalog/metadata. A test merge checkout can also have its own generated catalog identity. The PowerShell regression workflow now runs the canonical catalog generator `--write` **locally** and then immediately `--check`, before release metadata materialization. It never commits or pushes from this PR workflow and restores generated files during the clean-tree guard.

Regression test: `tests/test_chatgpt_powershell_ci_catalog_order.py`. The full Windows PowerShell / GTK/Tk / health regression suite remains mandatory; no tests were skipped or weakened.

## Remaining acceptance

- Fresh CI must pass on the updated implementation commit; old CI results cannot be attributed to this patch.
- `manifest_sync` must produce canonical `PACKAGE_INTEGRITY_MANIFEST.json` and `SOURCE_PROVENANCE.json` (no manual hash edits).
- A release candidate still requires external ChatGPT visible-turn acceptance with real current-message MCP capability or a working local executor, as detailed in `JAZN_V16_3_25_5_116_0_34_16_CHATGPT_INGRESS_PR392_ACCEPTANCE.md`.
- Do not merge without explicit user approval.
