# Jaźń — Serce Systemu: checkpoint 2 (.94.2)

2026-10-26. Development checkpoint, not release-ready. Continue Draft PR #423; no merge.

## Starting checkpoint

- Worktree: `D:\.AI\jazn_branches\jazn-v11603494-system-studio-diagnostics`.
- Branch: `fix/jazn-v11603494-system-studio-diagnostics-20261026`.
- Previous local/remote checkpoint SHA: `149f575405978b37050dc591c4cd466365ac62fb`.
- .94.1 independent metadata check returned synchronized=true for 3411 files. Remote SHA matched after push.

## Implemented

- Splash with actual initialization stage; asynchronous first-run wizard A/B/C. Canonical dependency profile/pyproject checks, selected interpreter, virtual environment, package integrity and root configuration. Optional program discovery and actual connection probes. Completion requires positive mandatory checks, unchanged interpreter/dependency scope and explicit save consent.
- Default Violet Night, better native label surfaces, responsive service table with real actions. PID, endpoint and readiness remain distinct. Starting a Cloudflare tunnel requires operator confirmation.
- Dockable/floating/reopenable operator panel: grouped/filterable problems with timestamps, redacted output source/search/export, three actual job consoles and an explicit external Windows TTY launch. The embedded consoles do not claim PTY/ConPTY capabilities.
- Searchable navigation/settings, settings categories/default draft/dirty-state guard, persistent bounded primitive JSON layout, sidebar placement and menu recovery.
- Native Models, MCP/ChatGPT and Developer pages using existing commands; status, Git, public evidence, reports and existing test/configuration workspaces. Tools show file availability. Main CLI/TTY and all compatibility launchers remain.
- Read deduplication now checks exact command/settings fingerprint; a changed endpoint/model cannot adopt an earlier observation. Mutations retain strict exclusion.
- Package profiles include launchers plus actual tools; existing Studio CI now includes .94 and new regressions. External Action pins unchanged. Startup/deployment release identities aligned.
- Windows type audit exposed an existing direct POSIX `os.killpg` reference. It now checks that capability only in the existing POSIX shutdown branch; Windows process ownership and termination behavior are unchanged.

## Evidence before source checkpoint

- Final focused Studio + Start Studio + startup/doc contracts: **241 PASS, 1 SKIPPED**, 20.72 s.
- Studio type gate: 0 errors/warnings. Full active-tree Pyright: **1364 files, 0 errors, 0 warnings**, 23.568 s (before final request-binding/splash additions; full final rerun remains required).
- Active-tree compileall (immutable archive excluded; external cache): PASS. diff --check: PASS.
- Node 24.20.0: npm ci from existing lock with scripts/audit/funding disabled, syntax check, ESM probe and canonical capability check: PASS. Actions audit: 22 workflows, no findings.
- First full regression attempt: **84 FAIL, 3090 PASS, 23 SKIPPED**, 268.55 s. Preserve `full.log` and `full.xml`. A shared outer `JAZN_MEMORY_ROOT` contaminated independent memory fixtures; startup/deployment versions were stale before alignment. The run also hit an existing Windows pytest temp cleanup permission error. These failures are not erased or represented as passes. Rerun with no inherited Jaźń bindings and a fresh TEMP/TMP is required.
- Canonical test catalog generated with sync_contract_catalog.py; no historical snapshot edited. Existing .94.1 diagnostics test fixture now reserves a real signed read to exercise batch reuse. Snapshot verified byte-for-byte against the approved Git blob. The snapshot was captured after adding new test cases due to an execution-order oversight, before revising the fixture; no original bytes were lost.
- Actual native Qt platform `windows`, Python 3.14.4: captured Pulpit, Usługi, Ustawienia, Developer, Terminal/Konsole, Kreator and 860x580 services view. Screenshots are actual widgets, not mockups. Initial captures exposed label contrast/layout issues, which were corrected and recaptured.
- Actual Ollama `/api/tags`: `gemma3:latest` present, selected_model_present=true. Generation_verified=false; no live turn inferred.

## Artifact locations and remaining work

External evidence root: `D:\.AI\codex_tasks\heart-system-20261026`. Native screenshots: `native-screenshots-v2`, with capture-report.json. Raw temporary logs and synthetic memory are never committed.

Remaining gates: full clean-environment regression, final-source type/compile, metadata write+independent check, doctor/package-smoke, release packaging/cleanroom, native wizard completion/save/reopen and real DPI scaling, isolated Start/Stop/Restart/no-duplicate daemon, real model generation/accepted turn, real local MCP and external ChatGPT acceptance. No private MEMORY database is authorized for repair or rebuild. Some legacy Studio editors remain separate compatibility windows, and full embedded terminal emulation is not implemented.

After source commit, generate release metadata only through release_metadata_sync, commit those two generated files, verify idempotence, push to the existing branch and verify exact remote SHA. Record final outcomes and SHA in the external checkpoint report; do not make a tracked report self-referential. Then recheck required CI and keep PR Draft until all remaining gates are actually met.
