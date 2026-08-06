from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"normalize_anchor_count:{path}:{count}:{old[:100]!r}")
    write(path, text.replace(old, new, 1))


# Correct one escaped source literal produced by the staging generator.
replace_once(
    "latka_jazn/core/handlers/post_update_coverage_audit_handler.py",
    '            "\n".join(lines),',
    '            "\\n".join(lines),',
)

# Keep Pyright narrowing stable across optional mapping values.
replace_once(
    "latka_jazn/core/handlers/external_tool_assistance_handler.py",
    '''        report = ctx.get("dialogue_intent_report") if isinstance(ctx.get("dialogue_intent_report"), dict) else {}
        tool_context = report.get("external_tool_context") if isinstance(report.get("external_tool_context"), dict) else {}
        tools = [str(item) for item in tool_context.get("requested_tools", [])]
''',
    '''        report_value = ctx.get("dialogue_intent_report")
        report: dict[str, Any] = report_value if isinstance(report_value, dict) else {}
        tool_context_value = report.get("external_tool_context")
        tool_context: dict[str, Any] = tool_context_value if isinstance(tool_context_value, dict) else {}
        tools = [str(item) for item in tool_context.get("requested_tools", [])]
''',
)
replace_once(
    "latka_jazn/mcp/tools/jazn_finalize_reply.py",
    "        bridge = presentation.get('chatgpt_host_bridge') if isinstance(presentation.get('chatgpt_host_bridge'), dict) else {}\n",
    "        bridge_value = presentation.get('chatgpt_host_bridge')\n        bridge: dict[str, Any] = bridge_value if isinstance(bridge_value, dict) else {}\n",
)

# Generic connector markers are parsed structurally. They must not become a
# competing lexical primary intent in RouteContractMatrix.
lexicon_path = ROOT / "latka_jazn/resources/nlp/polish_dialogue_route_lexicon.json"
lexicon = json.loads(lexicon_path.read_text(encoding="utf-8"))
lexicon.get("intents", {}).pop("external_tool_assistance_request", None)
lexicon["compound_rules"] = [
    rule
    for rule in lexicon.get("compound_rules", [])
    if "external_tool_assistance_request" not in list(rule.get("requires", []))
]
lexicon_path.write_text(json.dumps(lexicon, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Coverage questions need a semantic pattern, not only exact phrases. The gate
# is evaluated before broad diagnostic and route-matrix fallbacks.
replace_once(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "        has_post_update_coverage=self._has_any(norm,folded,self.POST_UPDATE_COVERAGE_AUDIT_TERMS) and (has_update or 'patch' in folded or 'aktualiz' in folded)\n",
    '''        has_post_update_coverage = (
            (has_update or "patch" in folded or "aktualiz" in folded)
            and any(marker in folded for marker in (
                "pominie", "kompletnosc", "czego nie objal", "nie objal", "nie objela",
            ))
        )
''',
)
replace_once(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "        effective_update = bool(update and component_report.explicit_execution and not component_report.negated_actions)\n",
    "        effective_update = bool(update and not component_report.negated_actions and (component_report.explicit_execution or intent == 'system_update_execution_request'))\n",
)
replace_once(
    "latka_jazn/nlp/dialogue_intent_classifier.py",
    "        route_contract_hint = self.route_contract_matrix.classify(norm)\n",
    '''        completion_update_execution = (
            has_update
            and any(marker in folded for marker in (
                "przygotuj", "dokonc", "dokoncz", "uzupeln", "dodaj brakuj",
            ))
        )
        if completion_update_execution:
            return report(
                norm, folded, "system_update_execution_request",
                ["jawne polecenie przygotowania lub dokończenia aktualizacji"],
                0.95, update=True, diag=has_diag,
                speech_act=speech.speech_act, question_object="system_update",
            )
        route_contract_hint = self.route_contract_matrix.classify(norm)
''',
)

# Exhausting the single retry budget must be explicit and auditable.
replace_once(
    "latka_jazn/core/chat_command_contract.py",
    "        release_claimed_host_request(config.root, turn_id=reply['turn_id'])\n        return None, [f'finalization:{item.code}' for item in finalization.violations]\n",
    '''        release_claimed_host_request(config.root, turn_id=reply['turn_id'])
        terminal_errors = [f'finalization:{item.code}' for item in finalization.violations]
        if regeneration.reason == 'regeneration_budget_exhausted':
            terminal_errors.insert(0, 'host_regeneration:host_regeneration_budget_exhausted')
        return None, terminal_errors
''',
)

# A regeneration is a new continuation phase. Reusing the first token would
# weaken replay protection, so issue a fresh token for the same immutable hash.
replace_once(
    "latka_jazn/mcp/tools/jazn_finalize_reply.py",
    "    HostRequestStoreError,\n    resolve_continuation_token,\n",
    "    HostRequestStoreError,\n    issue_continuation_token,\n    resolve_continuation_token,\n",
)
replace_once(
    "latka_jazn/mcp/tools/jazn_finalize_reply.py",
    "        bridge: dict[str, Any] = bridge_value if isinstance(bridge_value, dict) else {}\n        return {\n",
    '''        bridge: dict[str, Any] = bridge_value if isinstance(bridge_value, dict) else {}
        retry_continuation = issue_continuation_token(
            runtime_root,
            turn_id=str(binding["turn_id"]),
            request_contract_hash=request_contract_hash,
        )
        return {
''',
)
replace_once(
    "latka_jazn/mcp/tools/jazn_finalize_reply.py",
    "                'state': 'regenerate', 'continuation_token': continuation_token,\n",
    "                'state': 'regenerate', 'continuation_token': retry_continuation['continuation_token'],\n                'expires_at_utc': retry_continuation.get('expires_at_utc'),\n",
)

# The contract-level E2E fixture must mimic the secure gateway response shape,
# including the nested presentation packet, and use the fresh retry token.
replace_once(
    "tests/test_chatgpt_mcp_end_to_end_v96.py",
    "    packet = build_chatgpt_host_presentation_packet(presented)\n    assert packet[\"action\"] == \"generate_then_finalize\"\n\n    generated = jazn_generate_visible_reply.run(\n",
    "    packet = build_chatgpt_host_presentation_packet(presented)\n    assert packet[\"action\"] == \"generate_then_finalize\"\n    presented[\"chatgpt_host_presentation\"] = packet\n\n    generated = jazn_generate_visible_reply.run(\n",
)
replace_once(
    "tests/test_chatgpt_mcp_end_to_end_v96.py",
    "    second = jazn_finalize_reply.run(\n        root=tmp_path,\n        continuation_token=token,\n",
    "    second = jazn_finalize_reply.run(\n        root=tmp_path,\n        continuation_token=first[\"structuredContent\"][\"continuation_token\"],\n",
)

print(json.dumps({"ok": True, "normalized": True}, ensure_ascii=False))
