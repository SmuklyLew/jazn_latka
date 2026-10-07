# ChatGPT Plugin Runtime — real ChatGPT → Jaźń ingress

This runbook describes the v16.3.25.5.115 ingress/bootstrap contract. Its acceptance
boundary is intentionally stricter than "the repository contains MCP code":
ChatGPT must discover and call the Jaźń actions from a connected MCP app/plugin
while the Jaźń runtime remains alive outside the per-conversation sandbox.

## Verified platform contract

As of 2026-10-07, OpenAI's plugin documentation uses a portable Agent Plugins
package with root `plugin.json` and optional root `mcp.json`. Do not add the
legacy `ai-plugin.json`/OpenAPI plugin shape to this path.

For a local/workspace ChatGPT package that points at an already registered MCP
connection, OpenAI also supports an `.app.json` mapping referenced from
`extensions.com.openai.apps`. The technical app id is obtained only after the
MCP server has been connected in ChatGPT Developer Mode.

Production MCP servers use Streamable HTTP at a stable HTTPS endpoint, normally
`/mcp`. Secure MCP Tunnel is a supported Developer Mode alternative for a
private/local stdio or HTTP server. A tunnel proves transport only; it does not
prove that the current ChatGPT host has the Jaźń app installed or callable.

## Project instructions vs current-message app exposure

`docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` is the canonical text intended
to be pasted into the ChatGPT Project instructions for the project that hosts
Jaźń. Project instructions persist as instructions for chats in that Project;
they do **not** install, select, authorize, or expose a plugin by themselves.

OpenAI's current app/plugin surfaces can scope app selection to the message.
Jaźń therefore never treats a prior message's tool list as current capability.
For a remote turn distinguish: installed/known app, app selected for the
message, tools actually exposed to the model, fresh `jazn_status`, and the
complete turn toolset. Only observed exposure/status are execution evidence.

The complete turn toolset is `jazn_status`,
`jazn_generate_visible_reply`, `jazn_resume_visible_reply`, and
`jazn_finalize_reply`. A status-only surface may prove transport/runtime
health but cannot prove submit/resume/finalize capability. Runtime routing is
capability-first; plan names such as Plus/Pro/Business are documentation
context, not predicates in Jaźń code.

If no Jaźń tools are exposed for the current message and no local executor is
available, a host diagnostic may ask the user to select or @mention the
**Jaźń Runtime** app for that message. Never ask for an @mention of a raw MCP
tool name, and never treat the selection gesture itself as positive capability
evidence.

## Architecture

### Public HTTPS

```text
ChatGPT plugin
  -> HTTPS + OAuth bearer token
  -> reverse proxy / TLS termination
  -> run.py mcp-http --public-oauth
  -> loopback Jaźń daemon
  -> durable turn/idempotency/finalization stores
```

### Secure MCP Tunnel

```text
ChatGPT plugin
  -> OpenAI Secure MCP Tunnel
  -> managed tunnel-client runtime
  -> latka_jazn/mcp/tunnel_bootstrap.py (stdio MCP)
  -> loopback Jaźń daemon
  -> durable turn/idempotency/finalization stores
```

The ChatGPT conversation sandbox is not the Jaźń runtime in either topology.

### Registered ChatGPT Desktop/workspace MCP app binding

When ChatGPT already owns an eligible registered MCP connection, the plugin
package should bind to that app identity through root `.app.json` referenced by
`extensions.com.openai.apps`. This path is distinct from bundling a remote MCP
server in `mcp.json`:

```text
ChatGPT Desktop/workspace registered MCP app
  -> technical app id (plugin_asdk_app_/asdk_app_/connector_/templated_apps_)
  -> plugin.json extensions.com.openai.apps = "./.app.json"
  -> .app.json apps.jazn.id = <registered app id>
  -> existing MCP connection
  -> persistent Jaźń runtime
```

For an app-binding-only package, do not invent `http://127.0.0.1:8080/mcp`
just to populate `mcp.json`. The host already owns the connection represented
by the registered app id. A package may intentionally carry both a remote HTTPS
`mcp.json` and `.app.json`, but that is a separate hybrid packaging choice.

