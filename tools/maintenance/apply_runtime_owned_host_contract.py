from __future__ import annotations

from pathlib import Path


PATH = Path("latka_jazn/core/chat_command_contract.py")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    import_line = "from latka_jazn.core.host_visible_finalization import finalize_host_visible_text\n"
    ownership_import = "from latka_jazn.core.runtime_ownership_contract import build_runtime_ownership_contract\n"
    if ownership_import not in text:
        text = replace_once(
            text,
            import_line,
            import_line + ownership_import,
            label="ownership import",
        )

    text = replace_once(
        text,
        '''    requires_host = chatgpt_result_requires_host_visible_reply(result)\n    turn_id = str(trace.get("turn_id") or runtime_turn.get("turn_id") or final_contract.get("turn_id") or "")\n    trace_id = str(trace.get("trace_id") or runtime_turn.get("trace_id") or final_contract.get("trace_id") or "")\n    timestamp_header = str(trace.get("timestamp_header") or runtime_turn.get("timestamp_header") or final_contract.get("timestamp_header") or "")\n    return {\n''',
        '''    requires_host = chatgpt_result_requires_host_visible_reply(result)\n    detected_intent = str(\n        decision.get("detected_user_intent")\n        or decision.get("intent")\n        or runtime_turn.get("detected_user_intent")\n        or runtime_turn.get("intent")\n        or ""\n    )\n    runtime_route = str(decision.get("route") or runtime_turn.get("runtime_route") or "")\n    ownership = build_runtime_ownership_contract(\n        detected_intent=detected_intent,\n        route=runtime_route,\n    )\n    host_policy = ownership.get("host_visible_generation_contract") or {}\n    host_policy_rules = [str(item) for item in host_policy.get("rules", []) if str(item).strip()]\n    turn_id = str(trace.get("turn_id") or runtime_turn.get("turn_id") or final_contract.get("turn_id") or "")\n    trace_id = str(trace.get("trace_id") or runtime_turn.get("trace_id") or final_contract.get("trace_id") or "")\n    timestamp_header = str(trace.get("timestamp_header") or runtime_turn.get("timestamp_header") or final_contract.get("timestamp_header") or "")\n    return {\n''',
        label="host bridge preamble",
    )

    text = replace_once(
        text,
        '''            "route": decision.get("route") or runtime_turn.get("runtime_route"),\n''',
        '''            "route": runtime_route,\n            "detected_intent": detected_intent,\n''',
        label="runtime summary route",
    )

    text = replace_once(
        text,
        '''        "host_reply_jsonl_shape": {\n''',
        '''        "runtime_ownership_contract": ownership,\n        "host_generation_policy": host_policy,\n        "host_reply_jsonl_shape": {\n''',
        label="ownership payload",
    )

    text = replace_once(
        text,
        '''            "final_text": "<widoczna odpowiedź ChatGPT ułożona na podstawie runtime Jaźni>",\n''',
        '''            "final_text": "<widoczna odpowiedź ułożona zgodnie z runtime_ownership_contract>",\n''',
        label="host reply shape",
    )

    text = replace_once(
        text,
        '''        "host_generation_rules": [\n            "Ułóż widoczną odpowiedź po polsku na podstawie bieżącego runtime result, nie na podstawie starego szablonu.",\n            "Nie twierdź, że lokalny Python wywołał ChatGPT jako funkcję.",\n            "Widoczna odpowiedź MUSI zaczynać się dokładnie od required_visible_prefix/timestamp_header; faza finalizacji odrzuci obcy timestamp i naprawi brakujący.",\n            "Jeżeli runtime_truth_gate blokuje zwykłą odpowiedź, pokaż krótką diagnozę zamiast udawanej wypowiedzi Łatki.",\n        ],\n''',
        '''        "host_generation_rules": [\n            *host_policy_rules,\n            "Nie twierdź, że lokalny Python wywołał ChatGPT jako funkcję.",\n            "Widoczna odpowiedź MUSI zaczynać się dokładnie od required_visible_prefix/timestamp_header; faza finalizacji odrzuci obcy timestamp i naprawi brakujący.",\n            "Jeżeli runtime_truth_gate blokuje zwykłą odpowiedź, pokaż krótką diagnozę hosta zamiast imitować wypowiedź Łatki.",\n        ],\n''',
        label="host generation rules",
    )

    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
