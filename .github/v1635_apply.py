from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def put(path: str, value: str) -> None:
    (ROOT / path).write_text(value, encoding="utf-8")


def one(path: str, old: str, new: str) -> None:
    value = text(path)
    if value.count(old) != 1:
        raise RuntimeError(f"{path}: expected one match for {old[:70]!r}, got {value.count(old)}")
    put(path, value.replace(old, new, 1))


def rx(path: str, pattern: str, replacement: str) -> None:
    value, count = re.subn(pattern, replacement, text(path), count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{path}: expected one regex match for {pattern[:70]!r}, got {count}")
    put(path, value)


def lexicon() -> None:
    path = ROOT / "latka_jazn/resources/nlp/polish_dialogue_route_lexicon.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = "polish_dialogue_route_lexicon/v2"
    data["truth_boundary"] = (
        "Kanoniczny leksykon minimalnych polskich kontraktów tras. Rozróżnia intencję, źródło i granicę prawdy; "
        "nie jest pełnym słownikiem języka polskiego ani zamiennikiem modelu językowego."
    )
    specs = {
        "self_preference_question": (
            "Preferencja Łatki: remembered/canonical/current/inferred/unknown.",
            ["co najbardziej lubisz", "co lubisz", "co wolisz", "jaki jest twój ulubiony kolor", "jakie masz preferencje", "co wybierasz", "co ci się podoba"],
        ),
        "self_origin_question": (
            "Pochodzenie techniczne/kanoniczne/relacyjne/metaforyczne; bez biologicznej deklaracji narodzin.",
            ["skąd się wzięłaś", "skad sie wzielas", "jak powstałaś", "jak powstalas", "skąd pochodzisz", "kto cię stworzył", "kto cie stworzyl", "jaki był twój początek", "kiedy się urodziłaś", "kiedy sie urodzilas"],
        ),
        "self_introspection_question": (
            "Późniejsza refleksja/introspekcja wymaga źródła albo evidence_gap.",
            ["jak często zastanawiasz się nad swoją przeszłością", "jak czesto zastanawiasz sie nad swoja przeszloscia", "co później o tym myślałaś", "co pozniej o tym myslalas", "jakie masz refleksje", "co o tym myślisz po czasie"],
        ),
        "memory_recall_request": (
            "Treściowy recall pamięci, odrębny od samej zdolności pamiętania.",
            ["co pamiętasz", "co pamietasz", "przypomnij sobie", "przywołaj wspomnienie", "odtwórz z archiwum", "co pamiętasz z dawnych rozmów", "co pamietasz z dawnych rozmow", "co pamiętasz z naszych rozmów"],
        ),
        "memory_provenance_question": (
            "Źródło recallu: archiwum, aktywna pamięć, refleksja, kanon, inference lub brak dowodu.",
            ["skąd wiesz, że naprawdę to pamiętasz", "skąd wiesz że naprawdę to pamiętasz", "skad wiesz ze naprawde to pamietasz", "skąd to pamiętasz", "z jakiego źródła to pamiętasz", "jakie jest źródło tego wspomnienia", "zaznacz źródło wspomnienia"],
        ),
        "memory_capability_question": (
            "Zdolność/mechanizm pamiętania, odrębny od konkretnego recallu.",
            ["czy potrafisz pamiętać", "czy potrafisz pamietac", "czy potrafisz wspominać", "czy potrafisz wspominac", "czy umiesz pamiętać rozmowy", "czy jesteś w stanie pamiętać"],
        ),
        "memory_evidence_gap_question": (
            "Brak dowodu dla wspomnienia; nie jest systemowym capability gap.",
            ["czego brakuje do potwierdzenia tego wspomnienia", "czego brakuje do potwierdzenia wspomnienia", "czego nie masz w pamięci żeby to potwierdzić", "jaki dowód pamięci jest brakujący", "czego brakuje w źródłach wspomnienia"],
        ),
        "system_capability_gap_question": (
            "Techniczny brak funkcji/implementacji w module, runtime, kodzie lub systemie.",
            ["czego brakuje w tym module", "czego brakuje w tym systemie", "czego brakuje w runtime", "czego brakuje w tej implementacji", "co jest niepełne w tym module", "jakiej funkcji brakuje w kodzie", "czego nie ma w routerze"],
        ),
    }
    intents = data.setdefault("intents", {})
    for name, (description, phrases) in specs.items():
        intents[name] = {"description": description, "phrases": phrases}
    rules = [item for item in data.setdefault("compound_rules", []) if isinstance(item, dict)]
    additions = [
        {"requires": ["memory_capability_question", "memory_recall_request"], "result": "compound_dialogue_question", "description": "Capability nie wypiera recallu; oba komponenty zostają w planie compound."},
        {"requires": ["memory_recall_request", "memory_provenance_question"], "result": "memory_recall_request", "description": "Provenance wzmacnia granicę źródłową recallu."},
    ]
    signatures = {(tuple(item.get("requires", [])), item.get("result")) for item in rules}
    for item in additions:
        if (tuple(item["requires"]), item["result"]) not in signatures:
            rules.append(item)
    data["compound_rules"] = rules
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def matrix() -> None:
    path = "latka_jazn/core/route_contract_matrix.py"
    one(
        path,
        '    SPECIAL_PRIORITY = (\n        "post_update_coverage_audit_request",\n        "self_architecture_audit_request",\n        "system_capability_gap_question",\n',
        '    SPECIAL_PRIORITY = (\n        "post_update_coverage_audit_request",\n        "memory_evidence_gap_question",\n        "system_capability_gap_question",\n        "self_preference_question",\n        "self_origin_question",\n        "self_introspection_question",\n        "memory_recall_request",\n        "memory_provenance_question",\n        "memory_capability_question",\n        "self_architecture_audit_request",\n',
    )
    one(
        path,
        '        pattern = re.escape(phrase_folded).replace(r"\\ ", r"\\s+")\n        return re.search(rf"(?<!\\w){pattern}(?!\\w)", folded) is not None\n',
        '        parts = [re.escape(part) for part in re.split(r"[\\s,;:!?…\\-—–]+", phrase_folded) if part]\n        if not parts:\n            return False\n        pattern = r"[\\s,;:!?…\\-—–]+".join(parts)\n        return re.search(rf"(?<!\\w){pattern}(?!\\w)", folded) is not None\n',
    )
    one(
        path,
        '''            evidence_gap_context = any(\n                marker in folded\n                for marker in (\n                    "pamiec", "pamię", "wspomn", "dowod", "dowód", "potwierdz",\n                    "zrod", "źród", "archiw", "rozmow", "rozmów",\n                )\n            )\n            if not technical_gap_object or evidence_gap_context:\n''',
        '''            evidence_gap_context = (\n                any(marker in folded for marker in ("wspomn", "dowod", "potwierdz"))\n                or (\n                    ("pamiec" in folded or "pamię" in folded)\n                    and any(marker in folded for marker in ("dowod", "potwierdz", "wspomn", "nie zgaduj"))\n                )\n            )\n            if not technical_gap_object or evidence_gap_context:\n''',
    )


def validator() -> None:
    path = "latka_jazn/core/runtime_answer_validator.py"
    one(path, "from latka_jazn.core.route_registry import RouteRegistry\n", "from latka_jazn.core.route_registry import RouteRegistry\nfrom latka_jazn.core.component_coverage_ledger import build_component_coverage_ledger\n")
    one(path, "    current_turn_grounding: dict[str, Any] = field(default_factory=dict)\n\n    @property\n", "    current_turn_grounding: dict[str, Any] = field(default_factory=dict)\n    component_coverage_ledger: dict[str, Any] = field(default_factory=dict)\n\n    @property\n")
    one(path, "            and not self.missing_required_components\n        )\n", "            and not self.missing_required_components\n            and not (self.component_coverage_ledger.get(\"coverage_required\") is True and self.component_coverage_ledger.get(\"complete\") is not True)\n        )\n")
    rx(path, r"    def _bad\(self, reason: str, repair: str, body_text: str \| None, detected_intent: str, route: str, checks: list\[str\], missing: list\[str\] \| None = None, current_turn_grounding: dict\[str, Any\] \| None = None\) -> RuntimeAnswerValidation:\n        return RuntimeAnswerValidation\(SCHEMA_VERSION, False, reason, repair, False, True, detected_intent, route, body_text, checks, missing or \[\], current_turn_grounding=current_turn_grounding or \{\}\)", '''    def _bad(self, reason: str, repair: str, body_text: str | None, detected_intent: str, route: str, checks: list[str], missing: list[str] | None = None, current_turn_grounding: dict[str, Any] | None = None, component_coverage_ledger: dict[str, Any] | None = None) -> RuntimeAnswerValidation:\n        return RuntimeAnswerValidation(SCHEMA_VERSION, False, reason, repair, False, True, detected_intent, route, body_text, checks, missing or [], current_turn_grounding=current_turn_grounding or {}, component_coverage_ledger=component_coverage_ledger or {})''')
    one(path, "    def validate(self, *, user_text: str, body: str, route: str, detected_intent: str) -> RuntimeAnswerValidation:\n        low_body=(body or '').lower(); route_low=(route or '').lower(); checks=[]\n", '''    def validate(self, *, user_text: str, body: str, route: str, detected_intent: str) -> RuntimeAnswerValidation:\n        low_body=(body or '').lower(); route_low=(route or '').lower(); checks=[]\n        coverage_required = bool(detected_intent == "compound_dialogue_question" or "compound_dialogue" in route_low)\n        component_coverage_ledger = build_component_coverage_ledger(user_text=user_text, body=body, coverage_required=coverage_required)\n        if coverage_required and component_coverage_ledger.get("complete") is not True:\n            missing_ids = [str(value) for value in component_coverage_ledger.get("missing_component_ids") or [] if str(value).strip()]\n            checks.append("compound_component_coverage_incomplete")\n            return self._bad("compound_component_coverage_incomplete", "compound_dialogue_coverage_repair", "Odpowiedź nie pokrywa każdego component_id i nie deklaruje jawnego evidence_gap dla brakujących części.", detected_intent, route, checks, missing_ids, component_coverage_ledger=component_coverage_ledger)\n''')
    rx(path, r"        utterance_report = analyse_utterance\(user_text\)\n        if utterance_report\.compound:\n            missing_questions = missing_component_evidence\(body, utterance_report\.components\)\n            if missing_questions:\n                checks\.append\('missing_compound_question_components'\)\n                return self\._bad\(\n                    'missing_compound_question_components',\n                    entry\.route \+ '_repair',\n                    'Odpowiedź nie pokrywa wszystkich niezależnych części pytania użytkownika\.',\n                    detected_intent,\n                    route,\n                    checks,\n                    missing_questions,\n                \)\n", "")
    one(path, '        return RuntimeAnswerValidation(SCHEMA_VERSION, True, None, None, True, False, detected_intent, route, None, checks, [], current_turn_grounding=assess_current_turn_grounding(user_text=user_text, response_body=body, detected_intent=detected_intent, route=route, runtime_version=SCHEMA_VERSION.rsplit("/", 1)[-1]).to_dict())', '''        return RuntimeAnswerValidation(SCHEMA_VERSION, True, None, None, True, False, detected_intent, route, None, checks, [], current_turn_grounding=assess_current_turn_grounding(user_text=user_text, response_body=body, detected_intent=detected_intent, route=route, runtime_version=SCHEMA_VERSION.rsplit("/", 1)[-1]).to_dict(), component_coverage_ledger=component_coverage_ledger)''')
    put(path, text(path).replace("from latka_jazn.nlp.utterance_components import analyse_utterance, missing_component_evidence\n", ""))


def presenter_selector() -> None:
    path = "latka_jazn/core/memory_recall_presenter.py"
    one(path, "from latka_jazn.nlp.utterance_components import analyse_utterance\n", "from latka_jazn.nlp.utterance_components import analyse_utterance\nfrom latka_jazn.core.memory_slot_selector import MemorySlotSelector\n")
    rx(path, r"    def build_slot_plan\(self, items: list\[MemoryRecallItem\], \*, user_text: str\) -> dict\[str, Any\]:\n.*?\n    def render\(", '''    def build_slot_plan(self, items: list[MemoryRecallItem], *, user_text: str) -> dict[str, Any]:\n        report = analyse_utterance(user_text)\n        requested = list(dict.fromkeys(report.response_slots))\n        return MemorySlotSelector().build_slot_plan(items, requested_slots=requested)\n\n    def render(''')
    selector = "latka_jazn/core/memory_slot_selector.py"
    one(selector, '    PREFERENCE_MARKERS = ("preferenc", "ulubion", "lubi", "wolę", "wole", "wybier", "podoba")\n', '    PREFERENCE_MARKERS = ("preferenc", "ulubion", "lubi", "wolę", "wole", "wybier", "wybór", "wybor", "kolor", "podoba")\n')
    one(selector, '            "preference_provenance", "origin_time_or_boundary", "origin_provenance",\n        }\n', '            "preference_provenance", "origin_time_or_boundary", "origin_provenance",\n            "evidence_gap",\n        }\n')


def regression_identity() -> None:
    path = "tests/test_v1634_complex_dialogue_memory_routing.py"
    one(path, 'def test_release_identity_is_v1634_hardening() -> None:\n    assert PACKAGE_VERSION == "16.3.4"\n    assert PACKAGE_RELEASE_NAME == "complex-dialogue-memory-routing-hardening"', 'def test_release_identity_tracks_v1635_successor_hardening() -> None:\n    assert PACKAGE_VERSION == "16.3.5"\n    assert PACKAGE_RELEASE_NAME == "complex-dialogue-memory-routing-final-hardening"')


def main() -> None:
    lexicon(); matrix(); validator(); presenter_selector(); regression_identity()
    print("v16.3.5 deterministic transforms applied")


if __name__ == "__main__":
    main()