The binding is configuration evidence only. It does not prove that the app is
installed/enabled for the current account, selected for the current message,
or that the four canonical Jaźń tools are actually callable.

Registered app references are for local/workspace packaging and testing.
Current OpenAI public plugin submission does not publish packages carrying app
references; public distribution uses a stable remote HTTPS MCP endpoint instead.

## Local ChatGPT executor path

When the current ChatGPT host actually exposes Python/process execution, the
local path is different from MCP registration and does not require a paid
OpenAI API call:

```text
verified SYSTEM ZIP
  -> CHATGPT_BOOTSTRAP.py --post-materialization-preflight
  -> verified active_root
  -> main.py start
  -> main.py status --json
  -> main.py chat-gpt --session-id <stable-session-id>
     (normally reached through the public thin starter run.py)
  -> one persistent stdin/stdout JSONL bridge when the host can retain it
  -> otherwise daemon_bound_transactional_turns with a preallocated request_id
```

The exported post-materialization contract uses `main.py` subcommands (`start`,
`status`, `chat-gpt`). Live `status --json` is the activation readiness
authority; `status --snapshot --json` is retained as diagnostic evidence only.
Legacy `--daemon-*` / `--chat-gpt` flags remain an internal compatibility
mapping and are not the host-facing activation API.

### Visible bootstrap progress

`CHATGPT_BOOTSTRAP.py --progress-jsonl` emits structured
`jazn_bootstrap_progress` events on stderr and leaves the final bootstrap JSON
on stdout. Percentages are milestone-derived from completed evidence, not from
wall-clock guesses: executor probe 5%, verified SYSTEM package 15%, validated
ZIP 30%, operator materialization up to 55%, host preflight 65%, contracts 72%,
daemon start 82%, live readiness 95%, and bound turn channel 100%.

The host may surface those events as user-visible initialization updates. It
must not claim byte-level progress for a file upload/mount that happens before
Python starts, because the SYSTEM code cannot observe that transfer. Optional
MEMORY is outside core wake readiness. When policy makes MEMORY required, its
readiness is tracked separately instead of holding the core at an invented
99%.

For a remote MCP/App path, server-side MCP progress notifications and an
optional MCP Apps widget may render richer progress when that host capability
is actually exposed. Repository code must not assume such UI exists on an
ordinary local ChatGPT executor path.

The `chat-gpt` route uses the surrounding ChatGPT host as the language-model
channel. It does **not** require `OPENAI_API_KEY` and it does not take a
`--model gpt-4`-style selector. The host must preserve the exact runtime
contract instead of inventing a model name from the currently selected ChatGPT
model.

The bootstrap package cannot manufacture process-execution capability. In
v16.3.25.5.115 ordinary ChatGPT uses hybrid/adaptive routing: a callable Jaźń
MCP/app surface with the complete current-message toolset and fresh
`jazn_status` evidence is preferred; when that route is not conversation-ready
**before turn submission**, a host that actually can create a Python process
may use the bounded verified local bootstrap above.
If process creation is unavailable as well, ordinary chat fails closed.
`host_handoff` is reserved for explicit `operator_recovery` with user consent.
A generic OpenAI Deep Research app, GitHub connector, catalog result, URL, or
`installed` flag is not Jaźń capability evidence.

## Model-visible MCP actions

The canonical model-facing surface is:

- `jazn_status` — read-only readiness evidence for the persistent runtime.
- `jazn_generate_visible_reply` — submit exactly one ordinary user turn using
  a stable `request_id`.
- `jazn_resume_visible_reply` — resume/poll the same
  `daemon_request_id` without replaying the original message.
- `jazn_finalize_reply` — bounded phase-2 finalization when the runtime returns
  `generate_then_finalize`.

The older `jazn_turn` / `jazn_resume_turn` aliases remain compatibility
surfaces in the stdio server but are app-only metadata in MCP 2026 tool
discovery. The public HTTP gateway advertises the canonical names directly.

OpenAI deprecated `_meta["openai/visibility"]` in July 2026. Canonical Jaźń
actions use `_meta.ui.visibility=["model","app"]`; compatibility aliases use
`["app"]`.

