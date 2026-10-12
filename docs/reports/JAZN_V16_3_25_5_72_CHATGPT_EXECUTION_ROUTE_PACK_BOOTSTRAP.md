# JAZN v16.3.25.5.72 — ChatGPT execution-route and Pack bootstrap convergence

## Problem

A SYSTEM ZIP can be complete and valid while the current ChatGPT surface still cannot create a local process. Earlier host preflight treated local executor state as the dominant route decision, which made an unavailable local executor look too close to a package/runtime failure. Pack Generator also proved bytes and integrity but did not publish a machine-readable statement that package completeness is independent from host execution privileges.

## External evidence

The implementation follows current host and protocol boundaries rather than attempting to bypass them:

- OpenAI Help, **ChatGPT Work and Codex**: Work on desktop can work with local files/folders after user permission; Work on web/mobile does not directly gain access to local files on the user's computer. This is a host capability, not something a Python package can grant.
  - https://help.openai.com/en/articles/20001275
- OpenAI Help, **Developer mode and MCP apps in ChatGPT**: ChatGPT custom MCP connectivity is plan/workspace dependent; local/private services require an explicitly supported remote/tunnel path rather than assuming direct access to an arbitrary local stdio server.
  - https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- Model Context Protocol specification, **Transports**: stdio launches a subprocess owned by the client; Streamable HTTP is an independent HTTP transport. These are distinct execution topologies and should not be conflated.
  - https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- Python `zipfile` documentation: archive extraction must keep path/trust boundaries explicit; package bytes do not establish host execution authority.
  - https://docs.python.org/3/library/zipfile.html

## Runtime changes

`latka_jazn/core/chatgpt_host_executor_contract.py` now models execution topology explicitly:

- `local_executor` — a concrete local process was created and can be evaluated;
- `remote_runtime` — the host explicitly advertises an external runtime transport;
- `host_handoff` — the current surface cannot execute locally but the host explicitly offers a transition to an execution-capable surface;
- `none` — no safe route has been established.

A failed local process creation remains `host_executor_unavailable`; it is never upgraded to `available` merely because a remote/handoff route exists. Filesystem/package/runtime state stays unknown/unverified until separate evidence exists.

`latka_jazn/bootstrap/chatgpt_host_preflight.py` exposes independent gates:

- `bootstrap_allowed` / `local_bootstrap_allowed`;
- `remote_runtime_allowed`;
- `handoff_required`;
- `execution_route` and route-specific `next_action`.

This prevents a package or local preflight from pretending it repaired a platform-level executor.

## Pack Generator 10.1.86.0.115

SYSTEM and SYSTEM+MEMORY manifests remain `jazn_pack_generator_package/v2` for compatibility and gain an additive `host_bootstrap` object with schema `jazn_host_bootstrap_contract/v1`.

Before a SYSTEM package proceeds, the generator requires:

- `CHATGPT_BOOTSTRAP.py`;
- `run.py`;
- `main.py`;
- `AGENTS.md`;
- `AGENTS.chatgpt.md`;
- `latka_jazn/version.py`;
- `PACKAGE_INTEGRITY_MANIFEST.json`;
- `SOURCE_PROVENANCE.json`.

The manifest states explicitly that local bootstrap requires host process creation, package bytes cannot grant a host executor, remote runtime transport is external, and capability negotiation is required. MEMORY remains data-only and is never an active SYSTEM root.

## Compatibility and safety

- Existing `jazn_pack_generator_package/v2` loaders are not broken by a new outer schema.
- The established safe-extract, per-member SHA-256, clean-room integrity and provenance checks remain unchanged.
- Existing local executor behavior remains preferred when a usable local process is actually observed.
- A remote route or handoff is selected only from explicit host-declared capability evidence.
- No code claims that ordinary Chat can be forced by repository Python to spawn a local process.

## Tests

New tests cover remote-runtime routing, execution handoff, local-route precedence, filesystem truth boundaries, SYSTEM bootstrap completeness and MEMORY data-only semantics. The prior Pack Generator integration test is archived before its version/contract assertions are advanced to 10.1.86.0.115.
