# v112 — v111 closeout and real ChatGPT-host evidence

**Date:** 2026-10-06  
**Branch:** `upgrade/v16.3.25.5.112-v111-closeout-real-host-evidence-convergence`  
**Parent v111 SHA:** `ee00529cdbd9a4d0a469007db787ed4895667ddf`  
**Scope:** documentation/evidence/version closeout; no new conversation-runtime semantics.

## Result

The three v111 closeout items are now technically resolved:

1. stale repository truth documents are synchronized with final v111 validation;
2. the actual ChatGPT-host local-executor E2E was executed and reached accepted
   `display_exact`;
3. bounded final evidence is recorded here and in the canonical current-state docs.

No PR merge is authorized.

## Repository baseline

Final v111 repository evidence before this closeout:

- full local deterministic suite: **2107 PASS, 4 platform SKIPPED, 0 FAIL**;
- expected duplicate-ZIP warning only;
- final SHA `ee00529cdbd9a4d0a469007db787ed4895667ddf`;
- Pyright, release-hardening, persistent-runtime E2E Linux/Windows,
  package-distribution-cleanroom and PowerShell: **SUCCESS**;
- PR #321 rollup: **51 SUCCESS, 2 SKIPPED**.

## Host capability discovery

For the closeout message, the full remote Jaźń turn toolset
`jazn_status`, `jazn_generate_visible_reply`,
`jazn_resume_visible_reply`, `jazn_finalize_reply` was not callable.
Therefore a remote route was not claimed.

A fresh local process probe succeeded, so the host followed the independent
`local_executor` route from `AGENTS.chatgpt.md`.

This distinction matches current OpenAI product guidance: ChatGPT connects to a
configured remote MCP app, or to a private/local MCP server through Secure MCP
Tunnel when supported; mere presence of local MCP code is not a callable ChatGPT
app capability.

## Final v111 artifact verification

The host used the package produced from the final v111 SHA, not a source-tree
substitute:

- GitHub Actions workflow run: `37410740819`;
- artifact id: `11389445665`;
- artifact name: `jazn-package-linux-x64-py3.12`;
- outer artifact SHA-256:
  `541def22dbd2f6f0ea88ffa4cc3cc259f175b176806164d5290b87283986d613`;
- contained SYSTEM ZIP:
  `jazn_latka_v16.3.25.5.111-conversation-runner-legacy-dialogue-cutover-convergence.system-portable__linux-x64__py312.zip`;
- SYSTEM ZIP SHA-256:
  `aa9ba3cb8182b4fb63617f7e850d73039eb20731d7ab8849ca07de8d45d5356c`;
- size: `5,191,102` bytes;
- catalog: 2025 entries;
- CRC/path audit: PASS;
- `CHATGPT_BOOTSTRAP.py` SHA-256:
  `88a78adb1e8363cf1278363665b8281cf7533d5d2add0ac57adc7789518c57d6`.

Only the bootstrap member was materialized manually. The helper then performed the
fail-closed SYSTEM materialization and same-interpreter host preflight.

## Live runtime evidence

After durable daemon-start completed, canonical live `status --json` reported:

```text
activation_truth_gate_eligible=true
capability_matrix.conversation_ready=true
runtime_core.available=true
local_transport.available=true
host_finalization.available=true
voice_live_ready=true
system_fully_ready=true
```

Private persistent MEMORY was absent in optional mode and did not block ordinary
dialogue. No autobiographical recall claim was made.

## One-message / no-replay turn evidence

The exact user message was submitted once with a request id allocated before the
transport process:

- request id:
  `chatgpt-v111-3e423b5c5af14f9b9d71a9b4ace83388`;
- turn id:
  `6545d98a-35ea-4a0d-8c7a-f8af41a9880b`;
- trace id:
  `chatgpt-v111-3e423b5c5af14f9b9d71a9b4ace83388`;
- user-text SHA-256:
  `88b39175f6ff3919870eaf7c1f797d77255b6dc1e5787a1faa41baabec56f6d3`.

Phase-1 returned `generate_then_finalize`.

The first phase-2 call intentionally remains part of the evidence because it
demonstrated fail-closed binding: the host passed the finalization-contract hash
where the durable host-request hash was required. Runtime rejected it with
`host_request_contract_hash_mismatch` and left the durable request pending.