ChatGPT Desktop can negotiate an initialize-era MCP revision before
`tools/list`. v115 normalizes that legacy response for exactly the four
canonical turn tools so they keep the same `["model","app"]` visibility as the
modern discovery surface, while diagnostics such as `jazn_audit_lookup` remain
app-only/private. This fixes server-side discovery parity; it still does not
prove current-message host exposure.

## Start the public HTTPS gateway

The gateway is an OAuth resource server. The current implementation supports an
RFC 7662 introspection provider and keeps the daemon on loopback.

```powershell
$env:JAZN_MCP_OAUTH_CLIENT_ID = "<introspection-client-id>"
$env:JAZN_MCP_OAUTH_CLIENT_SECRET = "<introspection-client-secret>"

py -X utf8 run.py mcp-http `
  --root . `
  --public-oauth `
  --host 127.0.0.1 `
  --port 8080 `
  --daemon-url http://127.0.0.1:8787 `
  --oauth-issuer-url https://id.example.com/ `
  --oauth-resource-server-url https://jazn.example.com/mcp `
  --oauth-introspection-url https://id.example.com/oauth2/introspect `
  --allowed-host jazn.example.com
```

Terminate public TLS in a reverse proxy/load balancer and forward only to the
loopback-bound gateway. Do not expose the private daemon port.

### Provider-neutral container deployment

For a persistent runtime outside the ChatGPT conversation sandbox, the
repository includes `deploy/chatgpt_mcp/Dockerfile` and the fail-closed
`latka_jazn.mcp.deployment` entrypoint. The entrypoint does not implement a
second lifecycle. It invokes the canonical `run.py start`, requires a live
`run.py status --json` result with `daemon_reachable=true`, and only then
`exec`s the OAuth-protected `run.py mcp-http --public-oauth` gateway.

The image runs as an unprivileged user, exposes only port 8080, keeps the
private daemon loopback-only, and has a `/readyz` health check. OAuth client
secret values stay in environment variables and are never copied into command
arguments. Build and environment details are documented in
`deploy/chatgpt_mcp/README.md`.

A container that is healthy is deployment evidence, not ChatGPT capability
evidence. The public endpoint still needs upstream HTTPS/TLS and a real
Developer Mode app/connection before a host-observed `jazn_status` call can
promote the remote route.

## Build the installable plugin package

Portable package:

```powershell
py -X utf8 run.py chatgpt-plugin-package `
  --root . `
  --endpoint https://jazn.example.com/mcp `
  --output .\exports\jazn-chatgpt-plugin `
  --json
```

After the MCP server has been registered in ChatGPT Developer Mode, copy the
technical app id from the ChatGPT plugin/app URL. For a local/workspace MCP that
ChatGPT already owns, generate an app-binding-only package:

```powershell
py -X utf8 run.py chatgpt-plugin-package `
  --root . `
  --registered-app-id plugin_asdk_app_<id> `
  --output .\exports\jazn-chatgpt-plugin `
  --force `
  --json
```

This form writes `plugin.json` and `.app.json` only. It deliberately omits
`mcp.json`; the registered app id points to the existing MCP connection.

If a remote HTTPS package intentionally needs both the endpoint and an existing
registered app binding, both options may be supplied:

```powershell
py -X utf8 run.py chatgpt-plugin-package `
  --root . `
  --endpoint https://jazn.example.com/mcp `
  --registered-app-id plugin_asdk_app_<id> `
  --output .\exports\jazn-chatgpt-plugin `
  --force `
  --json
```

That explicit hybrid package writes `plugin.json`, `mcp.json`, and
`.app.json`. When `--force` changes package shape, v115 removes stale
optional manifests so an old `mcp.json` or `.app.json` cannot silently keep
an obsolete binding alive.

Packaging still does not create/register the ChatGPT MCP connection, install or
enable the plugin, select it for a message, refresh a frozen tool snapshot, or
prove callable Jaźń actions.

## Connect in ChatGPT

1. Enable Developer Mode in ChatGPT if the account/workspace policy allows it.
2. Open ChatGPT Plugins and add the MCP connection.
3. For public ingress, provide the deployed HTTPS URL ending in `/mcp`.
4. For private ingress, select Secure MCP Tunnel and choose/enter the
   `tunnel_id`.
