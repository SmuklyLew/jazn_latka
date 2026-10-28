# Jaźń — Serce Systemu: first-run + MCP/Tunnel boundary

Branch: `fix/run-studio-dual-chat-recovery-20261028`
Version: `16.3.25.5.116.0.34.94.6.12-run-studio-guided-onboarding-mcp-safety`
Base: PR #429 (draft). No live daemon or MEMORY modifications.

## Operator evidence, 2026-10-28

- The operator's `git worktree` completed correctly: separate `pr429-local` branch/worktree, while active `master` remains on `.10`.
- The observed launcher used Python **3.15**. Run Studio/core required dependencies were available. MCP/HTTP reported **0/4** (optional), so a public MCP connection must not be called ready. `pip check` only checked installed packages, not optional profiles.
- The operator's `run.py status --json` excerpt from the **master root** reported `active_trusted`, but `model_adapter_status = null_model_adapter`. The model does not yet generate local language.
- Canonical local MEMORY exists and transactional storage is operational; `memory_continuity_status=partial_unverified`, `normalization_status=normalization_stale`, `wake_context_ready=false`, and `continuity_claim_allowed=false`. Archive/search readiness **does not** establish autobiographical recall or continuity.
- `QFont::setPointSize(-1)` warning was observed; a root cause in the Studio source has not been confirmed. The warning alone is not evidence of a daemon failure or inability to show the Qt window.
- The current new-source worktree must not silently adopt or mutate the live daemon bound to the old master. A cross-root or cross-version status is shown as a mismatch, not an accepted client session.

## Implemented in this checkpoint

- Expanded first-run QWizard from only one editable model field to **all Settings dataclass fields**, grouped into local, MCP/tunnel and security/appearance; validation and save use the canonical Studio owner. No automatic writes when browsing, no implicit install/daemon/model/tunnel launch and no secret values in the wizard.
- Three-step dashboard: **start/check runtime → start/check Ollama + explicit model generation → open local chat**. Chat navigation unlocks only after a trusted local daemon identity and successful bounded Ollama generation probe for the chosen model.
- Canonical MEMORY/continuity is shown separately. A stale wake-state is never reported as verified continuity and is not automatically rebuilt while a daemon may be active.
- The status check now binds the **expected filesystem root and exact runtime version** to the canonical daemon evidence. The active master is not the same process lineage as an unactivated PR worktree.
- Retained MCP import preflight in the chosen interpreter. Updated the older PowerShell argv test by mocking a **successful preflight**, with its exact previous source retained under `tests/archive/` before the test change.

## Security review: ChatGPT / MCP / Tunnel

The public MCP endpoint is **not** the same thing as Studio's developer loopback endpoint:
1. Local Studio gateway starts `mcp-http --loopback-dev --host 127.0.0.1`; local `noauth` is only intended for direct loopback development.
2. Cloudflare Tunnel can expose that local HTTP port through a public hostname. A public hostname does not provide OAuth by itself; Cloudflare Access checks/IdP requirements are separate.
3. Exposing `--loopback-dev` via a tunnel would defeat its intended loopback security boundary. Studio therefore refuses **direct tunnel start** without an authenticated production deployment. The Studio panel still supports **read-only** gateway/Cloudflare probes. An authenticated `--public-oauth` gateway and public tunnel are deployed with the distinct `deploy/chatgpt_mcp` workflow after explicit operator approval.
4. Public OAuth requires issuer discovery, protected-resource metadata, proper challenge/status codes and token verification (issuer, audience and scope), and correct target endpoint. There is no evidence of these from local /readyz alone.
5. Remote tool visibility in a particular ChatGPT message requires a newly observed exposed toolset and a real `jazn_status` connector invocation. Installed app/tunnel connection alone cannot prove accepted conversation; `jazn_generate_visible_reply`, `jazn_resume_visible_reply`, `jazn_finalize_reply` and finalization lineage remain independent gates.
6. No paid OpenAI API key is required for the local Ollama chat and the Jaźń ChatGPT host transport, but separate provider auth/Cloudflare configuration and hosting limits must be handled by the operator.

## Manual acceptance gates (still pending until executed)

- On Windows, verify `py -0p`; use a separately supported environment for optional MCP dependencies, do not install incompatible wheels into the current Python 3.15 interpreter.
- Launch Studio in the **separate staging worktree** and check the full first-run form, validation, persistence, accessible labels and minimum 860×580 display.
- Check that runtime bound to old master results in **not-ready** on the PR worktree. Do **not** restart, migrate, copy MEMORY, or force-attach unrelated active state as part of this test.
- In an approved isolated test root: verify start/status, select existing Ollama model, `/api/tags` and bounded `/api/chat` generation, chat connect/send/resume and one accepted GUI final.
- Verify MEMORY search versus full autobiographical recall and wake-state separately with current canonical data and canonical maintenance procedures; do not edit SQLite/WAL/SHM manually.
- For public ChatGPT: use externally deployed `--public-oauth`, confirm OAuth, MCP `tools/list`, current host toolset, connector `jazn_status`, authenticated turn and accepted phase-2 finalization.
- Review GitHub Actions `release-hardening`, `jazn-run-studio`, `powershell-terminal-regressions`, and the metadata integrity sync on the **exact final SHA** before merge. No local runtime/Cloudflare E2E has been executed by the authoring host.

## Primary documentation

- Qt QWizard/QWizardPage lifecycle and validation: https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWizardPage.html
- Qt QFont point-size requirement: https://doc.qt.io/qtforpython-6/PySide6/QtGui/QFont.html
- Ollama chat and model tags: https://docs.ollama.com/api
- MCP 2026-07-28 Streamable HTTP: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx
- OAuth and MCP resource servers: https://apps.extensions.modelcontextprotocol.io/api/documents/authorization.html
- Cloudflare public tunnel ingress: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/
- Cloudflare secure MCP servers: https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/secure-mcp-servers/
- Project-specific deployment: `deploy/chatgpt_mcp/README.md`, `docs/runtime/LOCAL_MCP_TO_CLOUDFLARE_OAUTH_STAGING_42.md`

**Not a production release or proof of a running Jaźń turn in this ChatGPT conversation.**
