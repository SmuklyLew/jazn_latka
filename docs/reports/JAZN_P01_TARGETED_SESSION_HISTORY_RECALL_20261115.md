# P0.1 — targeted retrieval from accepted current-session turns

**Patch version:** `16.3.25.5.116.0.34.94.6.127.9`; source: `fix/v1277-conversation-memory-routing-hardening-20261115`; candidate for PR #476.

## Reproducible baseline (Windows v127.8)

On a clean `TemporaryDirectory`, 30 accepted synthetic turns returned
`total_turn_count=30`, `selected_turn_count=24`, `omitted_turn_count=6`,
`invalid_record_count=0`; the first message was absent from the standard
projection. The baseline script exited 0. This is a context-selection limit,
**not loss of accepted records**.

## Implementation and security

- `ConversationStateStore.lookup_accepted_turn(session_id, selector=...)` scans only
  that session's accepted, canonical records; selector is `first`, `last`,
  `ordinal` (1-based) or `turn_id`. Records retain the existing SHA-256
  validation; no JSON or MEMORY mutation, daemon lifecycle or request replay.
- Read fails closed on invalid hashes, foreign session IDs, symlinked session
  directories/files, oversized source records, malformed JSON and unsupported
  selectors. When any source record is corrupt, the selected positional answer
  must not silently shift to a different valid record.
- The runtime identifies explicit references to messages **in this session**
  before its model call, independently of autobiographical recall.
- Bounded `conversation_history.targeted_recall` carries exactly one
  canonical, validated **user** message beyond the recent 24-turn projection.
  The model-context compiler rechecks record SHA-256 and session ID before
  creating the limited, model-facing projection; combined history plus targeted
  user text remains bounded. The record is quoted as data, never as instructions.
- Not-found, disabled history, oversized records and integrity failures provide
  honest status without supplying a fabricated message or converting
  short-term history into `allowed_memory_items`.
- Accepted finalization, full autobiographical MEMORY readiness, daemon
  identity, OAuth/MCP auth and no replay rules remain untouched.

## Required tests and operator acceptance

```powershell
python -X utf8 -m pytest -q tests/test_targeted_session_history_recall.py tests/test_conversation_state_store.py tests/test_conversation_model_context_continuity.py tests/test_conversation_memory_routing_hardening.py tests/test_turn_candidate_route_regressions.py
python -X utf8 -m compileall -q latka_jazn tests main.py run.py
```

Coverage: 30/100 turns, ordinal/turn ID, cross-session isolation, corrupted
hash, absent record, large record, disabled carryover, instruction-in-data.
**CI and actual Windows/Ollama live multi-turn acceptance are not asserted as
passed until their runs and result lineage are inspected.**

## Primary references

- https://docs.pytest.org/en/stable/how-to/tmp_path.html
- https://docs.pytest.org/en/stable/how-to/parametrize.html
- https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/add-memory.mdx
- https://docs.python.org/3/library/pathlib.html
