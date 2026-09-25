# Jaźń v16.3.25.5.85 — ChatGPT discovery evidence tri-state convergence

## Problem

The v16.3.25.5.83/84 line correctly introduced Library discovery and explicit host evidence fields, but two evidence-model errors remained:

1. `executor_available` and `remote_runtime_available` were serialized as plain booleans. No executor observation or no remote-runtime probe therefore collapsed to `false`, violating the loader rule that absence of evidence stays `unknown`.
2. `system_search_attempted=true` was rejected unless `library_search_available=true`, even though SYSTEM discovery may run on conversation files, Project files, Library, or another logical file surface. That incorrectly coupled a search outcome to one namespace.

## Fix

- Preserve `bool | None` for executor and remote-runtime availability in `ChatGptHostPreflightDecision`.
- Report executor availability as:
  - `true` when any current-generation surface is verified available;
  - `false` only when every observed current-generation surface is explicitly `host_executor_unavailable`;
  - `unknown` otherwise.
- Report remote-runtime availability as:
  - `true` only from verified positive remote evidence;
  - `false` only when an actual remote probe/transport observation exists and is negative;
  - `unknown` when no remote evidence was observed.
- Keep route selection fail-closed: `remote_runtime_allowed` remains a routing decision and does not become tri-state.
- Decouple `system_search_attempted` from ChatGPT Library availability. A SYSTEM candidate still requires an attempted SYSTEM search.
- Clarify the ChatGPT Project loader and runbook so that `false` requires explicit negative evidence and SYSTEM search can originate from conversation/Project/equivalent file surfaces.

## External evidence

Current OpenAI documentation describes Library availability as account/surface/permission dependent and distinguishes saved Library files from connected provider files. OpenAI MCP documentation likewise treats remote tools as explicit capabilities that must initialize and be authorized; configuration alone is not runtime readiness. The MCP transport documentation distinguishes negotiated/observed protocol state from mere configuration.

## Regression coverage

The release adds tests for:

- no executor observation => `executor_available=null`;
- no remote probe => `remote_runtime_available=null`;
- explicit negative remote probe => `remote_runtime_available=false`;
- SYSTEM search on a non-Library logical file surface;
- current ChatGPT runbook tri-state semantics;
- existing positive verified remote-runtime behavior.
