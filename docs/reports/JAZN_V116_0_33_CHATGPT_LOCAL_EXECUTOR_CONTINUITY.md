# Jaźń v16.3.25.5.116.0.33 — ChatGPT local-executor continuity

## Goal

Keep ChatGPT ordinary-chat as the language-model channel (no OpenAI API key),
using the complete remote MCP capability set only when actually callable in the
current turn. Otherwise use bounded, generation-scoped local executor probing,
verified SYSTEM bootstrap, daemon-bound transactional turns and accepted phase-2.
No package code can grant an executor to a host that does not expose one.

## Improvements

1. The current-turn memory-excerpt validator now detects explicit self-state
   language with word-boundary-aware matching. Technical prompts containing
   `na tym` or `na tych` no longer incorrectly match `a ty`.
2. Phase-2 now exports independent `visible_reply_accepted`,
   `session_checkpoint_saved` and `continuity_readiness`, without weakening
   durable accepted-turn or `display_exact` authority.
3. A stale/non-matching continuity CAS reports `degraded_continuity` and
   `replay_allowed=false`; no last-writer-wins overwrite or phase-1 replay.
4. Host presentation forwards the truthful continuity state when an accepted
   host-finalized result exists. Missing data becomes `not_verified`.

## Host integration and next gates

- Prefer the actual four-tool remote Jaźń runtime if fully exposed and freshly
  ready in the current ChatGPT message, otherwise bounded local probes.
- Attempt one primary executor and no more than one **independent** alternative.
  `ClientError` before spawn does not prove filesystem loss or a bad ZIP.
- Use an immutable stable `session_id` per *conversation*, with one unique
  `request_id` per turn. If the host cannot supply a durable conversation ID,
  do **not** substitute a shared global ID for cross-conversation continuity.
- Preserve the original `request_id` through pending poll, failed stdout,
  regeneration and finalization. Never replay the user message after phase-1.
- Prefer compact `host_packet` outputs for CLI transport; collect verbose
  JSON/diagnostics separately and do not strip required integrity evidence.
- `display_exact` describes accepted authorship, not proven checkpoint
  persistence. Surface `degraded_continuity` without falsely claiming memory.
- MEMORY remains separate and optional; autobiographical claims require its
  independent verified native source. No private memory is distributed here.

## Acceptance

Run `python -X utf8 -m compileall -q latka_jazn tests main.py run.py`,
`python -X utf8 -m pytest -q -m "not live_model and not live_mcp"`,
Pyright, doctor, package smoke, and GitHub Actions cross-host gates. Additionally
run a real ChatGPT five-turn sequence with consecutive accepted finals and
persisted checkpoint counters, followed by executor-failure, stdout-loss,
concurrent-finalization and process-restart fault injection. Passing unit tests
alone does not establish cross-chat persistence.

## Sources

OpenAI Shell: https://developers.openai.com/api/docs/guides/tools-shell
OpenAI custom MCP connectors: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt
