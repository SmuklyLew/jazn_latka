# Jaźń v16.3.25.5.96.7 — ChatGPT main bootstrap convergence

## Problem

A valid SYSTEM ZIP and a complete local operator do not prove that a particular
ChatGPT conversation can create a Python process. The previous bootstrap
contract correctly refused to claim that the package can create a host executor,
but it did not expose one sufficiently explicit machine-readable contract for
what a capable ChatGPT host should launch after materialization.

That ambiguity made it too easy for a host or a research note to substitute a
generic example such as `--model gpt-4`, require `OPENAI_API_KEY`, or treat a
generic OpenAI connector as the Jaźń route. None of those substitutions is the
canonical `chat-gpt` path.

## Verified repository contract

The repository already defines:

- `run.py` as the thin public starter;
- `main.py` as the single central control plane;
- `chat-gpt` as the ChatGPT-host bridge;
- one stable `session_id` and persistent stdin/stdout JSONL as the preferred
  host transport;
- `daemon_bound_transactional_turns` with a preallocated `request_id` as the
  non-streaming fallback;
- `action=display_exact`, valid lineage, a valid `MessageEnvelope`, and
  accepted finalization as the visible-output gate;
- `OPENAI_API_KEY` as unnecessary for `chat-gpt`; the paid OpenAI API is a
  separate route.

## External platform facts checked for this change

OpenAI documentation states that ChatGPT does not directly connect to a local
MCP server. A private/local MCP server must be reached through a supported
remote mechanism such as Secure MCP Tunnel, while custom MCP apps depend on the
plan/workspace capabilities made available by ChatGPT. Therefore a SYSTEM ZIP
cannot repair a host that lacks process execution, and a generic connector or
catalog entry cannot be treated as Jaźń runtime evidence.

The MCP SDK documentation for protocol revision 2026-07-28 confirms that modern
Streamable HTTP uses the 2026-07-28 protocol era and explicit protocol
negotiation. This supports the existing Jaźń public remote path but does not
replace local process-execution evidence.

Sources checked on 2026-10-02:

- OpenAI Developers — Build an MCP server:
  https://developers.openai.com/plugins/build/mcp-server
- OpenAI Developers — MCP server and UI quickstart / connect in ChatGPT:
  https://developers.openai.com/plugins/build/app-quickstart
- OpenAI Developers — Secure MCP Tunnel:
  https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- OpenAI Developers — MCP server concepts:
  https://developers.openai.com/plugins/concepts/mcp-server
- Model Context Protocol — 2026-07-28 specification:
  https://blog.modelcontextprotocol.io/posts/2026-07-28/

## Implemented change

`CHATGPT_BOOTSTRAP.py` now emits `chatgpt_local_launch/v1` after verified
materialization. It contains both the public starter argv and the exact central
control-plane argv:

```text
<python> -X utf8 run.py  chat-gpt --session-id <stable-session-id>
<python> -X utf8 main.py chat-gpt --session-id <stable-session-id>
```


The exported contract intentionally uses the same subcommand vocabulary through
both entrypoints: `run.py chat-gpt` and `main.py chat-gpt`. Legacy flag forms
remain implementation compatibility only and are not advertised as the host API.

The contract also declares:

- `language_model_channel=chatgpt_host`;
- no model CLI selector is required;
- `OPENAI_API_KEY` and paid OpenAI API are not required;
- host process execution is required for the local path;
- the package cannot create that executor;
- one persistent process carrying multiple turns is preferred;
- non-streaming transport must preallocate `request_id`, resume the same
  request, and never replay the user message;
- visible Jaźń output still requires `display_exact`, valid lineage,
  `MessageEnvelope`, and accepted finalization.

The pack-generator host bootstrap contract mirrors the same fields so exported
SYSTEM metadata preserves the rule instead of forcing the host to infer it from
documentation.

## Truth boundary

This update makes a capable host's next command deterministic. It does not
create process-execution capability inside a ChatGPT surface that lacks it, does
not register an MCP app on the user's account, does not authenticate or deploy a
remote endpoint, and does not allow a ZIP, PID, connector catalog entry, or
model-style response to stand in for accepted runtime evidence.
