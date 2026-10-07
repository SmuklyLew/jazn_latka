# Current project state

**Snapshot date:** 2026-10-07  
**Repository:** `SmuklyLew/jazn_latka`  
**Current master baseline:** `7b322284e49ed0a08d24d5cd5a56ba567532eba1`  
**Master release:** `16.3.25.5.113-remote-only-chatgpt-ingress-convergence`  
**Current update branch:** `upgrade/v119.2.0-chatgpt-desktop-mcp-convergence`  
**Target release:** `119.2.0-chatgpt-desktop-mcp-convergence`

This file is a short truth overlay. Canonical release identity always comes from
`latka_jazn/version.py`; merged/verified/live claims require repository, CI and
host evidence.

## 1. Master convergence status

v108, v110, v111, v112 and v113 are already represented in current master
through the merged stacked release train ending in PR #323. PR #319 remains open
as a stale historical draft, but comparison against current master shows its
only branch-only delta is generated release metadata
(`PACKAGE_INTEGRITY_MANIFEST.json` / `SOURCE_PROVENANCE.json`). It does not
contain missing v109 runtime code that must be cherry-picked.

The previous CURRENT_STATE/CURRENT_STEP documents still described v107/v112 as
current. That documentation drift is corrected by v119.2.0.

## 2. Live local evidence observed 2026-10-07

The Windows runtime reached package-integrity and source-provenance verification,
`system_fully_ready=true`, `conversation_ready=true`,
`runtime_core_ready=true`, a verified persistent daemon, a supervisor with
confirmed process fingerprint, local HTTP `/healthz=200` and `/readyz=200`,
and a stdio bootstrap reusing the same daemon.

A manual initialize-era MCP probe completed
`initialize -> notifications/initialized -> tools/list` and returned
`jazn_generate_visible_reply`, `jazn_resume_visible_reply`, `jazn_status`,
`jazn_finalize_reply`, plus app-only audit diagnostics.

A separate 2026-07-28 probe returned all four canonical tools with
`_meta.ui.visibility=["model","app"]` and no deprecated
`openai/visibility=private`.

## 3. Defect found after v113

The initialize-era 2025-11-25 `tools/list` path still returned historical
app-only/private metadata for some canonical tools. This made the protocol server
healthy while leaving a plausible ChatGPT Desktop discovery/binding failure
mode.

v119.2.0 fixes that asymmetry and adds a regression test covering the real
initialize/initialized/tools-list sequence. Modern 2026 behavior remains
unchanged.

## 4. Truth boundary

A successful local MCP handshake, installed server, plugin record, HTTP
`/readyz`, or tool catalog is not current-message capability evidence.
Ordinary ChatGPT still requires all four canonical tools callable on the current
message and then a fresh `jazn_status`.

Visible Jaźń text still requires accepted finalization with
`action=display_exact`.

## 5. Release work remaining

Before v119.2.0 is merge-ready, focused and full deterministic tests, Pyright,
release-hardening, package cleanroom, Linux/Windows persistent-runtime E2E and
final release-metadata idempotence must pass. A fresh ChatGPT Desktop acceptance
test must then verify current-message tool exposure after refresh/recreate.
