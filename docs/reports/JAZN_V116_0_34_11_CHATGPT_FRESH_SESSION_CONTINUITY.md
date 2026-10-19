# ChatGPT fresh-session continuity recovery (v16.3.25.5.116.0.34.11)

## Observed failure and scope

The independent ChatGPT sandbox activation report (2026-10-19) recorded
accepted `display_exact` alongside
`session_advanced_or_phase_one_checkpoint_missing` and
`session_checkpoint_saved=false`. This is a concrete partial-continuity
observation, not evidence of a broken daemon or lost autobiographical MEMORY.

In `_build_session_continuity_commit`, `load_or_create()` can return a
transient session without writing a canonical checkpoint. The previous path
only replaced the daemon snapshot when a disk checkpoint had *already*
been resurrected. On a fresh session, phase-1 could therefore bind to one
created-at/expires-at pair while phase-2 reconstructed a different pair,
giving different hashes even without a second user message.

## Fix

When no existing checkpoint is loaded, persist a baseline session before
constructing the phase-1 CAS commitment. Always bind the commitment to the
canonical persisted snapshot; never bind a phase-1 continuity claim when
that initial checkpoint write fails.

Preserve the existing fail-closed CAS for genuinely advanced/changed
sessions. Conversation-state append and accepted visible-text finalization
remain separate from session-checkpoint success. This patch neither
invents MEMORY readiness nor repairs missing ChatGPT host execution.

## Acceptance

- Fresh phase-1 persists a canonical checkpoint and phase-2 can advance it.
- Existing checkpoint wins over stale daemon state, without overwriting it.
- Delayed finalizer does not overwrite a newer session (existing regression).
- Full pytest, compileall, Pyright, doctor, package-smoke, release metadata
  synchronization and Ubuntu/Windows CI remain mandatory.
- Live, five-turn ChatGPT MCP continuity and external OAuth exposure are
  separate gates and cannot be inferred from green unit tests.

## External references

- SQLite transaction semantics: https://www.sqlite.org/lang_transaction.html
- OpenAI MCP server: https://developers.openai.com/plugins/build/mcp-server
- MCP Tasks: https://tasks.extensions.modelcontextprotocol.io/specification/2026-07-28/tasks