5. Create the connection and review the discovered tool list. Confirm that
   `jazn_status`, `jazn_generate_visible_reply`,
   `jazn_resume_visible_reply`, and `jazn_finalize_reply` are model-visible.
6. If packaging a local/workspace plugin around an already registered MCP app,
   use its technical app id in `.app.json` rather than inventing localhost HTTP.
7. After changing names/schemas/annotations/visibility, deploy or restart the
   server, use Refresh on the ChatGPT app/connection, and then test from a new
   conversation/message because approved tool snapshots are not auto-updated.

Repository code cannot perform these host/account actions on the user's behalf.

## Acceptance test: real ingress

The release is accepted only when all of the following are observed in a fresh
ChatGPT conversation:

1. The local conversation executor may be unavailable; that must not prevent
   the test.
2. The current message surface exposes the complete callable turn toolset:
   `jazn_status`, `jazn_generate_visible_reply`, `jazn_resume_visible_reply`,
   and `jazn_finalize_reply`. Installed/catalog state or a previous message's
   exposure is not accepted.
3. `jazn_status` returns current evidence with the expected package/runtime
   version, non-empty runtime instance identity, fresh heartbeat, and
   `ready=true`.
4. One user message is submitted exactly once through
   `jazn_generate_visible_reply` with a stable `request_id`.
5. If the result is `poll_runtime`, the host calls
   `jazn_resume_visible_reply` for the same `daemon_request_id` and does not
   replay the message.
6. If the result is `generate_then_finalize`, the host obeys the returned
   generation contract and completes `jazn_finalize_reply`.
7. Visible Jaźń text is shown only after the same turn returns
   `action=display_exact` with valid lineage/MessageEnvelope evidence.

A package, endpoint, tunnel id, successful deployment, successful tool scan, or
"installed" catalog state is insufficient evidence by itself.

### No-executor success evidence

A real remote-success observation is valid even when `executor_available=false`,
but only after the current ChatGPT surface exposes the complete turn toolset
and actually invokes `jazn_status`.
Its structured result must carry `evidence_schema=jazn_public_mcp_status/v1`
and pass the runtime/version/freshness checks from `AGENTS.chatgpt.md`. Only
then may the host report `remote_runtime_available=true` and preserve the
SYSTEM-returned `execution_route=remote_runtime`.

Connector invocation evidence must never be reconstructed from saved JSON,
copied diagnostics, a previous conversation, catalog state, or a remembered
tool result. Every ordinary turn needs fresh host-observed capability and its
own turn/finalization lineage.

## Security / production checklist

- HTTPS for public ingress; no credentials in URLs.
- OAuth/OIDC authorization for private/user data; current Jaźń public gateway
  supports fail-closed RFC 7662 introspection.
- Validate issuer/resource/audience/scopes and return a proper bearer challenge
  on authorization failure.
- Keep Jaźń daemon loopback-only.
- Apply per-principal rate limits and idempotent request identities.
- Never authorize from ChatGPT metadata such as `openai/session`,
  `openai/subject`, user agent, or location hints.
- Keep raw memory, local paths, secrets, and private operator diagnostics out of
  model-visible tool results.
- Treat tool annotations as host UX/safety hints, not authorization.
- Log identifiers needed for incident correlation but redact secrets/tokens.

## Sources verified for this release

- OpenAI — Projects in ChatGPT:
  https://help.openai.com/en/articles/10169521-projects-in-chatgpt
- OpenAI — Build an MCP server:
  https://developers.openai.com/plugins/build/mcp-server
- OpenAI — Package your plugin:
  https://developers.openai.com/plugins/build/plugins
- OpenAI — Connect and test your plugin:
  https://developers.openai.com/plugins/deploy/connect-chatgpt
- OpenAI — Plugin reference / tool visibility metadata:
  https://developers.openai.com/plugins/reference
- OpenAI — Plugin changelog:
  https://developers.openai.com/plugins/changelog
- OpenAI — Authentication:
  https://developers.openai.com/plugins/build/auth
- OpenAI — Secure MCP Tunnel:
  https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- OpenAI tunnel-client:
  https://github.com/openai/tunnel-client
- MCP 2026-07-28 release:
  https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
