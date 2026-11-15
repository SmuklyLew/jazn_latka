# P0.2.1 — type-safe uninitialized-store boundary

The CI Pyright gate on commit `8127e37e1929710c599f5289606a49772c81f931` reported an argument type error: an existing P0.2 regression intentionally called `_with_targeted_session_recall(None, ..., allow_history=False)`, but the helper annotated its `store` parameter as non-optional.

This patch changes the helper annotation to `ConversationStateStore | None`, and distinguishes `history_disabled` from `history_unavailable` without returning any user text when the store is absent. The model-context sanitizer permits only those explicit status labels. No memory state, turn, request, acceptance or finalization is created.

Run: `python -X utf8 -m pytest -q tests/test_runtime_session_store_unavailable_guard.py tests/test_p02_nlp_nlg_source_greeting_and_finalization.py tests/test_release_hardening_integrity_pipeline.py`.

Full CI and actual Ollama dialog acceptance still must be checked on the new SHA.

References: https://docs.python.org/3/library/typing.html ; https://docs.pytest.org/en/stable/how-to/parametrize.html .
