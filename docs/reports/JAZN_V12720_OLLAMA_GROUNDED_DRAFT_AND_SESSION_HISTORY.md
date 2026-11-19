# Jaźń v127.20 — bounded self-state draft and accepted session history

## Source and observed PC regression

Source branch: fix/v12719-ollama-self-state-validated-retry-20261119
Source SHA: 1622940ecb6b9acf5c05eedd7490aed49d5f7e66
Runtime version: 16.3.25.5.116.0.34.94.6.127.20

The Windows 11 Ollama Gemma 3 acceptance run on 2026-11-19 showed:
- Turn 1, request 0e12352d-d6f9-4579-a2ff-41c4ef71f08c: FINALIZATION_REJECTED, classified_non_dynamic_response, missing_required_components_for_intent (operational_state, truth_boundary), model_retry attempted, canonical persistence false.
- Turn 2, request e8f4a466-6831-41d2-aecc-96d47465bb49: completed and canonically persisted, but the model positively claimed to see a prior session-history message for which no accepted record was available.
- Version v127.19 tests and release-hardening were green for an older test scope; a real Gemma 3 two-turn acceptance run exposed missing end-to-end coverage.

## Production fixes

1. RecoveryPolicy validates the SelfStateHandler result before authorizing a model-facing draft, and does so only for the self-state retry intent allowlist. The unaccepted model answer does not become evidence.
2. ModelGuidedResponseSynthesizer exposes verified_self_state_draft only with internal validated-handler provenance.
3. LocalModelContextCompiler carries the field through a bounded budget, with an allowlist of required/missing component IDs, a 1100-character limit, no unrelated dictionary keys, and a privacy-pattern check. It is retained in minimal context selection rather than being silently dropped with low-priority content.
4. LocalLlmAdapter includes the verified field in the system JSON context and retains its role as an **untrusted language candidate**; independent answer validation and finalization remain compulsory.
5. LocalLlmAdapter no longer promotes unverified legacy previous_user_text/previous_assistant_text into Ollama role messages. Only the canonical accepted-turn projection is sent as conversation history.
6. RuntimeAnswerValidator rejects **positive** assertions about a previously recorded session message if the runtime did not supply an accepted-turn projection or validated targeted lookup; absence disclosures remain allowed to be evaluated by the other validator rules.

## Authority and privacy boundaries

- No MEMORY files, operational SQLite, daemon state or Windows installation are changed by this source patch.
- The model is not a source of historical evidence and cannot commit a turn.
- Model output is a candidate. No bypass of RuntimeAnswerValidator, RuntimeTruthGate, IntegrityConsensus, finalization or persistence.
- The validated draft is runtime-owned self-state material, **not** raw memory, a user-secret or a general candidate transcript. Unrecognized fields are removed by the bounded compiler.
- Runtime claims of session history use accepted canonical records, not model memory or legacy dialogue hints.

## Regression and release gates

New test module: tests/test_v12720_ollama_grounded_context_history.py
- bounded self-state draft remains model-visible, while private keys/paths/tokens are discarded;
- unsupported or oversized draft is excluded;
- adapter request contains the verified draft;
- no accepted turn means no legacy history replay;
- accepted turn becomes user/assistant role messages;
- validator rejects ungrounded session-history claims and permits explicit uncertainty;
- prior retry failure cannot bypass existing truth/finalization gates.

The previous tests/test_ollama_chat_experience.py is retained verbatim in tests/archive/v12719_pre_v12720 before the active test's accepted-history fixture was updated.

Required checks (statuses must come from actual execution, not source-file inspection):
- targeted pytest for the above and existing Ollama/session tests;
- Python compilation, Pyright, deterministic full release-hardening and integrity/provenance;
- actual Windows Ollama gemma3:latest two-turn acceptance with the *same* session ID;
- an accepted-turn reconnect verification and negative history claim test;
- no claim of autobiographical MEMORY readiness without verified source.

## References

- Ollama chat: https://docs.ollama.com/api/chat
- GitHub Actions logs: https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs
- Source of truth: latka_jazn/core/conversation_state_store.py; see the SHA validated by release CI.
