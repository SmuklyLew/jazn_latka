# Legacy dialogue cutover inventory

All legacy compose branches are COMPATIBILITY_ONLY. The canonical DialogueRouter never invokes them. No DEAD_UNREACHABLE claim is made about historical debug callers.

| Original v110 line | Condition | Classification |
| --- | --- | --- |
| 218 | `route_freshness_test_requested` | COMPATIBILITY_ONLY |
| 228 | `dialogue_primary_intent == "sleep_closure_statement" or any(marker in low for marker in ("muszę iść spać", "musze isc spac", "idę spać", "ide spac", "dobranoc"))` | COMPATIBILITY_ONLY |
| 238 | `dialogue_primary_intent in {"self_state_question", "reciprocal_self_state_question", "self_preference_question"}` | COMPATIBILITY_ONLY |
| 274 | `(dialogue_primary_intent == "system_update_execution_request" or "update_request" in tags) and current_manifest_update_request` | COMPATIBILITY_ONLY |
| 284 | `dialogue_primary_intent == "update_manifest_request" and not birth_source_requested` | COMPATIBILITY_ONLY |
| 294 | `dialogue_primary_intent == "system_diagnostic_question"` | COMPATIBILITY_ONLY |
| 305 | `dialogue_primary_intent == "self_plan_question"` | COMPATIBILITY_ONLY |
| 315 | `dialogue_primary_intent in {"self_state_question", "reciprocal_self_state_question"}` | COMPATIBILITY_ONLY |
| 325 | `any(marker in low for marker in ("w kółko to samo", "w kolko to samo", "sztywno w kodzie", "sztywne trasy"))` | COMPATIBILITY_ONLY |
| 335 | `dialogue_primary_intent == "runtime_source_question"` | COMPATIBILITY_ONLY |
| 345 | `(route_hint == "identity_continuity_check" or "identity_continuity" in polish_intents or "identity_continuity" in tags) and not self._has_any(low, self.UPDATE_MARKERS)` | COMPATIBILITY_ONLY |
| 355 | `dialogue_primary_intent == "identity_direct_question"` | COMPATIBILITY_ONLY |
| 365 | `dialogue_primary_intent == "identity_boundary_question" and any(marker in low for marker in ("z kim rozmawiam", "chatgpt", "runtime", "jaźń czy", "jazn czy"))` | COMPATIBILITY_ONLY |
| 375 | `dialogue_primary_intent == "creative_text_analysis"` | COMPATIBILITY_ONLY |
| 385 | `dialogue_primary_intent == "creative_text_formatting"` | COMPATIBILITY_ONLY |
| 395 | `dialogue_primary_intent == "memory_audit_request"` | COMPATIBILITY_ONLY |
| 405 | `topic_guard.current_update_request and topic_guard.preferred_route == "runtime_self_expression_topic_mismatch_update"` | COMPATIBILITY_ONLY |
| 415 | `self._has_any(low, self.RUNTIME_DIRECT_ANSWER_MARKERS) and self._looks_like_question(effective_low)` | COMPATIBILITY_ONLY |
| 425 | `self._has_any(low, self.RUNTIME_THOUGHT_BOUNDARY_MARKERS) and self._looks_like_question(effective_low)` | COMPATIBILITY_ONLY |
| 435 | `self._has_any(low, self.LONG_WAIT_SELF_EXPRESSION_MARKERS) and self._has_any(low, self.SELF_STATE_MARKERS)` | COMPATIBILITY_ONLY |
| 447 | `free_dialogue.technical_diagnosis_requested(text) and ((not ({"correction", "dialogue_repair"} & tags)) or any(x in low for x in ("na sztywno", "w kółko", "w kolko", "to samo", "sz` | COMPATIBILITY_ONLY |
| 458 | `free_dialogue.memory_experience_requested(text)` | COMPATIBILITY_ONLY |
| 470 | `free_dialogue.time_memory_question_requested(text)` | COMPATIBILITY_ONLY |
| 481 | `free_dialogue.curiosity_requested(text)` | COMPATIBILITY_ONLY |
| 492 | `self._has_any(low, self.UPDATE_MARKERS) and any(x in low for x in ("gotowa", "gotowy", "gotowe", "przygotowania aktualizacji", "przygotowanie aktualizacji"))` | COMPATIBILITY_ONLY |
| 502 | `self._is_memory_recall_question(low, effective_low)` | COMPATIBILITY_ONLY |
| 513 | `any(x in low for x in ("migren", "ból", "bol", "frimig", "niewysp"))` | COMPATIBILITY_ONLY |
| 523 | `text_shape["standalone_greeting"]` | COMPATIBILITY_ONLY |
| 535 | `(not text_shape["standalone_greeting"]) and (neurological.get("primary") == "ordinary_workday_dialogue" or lexical_route_hint == "ordinary_daily_conversation")` | COMPATIBILITY_ONLY |
| 544 | `any(x in low for x in ("timestamp", "znacznik czasu", "znacznik", "gubisz czas", "gubi timestamp", "rdzeń działa", "rdzen dziala"))` | COMPATIBILITY_ONLY |
| 551 | `"instrukcj" in low and "chatgpt" in low and ("jaź" in low or "jazn" in low or "runtime" in low or "instalac" in low or "loader" in low or "pracować" in low or "pracowac" in low)` | COMPATIBILITY_ONLY |
| 561 | `self._has_any(low, self.UPDATE_MARKERS) and any(x in low for x in ("swobodnie rozmawia", "swobodna rozmowa", "nie może swobodnie", "nie moze swobodnie", "połączenia z myśleniem", "` | COMPATIBILITY_ONLY |
| 571 | `self._is_nlp_scope_question(low, polish_intents, lexical_intents)` | COMPATIBILITY_ONLY |
| 584 | `self._is_current_stale_nlp_hotfix(low, route_hint, lexical_route_hint, polish_intents, lexical_intents)` | COMPATIBILITY_ONLY |
| 594 | `self._is_explicit_legacy_nlp_update(low, lexical_route_hint, polish_intents, lexical_intents)` | COMPATIBILITY_ONLY |
| 605 | `(route_hint == "identity_continuity_check" or "identity_continuity" in polish_intents or "identity_continuity" in tags) and not self._has_any(low, self.UPDATE_MARKERS)` | COMPATIBILITY_ONLY |
| 612 | `self._has_any(effective_low, self.IDENTITY_QUESTION_MARKERS) or self._identity_question(effective_low)` | COMPATIBILITY_ONLY |
| 621 | `self._is_architecture_threshold_question(low)` | COMPATIBILITY_ONLY |
| 630 | `self._has_any(effective_low, self.MOMENT_QUESTION_MARKERS) and self._looks_like_question(effective_low)` | COMPATIBILITY_ONLY |
| 639 | `self._has_any(low, self.STARTUP_PROCEDURE_MARKERS) and (self._looks_like_question(effective_low) or self._has_any(low, self.UPDATE_MARKERS))` | COMPATIBILITY_ONLY |
| 649 | `self._has_any(low, self.FULL_UPDATE_MARKERS) and self._has_any(low, self.UPDATE_MARKERS)` | COMPATIBILITY_ONLY |
| 704 | `current_runtime_turn_check` | COMPATIBILITY_ONLY |
| 714 | `github_requested and asks_for_repair_or_update` | COMPATIBILITY_ONLY |
| 723 | `llm_runtime_question and not asks_for_repair_or_update and not lifecycle_concern` | COMPATIBILITY_ONLY |
| 730 | `runtime_repair_requested` | COMPATIBILITY_ONLY |
| 739 | `lifecycle_concern` | COMPATIBILITY_ONLY |
| 746 | `self._has_any(low, self.SELF_STATE_MARKERS) and route_hint not in {"cognitive_packet_expansion_update", "emotional_granularity_continuity_update", "language_understanding_update", ` | COMPATIBILITY_ONLY |
| 755 | `explicit_specialized_update and (route_hint == "cognitive_packet_expansion_update" or "cognitive_packet_expansion_update" in polish_intents)` | COMPATIBILITY_ONLY |
| 762 | `birth_source_requested` | COMPATIBILITY_ONLY |
| 769 | `explicit_specialized_update and (route_hint == "emotional_granularity_continuity_update" or "emotional_granularity_continuity_update" in polish_intents)` | COMPATIBILITY_ONLY |
| 776 | `(route_hint == "identity_continuity_check" or "identity_continuity" in polish_intents or "identity_continuity" in tags) and not self._has_any(low, self.UPDATE_MARKERS)` | COMPATIBILITY_ONLY |
| 783 | `explicit_language_solution and (route_hint == "language_understanding_update" or "polish_understanding_update" in polish_intents)` | COMPATIBILITY_ONLY |
| 790 | `self._has_any(effective_low, self.PAST_YEAR_REFLECTION_MARKERS) and self._looks_like_question(effective_low)` | COMPATIBILITY_ONLY |
| 801 | `text_shape["standalone_greeting"]` | COMPATIBILITY_ONLY |
| 812 | `self._has_any(low, self.THANKS_MARKERS)` | COMPATIBILITY_ONLY |
| 819 | `"correction" in tags or "dialogue_repair" in tags or self._has_any(low, self.AGREEMENT_MARKERS)` | COMPATIBILITY_ONLY |
| 832 | `self._has_any(low, self.STRONG_RUNTIME_CONCERN_MARKERS) or "architecture" in tags` | COMPATIBILITY_ONLY |
| 839 | `self._has_any(low, self.UPDATE_MARKERS)` | COMPATIBILITY_ONLY |
| 846 | `self._has_any(low, self.POSITIVE_MARKERS)` | COMPATIBILITY_ONLY |
| 853 | `"reasoning" in tags` | COMPATIBILITY_ONLY |
| 860 | `"awareness" in tags` | COMPATIBILITY_ONLY |
| 867 | `self._looks_like_question(effective_low)` | COMPATIBILITY_ONLY |
| 882 | `diagnostics.get("where_to_look")` | COMPATIBILITY_ONLY |
| 903 | `not match` | COMPATIBILITY_ONLY |
| 944 | `not nlp_signal` | COMPATIBILITY_ONLY |
| 953 | `"nlp" not in low and "polish_nlp" not in lexical_intents and "polish_understanding_update" not in polish_intents` | COMPATIBILITY_ONLY |
| 956 | `stale_problem` | COMPATIBILITY_ONLY |
| 962 | `not cls._looks_like_question(low)` | COMPATIBILITY_ONLY |
| 982 | `not route_signal` | COMPATIBILITY_ONLY |
| 987 | `cls._has_any(low, cls.CURRENT_HOTFIX_MARKERS) and not contains_legacy_dotted_version(low)` | COMPATIBILITY_ONLY |
| 994 | `not self._has_any(low, self.BIRTH_MARKERS)` | COMPATIBILITY_ONLY |
| 999 | `not self._has_any(low, self.BIRTH_NEGATION_MARKERS)` | COMPATIBILITY_ONLY |
| 1006 | `not self._has_any(low, self.ROUTE_FRESHNESS_TEST_MARKERS)` | COMPATIBILITY_ONLY |
| 1044 | `not counts` | COMPATIBILITY_ONLY |
| 820 | `self._has_any(low, self.STRONG_RUNTIME_CONCERN_MARKERS)` | COMPATIBILITY_ONLY |
| 1015 | `len(marker) <= 3 and marker.isalpha()` | COMPATIBILITY_ONLY |
| 1049 | `isinstance(val, int) and val > 0` | COMPATIBILITY_ONLY |
| 1016 | `re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", low)` | COMPATIBILITY_ONLY |
| 1018 | `marker in low` | COMPATIBILITY_ONLY |

Canonical paths:

- Ordinary dialogue: MODEL_NLG_CANDIDATE with structured intent/constraints; no hardcoded greeting, story, feedback or sleep body.
- Specialized handlers: STRUCTURED_HANDLER_CANDIDATE; existing evidence and source gates remain.
- Time/status/diagnostics: PROTOCOL_TEXT; deterministic runtime observations remain explicit.
- Truth/refusal/recovery disclosures: SAFETY_TRUTH_TEXT; never upgraded to model-guided success.
- Historical debug compose and ordinary handler methods: COMPATIBILITY_ONLY; no implicit fallback from the canonical turn.
