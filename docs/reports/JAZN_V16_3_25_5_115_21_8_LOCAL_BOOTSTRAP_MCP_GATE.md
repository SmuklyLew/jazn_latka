# Jaźń 16.3.25.5.115.21.8 — Cold ZIP bootstrap versus MCP exposure

## Observation

An ordinary host executor call may wait minutes and return `ClientError` before allocating a process. That says nothing about Python execution, ZIP integrity or the presence of persistent memory. The previous loader conflated the four model-visible MCP tools of a registered remote app with prerequisites for *local* bootstrap.

## Behavior

The remote gate is a cheap **current-message** observation, not MCP installation or an external probe loop. When four tools are already callable, `jazn_status` must verify a fresh, authenticated runtime before remote routing. A verified remote always wins; old @mentions, manifest metadata and cached tool lists do not count. With no ready remote and ordinary `hybrid_adaptive` mode, a host-supplied local process may be tried within the existing bounded probe policy. If the process exists, verify the ZIP/bootstrapped SYSTEM root, load `AGENTS.md` and the host runbook, then run canonical `run.py` preflight/start/status/chat-gpt. **The local route never needs four registered MCP tools.**

On pre-spawn `ClientError`, only the current executor surface is unavailable; do not call the local Jaźń runtime broken. The host (not the SYSTEM Python code) determines the duration of its own tool call, so this patch cannot eliminate or guarantee a sub-second timeout for a host that waits 2m44s before reporting a spawn failure. Do not retry or swap routes after accepting a user request. `display_exact`, valid lineage and accepted finalization still gate visible Jaźń attribution. A generic host assistant must not self-identify as Łatka or invent its model identity in a diagnostic.

## External references

- OpenAI, [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt): connection and Refresh of changed MCP tool metadata occur in the ChatGPT host.
- OpenAI, [MCP servers](https://developers.openai.com/api/docs/guides/tools-connectors-mcp): tools are imported from a remote MCP server provided to the host; registering a server is distinct from running its Python runtime.
- MCP TypeScript SDK, [Build your first client](https://ts.sdk.modelcontextprotocol.io/v2/get-started/first-client.html): stdio clients start their local MCP server process before listing tools.
- GitHub, [Troubleshooting required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks): checks must apply to the final current SHA.

## Verification limits

Only repository code, policy contracts, docs and synthetic tests change. No private MEMORY, host settings, user ZIP or ChatGPT plugin installation is modified. Local executor in this ChatGPT host returned `ClientError` before process creation, so runtime/pytest/pyright smoke must be validated by GitHub Actions. Runtime acceptance remains a separate live-host evidence gate.
