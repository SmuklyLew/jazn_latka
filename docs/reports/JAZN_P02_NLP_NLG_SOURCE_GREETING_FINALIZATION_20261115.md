# Jaźń P0.2 — NLP/NLG source + greeting and runtime finalization safety

**Branch:** `fix/v1277-conversation-memory-routing-hardening-20261115` · **Version:** `16.3.25.5.116.0.34.94.6.127.10` · **Baseline:** `f155be3f12540815071eb20935252b322da06a21`

## Confirmed problems

1. Real Windows Ollama output contained a duplicated `🌿 Łatka` speaker prefix, even though the runtime already supplies `MessageEnvelope`.
2. A greeting plus question about provenance was routed to `RuntimeSourceHandler`, which answered provenance but omitted the greeting.
3. P0.1 full Ubuntu release-hardening on commit `b7ddd09c3050c04ad125ea94c19aab1b4e36da3d` failed six existing final-integrity fixture tests with `AttributeError: ConversationRunner has no attribute conversation_state_store`. The fixture intentionally constructs a no-carryover runner without a store. The full job had **4168 PASS, 6 FAIL, 25 SKIP**: https://github.com/SmuklyLew/jazn_latka/actions/runs/43765512122

## Implementation

- For a fresh, no-carryover turn, `ConversationRunner` never accesses `conversation_state_store`; a user request for session history gets explicit `history_disabled` instead. The normal verified-store path stays intact.
- `RuntimeSourceHandler` answers explicit greeting + source questions as a deterministic response, and clearly discloses that the text is **not** attributed to the language model. Existing `runtime_source_question` protected-intent policy remains unchanged.
- `clean_model_generated_body` removes a **single** structural author prefix preceding recognizable greetings, while preserving in-body mentions and subject-like prose. The runtime-owned MessageEnvelope still authors the only verified header.
- New tests cover greeting+source, provenance vs external research, exact quote without checkpoint, one/two repeated labels, envelope rendering, and disabled session history. No previous test assertions are removed or weakened.

## Evidence and outstanding work

New dedicated tests: `tests/test_p02_nlp_nlg_source_greeting_and_finalization.py`.
Full targeted/Windows/Linux CI must be confirmed on this patch SHA; no claims of tests run locally in ChatGPT. Real Ollama dialogue quality and arbitrary multi-intent requests outside provenance remain open acceptance criteria.

## Primary sources

- https://docs.pytest.org/en/stable/how-to/parametrize.html
- https://docs.python.org/3/library/re.html
- https://docs.ollama.com/api/chat
