# Jaźń 16.3.25.5.116.0.34.1 — host capability source convergence

## What was missing after v116.0.34

Version 116.0.34 already corrected the ChatGPT Project loader, pre/post packaging contracts and separation of optional MEMORY from the dialogue core. It did **not** connect the ChatGPT app to a remote MCP server, and the user correctly requested an actual implementation delta on the specified branch rather than another copy of master.

## Implemented

- `latka_jazn/bootstrap/chatgpt_ingress_capability.py`: deterministic two-stage negotiation (`before_unpack` / `after_unpack`). It reuses strict existing public/registered MCP status validators, which require fresh current-message status, a complete four-tool exposure, version/protocol matching, confirmed daemon lineage and a current heartbeat. Otherwise it selects bounded local bootstrap **only** with evidence that a host process actually started, or reports a diagnostic without pretending to be Łatka.
- A verified local SYSTEM operator still only authorizes `host-preflight`, `start` and live `status`; no auto-claim of conversation readiness or accepted finalization.
- `latka_jazn/memory/availability.py`: filesystem `stat` failures on an optional private MEMORY candidate degrade the MEMORY capability without disabling the core or granting autobiographical recall. Invalid explicit root paths remain fail-closed.
- Regression tests for missing/copy-only/stale/wrong-version MCP status, pre/post materialization, truthful host capability outcomes and optional MEMORY errors.
- Bump to `16.3.25.5.116.0.34.1`; historic active tests archived before updating version assertions.

## Read-only operator command

After source materialization (or in an operator checkout), a host with a real Python executor can evaluate its own structured observations:

```bash
python -X utf8 -m latka_jazn.bootstrap.chatgpt_ingress_capability --phase before_unpack --evidence-file ./host-evidence.json
python -X utf8 -m latka_jazn.bootstrap.chatgpt_ingress_capability --phase after_unpack --evidence-file ./host-evidence.json
```

The input is a <=64 KiB JSON object with optional `callable_tool_names`, `current_message_toolset_observed`, `status_invoked_in_current_message`, `status_payload`, `local_process_created`, and `system_operator_verified`. The response includes only a redacted decision, not credentials, the raw status or memory. An actual ChatGPT host must *separately* supply real tool invocation evidence; a manually written JSON declaration is not an authentication mechanism. When Python is unavailable **before** unpacking, use native host discovery/probes, not this file as a magic bootstrap.

## Secure ChatGPT route — separate deployment requirement

The ChatGPT host cannot be granted new tools by the source tree, Project instructions, a ZIP, or a successful GitHub CI run. To make real calls in ChatGPT, deploy an authenticated, reachable MCP service through public HTTPS + OAuth 2.1 or an available Secure MCP Tunnel, refresh the installed plugin, and verify multiple consecutive real `jazn_status` / turn / finalize invocations. A local-only `127.0.0.1` declaration or Cloudflare 503 staging is not a working connection.

Operator acceptance requires an actual ChatGPT conversation with four callable tools, fresh status, two consecutive accepted and finalized turns, and a separate missing-MEMORY dialogue test.

## Validation and security

No private MEMORY, account secrets, public ingress credentials, transport authorization policy, or Cloudflare configuration changed. CI and package integrity must be checked on the new head; the release metadata generator, not manual hash editing, owns `SOURCE_PROVENANCE.json` and `PACKAGE_INTEGRITY_MANIFEST.json`.

External references:
- OpenAI plugin connection and refresh: https://developers.openai.com/plugins/deploy/connect-chatgpt
- OpenAI MCP authorization including OAuth2.1/PKCE: https://developers.openai.com/plugins/build/auth
- OpenAI MCP deployment guidance: https://developers.openai.com/plugins/build/mcp-server
