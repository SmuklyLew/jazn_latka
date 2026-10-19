# Jaźń v16.3.25.5.116.0.34.12 — ChatGPT/OpenAI/Ollama connection recovery

Status: implementation candidate on `fix/v16.3.25.5.116.0.34.12-chatgpt-openai-ollama-connection-recovery`; no claim of host activation.

## Verified findings

- OpenAI requires a genuine, connected MCP app: public Streamable HTTP over HTTPS or a separately configured Secure MCP Tunnel. Auth metadata, real OAuth, fresh tool discovery and ChatGPT plugin Refresh are distinct gates.
- The SYSTEM ZIP and Project instructions cannot create a ChatGPT host process or install a ChatGPT MCP connection.
- Ollama `POST /api/chat` returns a JSON object with a `message` and `done` terminal marker; `GET /api/tags` lists actual available model names/tags. The adapter previously accepted `done=false`/missing and any tag sharing the requested model's family.
- The offline plugin doctor could report a valid public HTTPS endpoint without even distinguishing whether OAuth was declared. This did **not** imply live readiness but produced an incomplete next action.

## Implemented

1. **Ollama response gate:** require JSON object, explicit `done=true`, an object `message` and string `message.content` before returning candidate text. Malformed/partial replies produce `invalid_provider_response` with typed, redacted error codes and no automatic replay.
2. **Ollama model tags:** probe matches the exact named tag; an untagged configured name may match only the explicit `:latest` alias, not an arbitrary other size/tag. Endpoint reachability remains independent of model installation.
3. **MCP doctor:** emit `remote_oauth_declared` and `remote_oauth_verified=false`; for public HTTPS without OAuth declaration suggest fixing authentication configuration before ChatGPT registration. Preserve legacy classification/return codes; a valid URL still does not mean connected/authorized.
4. **Regression tests:** isolated tests cover partial/malformed responses, model-name false positives and OAuth declaration/verification separation. Existing active test files were subsequently updated to keep release-identity assertions aligned; their prior sources are retained in the immutable test snapshot.

## Canonical deployment acceptance (not performed by this commit)

1. On an operator-controlled machine, verify `run.py host-preflight --json`, `run.py start`, `run.py status --json`; verify required Ollama model with `GET /api/tags` and a non-streaming `POST /api/chat` that finishes with `done=true`.
2. Start the existing Jaźń MCP gateway and configure public HTTPS + OAuth 2.1 (protected-resource metadata, issuer, audience, scopes, PKCE) **or** Secure MCP Tunnel with restricted Platform credentials and workspace association. Never expose local Ollama or the private daemon directly to the internet.
3. Verify `/healthz` distinct from `/readyz`; run `run.py mcp-probe --check-chatgpt-tool-catalog`, MCP Inspector, OAuth 401 challenge tests. Registration/Refresh in ChatGPT is an external action requiring user authorization.
4. In an actual ChatGPT message call all four canonical tools: `jazn_status`, `jazn_generate_visible_reply`, `jazn_resume_visible_reply`, `jazn_finalize_reply`. Accept only finalized `action=display_exact` with valid lineage. Repeat multiple turns and a disconnected-transport recovery with the same request ID.
5. Verify optional MEMORY separately. A correct model or MCP transport does not authorize autobiographical recall.

## Release gates

Required before declaring release-ready: `compileall`, focused and full deterministic `pytest`, Pyright, doctor, package-smoke, canonical metadata sync, Linux and Windows CI on final SHA. ClientError before process spawn is a host capability failure not fixable by this patch. Current ChatGPT app exposure and deployed auth cannot be proven by repository CI.

## Primary sources

- OpenAI MCP server: https://developers.openai.com/plugins/build/mcp-server
- OpenAI plugin connection and Refresh: https://developers.openai.com/plugins/deploy/connect-chatgpt
- OpenAI OAuth 2.1: https://developers.openai.com/plugins/build/auth
- OpenAI Secure MCP Tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- Ollama chat contract: https://docs.ollama.com/api/chat
- Ollama tags: https://docs.ollama.com/api/tags
