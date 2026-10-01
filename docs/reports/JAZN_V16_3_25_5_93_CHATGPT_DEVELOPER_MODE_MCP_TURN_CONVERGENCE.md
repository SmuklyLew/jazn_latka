# Jaźń v16.3.25.5.93 — ChatGPT Developer Mode MCP turn convergence

## Purpose

This release applies the ChatGPT Developer Mode / MCP integration research to
the existing v92 architecture without moving persistent MEMORY into an
ephemeral ChatGPT sandbox and without creating a second Jaźń runtime.

## Architecture decision

ChatGPT is a client of one persistent Jaźń daemon. Public HTTPS MCP and OpenAI
Secure MCP Tunnel are transport choices to that same daemon. MEMORY, cognition,
affect, turn lineage and host-visible finalization remain runtime-owned.

The existing two-phase safety boundary is preserved. Version 5.93 adds an
ergonomic Developer Mode facade instead of replacing
generate_then_finalize -> jazn_finalize_reply -> display_exact.

## Implemented changes

- Added latka_jazn/mcp/developer_mode_surface.py as a shared transport-only
  adapter for public HTTPS and Secure MCP Tunnel.
- Added the public tools jazn_turn, jazn_resume_turn, jazn_health and
  jazn_memory_status.
- Kept jazn_finalize_reply and jazn_status visible because finalization and
  connector-observed readiness remain part of the canonical contract.
- Hid the canonical generate/resume implementation names from the modern
  Developer Mode tool list while preserving them for compatibility and Tasks.
- Mapped clientTurnId exactly to request_id / daemon_request_id.
- Rewrote pending-result guidance to point back to jazn_resume_turn and preserve
  must_not_resubmit_user_message=true.
- Ensured Secure MCP Tunnel aliases are decorated by ProfessionalTurnRuntime
  using the translated canonical request, so aliases cannot bypass typed turn
  lineage.
- Added redacted health and memory-readiness results that do not expose raw
  MEMORY, local paths or private operator state.
- Left raw MEMORY entirely on the persistent runtime host.

## Security decisions

The research considered unauthenticated public endpoints and static secrets in
URLs. This patch intentionally does not adopt those weaker production options.

The existing fail-closed policy remains:

- public non-loopback Streamable HTTP requires TokenVerifier / OAuth
  resource-server configuration;
- no-auth remains explicit loopback development only;
- Secure MCP Tunnel remains a separate private transport with its own external
  control-plane credentials;
- a SYSTEM package cannot create a ChatGPT connector capability by itself.

## ChatGPT first-message behavior

When the Jaźń app is selected for a Developer Mode conversation, the tool
description makes jazn_turn the primary entrypoint for every ordinary user
message, including the first message in a new conversation.

The repository still cannot force ChatGPT to globally preselect an app for every
new conversation. That is a host/UI capability boundary. The implementation
therefore optimizes the first call after selection rather than claiming a global
auto-activation capability that the platform has not provided.

## Tests

The patch updates the public HTTP tool-surface tests and adds a dedicated
Developer Mode convergence suite covering:

- exact clientTurnId -> request_id mapping;
- resume without message replay;
- modern tool-list redaction of internal generate/resume names;
- poll_runtime guidance toward jazn_resume_turn;
- redaction of memory/operator internals;
- release version contract.

Previous active tests modified by this release were archived byte-for-byte under
tests/archive before replacement, in accordance with repository governance.

## Release metadata

PACKAGE_VERSION: 16.3.25.5.93
PACKAGE_RELEASE_NAME: chatgpt-developer-mode-mcp-turn-convergence

PACKAGE_INTEGRITY_MANIFEST.json and SOURCE_PROVENANCE.json are not hand-edited.
The upgrade branch relies on the canonical release-hardening metadata sync.

## Research sources

OpenAI Developers — ChatGPT Developer mode
https://developers.openai.com/api/docs/guides/developer-mode

OpenAI Developers — Connect and test your plugin
https://developers.openai.com/plugins/deploy/connect-chatgpt

OpenAI Developers — Secure MCP Tunnel
https://developers.openai.com/api/docs/guides/secure-mcp-tunnels

MCP specification / Python SDK — the protocol, Streamable HTTP, Tasks and
authorization contracts already pinned and tested by the repository.
