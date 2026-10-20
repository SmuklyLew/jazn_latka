# PR #392 Windows PowerShell clean-tree metadata correction — 16.3.25.5.116.0.34.18

The first PR catalog-race correction introduced `sync_contract_catalog.py --write` followed by `--check`, but the next step (`release_metadata_sync --write`) intentionally rejects a dirty working tree. The exact Python code at `latka_jazn/tools/_release_metadata_sync_impl.py:253-255` raises `release metadata synchronization requires a clean working tree` unless only allowed metadata is dirty.

The follow-up preserves the catalog write/check and now performs a **local-only generated-catalog commit in the disposable PR checkout**, before running release-metadata sync. It stages only `tools/jazn_tests_studio/test_contracts.json`, rejects unrelated dirty and staged paths, and never pushes to the GitHub branch. The normal clean checkout guard and full Windows tests remain.

CI incident: [run 39432486400](https://github.com/SmuklyLew/jazn_latka/actions/runs/39432486400) failed at `Materialize canonical PR metadata locally`. This fix is based on the actual clean-tree contract and mirrors the canonical `manifest_sync` order in `release-hardening.yml`.

Validation requires the fresh `powershell-terminal-regressions` run, `release-hardening`, Pyright, tests and a separate real-ChatGPT acceptance; no CI-only local commit implies actual ChatGPT execution.