The host then polled the **same** request; it did not resend the user message.
Using the durable request-contract hash
`d019552d5a08acf3eb00251147caa3f383beb01a458170ad0caee2aaf60b8bcc`,
phase-2 returned:

```text
accepted=true
replay_protected=true
turn_authority_validation.ok=true
accepted_visible_turn_ready=true
action=display_exact
visible_output_source=runtime_finalized
```

Turn-authority receipt SHA-256:
`dcd8f7300a5c9f9f6870862ac4d14ffc6f474775d86387c56bb6f0997c6f9d14`.

This is positive evidence for the v111 **real ChatGPT host local-executor route**.
It is not evidence for a public Streamable HTTP connector or Secure MCP Tunnel
deployment.

## External references verified for this closeout

Primary sources checked on 2026-10-06:

- MCP Tasks 2026-07-28:
  https://tasks.extensions.modelcontextprotocol.io/specification/2026-07-28/tasks
  — durable task identity and polling/resume support the no-replay design.
- MCP TypeScript SDK protocol versions:
  https://ts.sdk.modelcontextprotocol.io/v2/protocol-versions
  — the 2026-07-28 modern lifecycle uses per-request protocol/capability semantics.
- OpenAI Help Center, Developer mode and MCP apps in ChatGPT:
  https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt
  — ChatGPT uses configured MCP apps; local/private servers require an appropriate
  remote route such as Secure MCP Tunnel rather than being inferred from local files.

## Truth boundary

This report records one real host generation and one accepted finalization lineage.
It does not imply universal host availability, permanent background execution,
persistent private MEMORY, or remote MCP deployment. Every future conversation
must re-evaluate its current capabilities.


## v112 CI correction evidence

The first v112 push exposed a real release-contract drift rather than a runtime
behavior regression. Persistent-runtime E2E run `37416896354` failed on both
Windows and Linux in:

`tests/test_persistent_remote_runtime_operations.py::test_deployment_contract_tracks_runtime_and_real_mcp_wire_names`.

Observed matrix before the assertion: **72 PASS, 1 FAIL** on each platform. The
failure was exact and symmetric:

```text
deploy/chatgpt_mcp/deployment.contract.json runtime_version
= 16.3.25.5.111-conversation-runner-legacy-dialogue-cutover-convergence

PACKAGE_VERSION_FULL
= 16.3.25.5.112-v111-closeout-real-host-evidence-convergence
```

The correction updates only the deployment contract's declared runtime version to
the v112 package identity. No assertion, gate, route, readiness requirement, MCP
method name, or security rule is weakened. The failed run remains evidence and the
corrected branch must pass a fresh persistent-runtime E2E before v112 is considered
complete.


### Full-suite release identity drift found by release-hardening

The same first v112 generation also produced release-hardening run
`37416896389`. Its Ubuntu full deterministic suite completed
**2104 PASS, 2 SKIPPED, 5 FAIL** before the fix sequence. All five failures were
release-identity assertions caused by the v112 bump while active contracts/tests
still pinned v111:

- `tests/test_chatgpt_capability_loader_convergence.py::test_release_version_tracks_current_distribution_identity`;
- `tests/test_chatgpt_fresh_session_plugin_exposure_convergence.py::test_startup_contract_publishes_fresh_message_capability_gate`;
- `tests/test_chatgpt_zip_bootstrap_runtime_convergence.py::test_release_identity_tracks_current_distribution`;
- `tests/test_fast_bootstrap_persistent_runtime.py::test_release_identity_tracks_current_distribution`;
- `tests/test_persistent_remote_runtime_operations.py::test_deployment_contract_tracks_runtime_and_real_mcp_wire_names`.

The deployment-contract mismatch is fixed in the preceding correction. This follow-up
updates `latka_jazn/resources/startup_contract.json` to v112 and updates the three
active tests that intentionally pin the current release identity. Before modifying
those active tests, their exact committed v111 bytes are preserved append-only under
`tests/archive/v16.3.25.5.111-v112-release-identity-bump/`, per repository policy.
No behavioral assertion is removed or weakened.
