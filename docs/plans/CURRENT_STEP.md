# Jaźń — CURRENT STEP

**Status:** `CANONICAL_CURRENT_STEP`  
**Date:** 2026-10-07  
**Base master:** `7b322284e49ed0a08d24d5cd5a56ba567532eba1` / v113  
**Branch:** `upgrade/v119.2.0-chatgpt-desktop-mcp-convergence`  
**Target:** `119.2.0-chatgpt-desktop-mcp-convergence`

## Current objective

Close the real ChatGPT Desktop MCP discovery gap observed after v113 without
creating a second runtime or weakening the remote-only ordinary-chat gate.

## Confirmed root-cause boundary

Persistent daemon, supervisor, local HTTP readiness and stdio MCP negotiation
are healthy. Manual MCP `tools/list` returns the complete canonical tool names.
The missing parity was metadata on initialize-era MCP discovery: modern
2026-07-28 discovery already promoted the canonical tools to model-visible while
legacy 2025-11-25 discovery did not.

## v119.2.0 implementation

1. normalize only the four canonical turn tools on legacy `tools/list` to
   `ui.visibility=["model","app"]`;
2. remove deprecated `openai/visibility=private` from those tools only;
3. keep audit/diagnostic/compatibility tools app-only;
4. preserve modern discovery behavior;
5. add the exact initialize -> initialized -> tools/list regression;
6. bump release identity and active release contracts;
7. update stale project/runtime truth documents;
8. use canonical automation for Test Studio and release metadata.

## Exit gate

Release-candidate quality requires focused MCP tests, full non-live deterministic
pytest, compileall, Pyright, release-hardening, persistent-runtime E2E on Linux
and Windows, package cleanroom/system smoke, synchronized/idempotent generated
metadata, and a fresh Desktop host test that exposes all four canonical tools on
the current message and receives fresh v119.2.0 readiness from `jazn_status`.

No repository test may replace the final current-message host exposure check.
