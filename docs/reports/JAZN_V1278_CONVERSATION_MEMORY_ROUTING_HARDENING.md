# Jaźń V127.8 — conversation / session-memory routing hardening

**Branch:** `fix/v1277-conversation-memory-routing-hardening-20261115`  
**Tested baseline SHA:** `3cf12209bc71378e28b87f91004fb5473a2cf97b`  
**Status:** Code patch for review; full Windows/Ollama and release acceptance still required.

## Evidence from 2026-11-15 local operator tests

- Windows/Python 3.14.4 SYSTEM V127.7: verified integrity, `active_trusted` daemon, local `gemma3:latest`.
- A question about the origin of the generated answer was incorrectly classified `external_research_request`.
- `is_session_dialogue_reference("Czy pamiętasz moją pierwszą wiadomość w tej sesji?")` returned `False`; the primary route was `memory_experience_question`.
- `ConversationStateStore.load_context_projection("v1277-dialogue-smoke-02")` returned 3 accepted turns, 0 omitted, 0 invalid and the exact first user message.
- The misrouted model answer failed with `memory_claim_without_allowed_memory_payload` and `memory_claim_without_grounded_items`.
- An ordinary Ollama turn returned `model_generated=True`, `runtime_model_guided`, `final_integrity_valid=True`; visible text contained repeated `🌿 Łatka` labels.

## Implemented changes

1. Questions about the source of the current answer are not treated as generic web research.
2. Explicit anchors to first/earlier messages in this session choose short-term `contextual_continuation_question`, not autobiographical recall.
3. The model context carries the session ID and instructs use of accepted `conversation_history.turns`, without making ungrounded autobiographical claims.
4. Leading model-generated duplicate speaker labels are removed only under structural/prefix conditions. Runtime-owned MessageEnvelope and timestamps remain authoritative.
5. Existing fail-closed autobiographical memory grounding, daemon identity, and finalization are not bypassed.

## CI investigation (2026-11-15)

- The active-test governance check rejects release-coupled test filenames; the new test is therefore named by its stable purpose, not by version.
- The MCP deployment contract is kept in lockstep with PACKAGE_VERSION_FULL; unchanged runtime v127.7 in deployment.contract.json failed the persistent-runtime E2E and docs-truth gates.
- Ubuntu memory-cloud CI cannot provision Python 3.12.9 on Ubuntu 26.04; this failure is not part of the local NLP patch and remains separately gated.

## Acceptance gates (NOT YET EXECUTED)

```powershell
python -X utf8 -m pytest -q tests/test_conversation_memory_routing_hardening.py tests/test_conversation_model_context_continuity.py tests/test_turn_candidate_route_regressions.py tests/test_memory_experience_recall_handler.py
python -X utf8 -m compileall -q latka_jazn tests main.py run.py
```

Required before release: full NLP/memory/continuity/finalization regression, Windows/Linux CI, cleanroom staging, canonical metadata sync + idempotency, and two consecutive accepted same-session Ollama turns including exact first-message recall. Test missing-history, historical-memory refusal, author-label hygiene, reconnect/resume and no replay of failed requests.

Do not hand-edit `PACKAGE_INTEGRITY_MANIFEST.json` or `SOURCE_PROVENANCE.json`, mutate private MEMORY, or restart the existing operator's trusted daemon.

## References

- https://docs.python.org/3/howto/regex.html
- https://docs.pytest.org/en/stable/how-to/parametrize.html
- https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/persistence.mdx
- https://github.com/ollama/ollama/blob/main/docs/api.md
- https://docs.github.com/en/rest/repos/contents
