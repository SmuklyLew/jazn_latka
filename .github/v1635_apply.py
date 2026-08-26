from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one exact match, got {count}: {old[:80]!r}")
    write(path, text.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{path}: regex expected one match, got {count}: {pattern[:80]!r}")
    write(path, updated)


def update_lexicon() -> None:
    path = ROOT / "latka_jazn/resources/nlp/polish_dialogue_route_lexicon.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = "polish_dialogue_route_lexicon/v2"
    data["truth_boundary"] = (
        "Kanoniczny leksykon minimalnych polskich kontraktów tras. Rozróżnia intencję, źródło i granicę prawdy; "
        "nie jest pełnym słownikiem języka polskiego ani zamiennikiem modelu językowego."
    )
    intents = data.setdefault("intents", {})
    intents.update(
        {
            "self_preference_question": {
                "description": "Pytanie o preferencję Łatki; odpowiedź musi rozróżnić preferencję pamiętaną, kanoniczną, bieżącą, wnioskowaną albo unknown.",
                "phrases": [
                    "co najbardziej lubisz", "co lubisz", "co wolisz", "jaki jest twój ulubiony kolor",
                    "jaka jest twoja ulubiona", "jakie masz preferencje", "co wybierasz", "co ci się podoba",
                ],
            },
            "self_origin_question": {
                "description": "Pytanie o pochodzenie/początek Łatki. Warstwy techniczna, kanoniczna, relacyjna i metaforyczna są rozdzielone; biologiczne urodzenie nie jest deklarowane.",
                "phrases": [
                    "skąd się wzięłaś", "skad sie wzielas", "jak powstałaś", "jak powstalas", "skąd pochodzisz",
                    "kto cię stworzył", "kto cie stworzyl", "jaki był twój początek", "jaki byl twoj poczatek",
                    "kiedy się urodziłaś", "kiedy sie urodzilas",
                ],
            },
            "self_introspection_question": {
                "description": "Pytanie o późniejszą refleksję/introspekcję; wymaga źródła refleksji albo evidence_gap.",
                "phrases": [
                    "jak często zastanawiasz się nad swoją przeszłością", "jak czesto zastanawiasz sie nad swoja przeszloscia",
                    "co później o tym myślałaś", "co pozniej o tym myslalas", "jakie masz refleksje", "co z tego wynika w twojej refleksji",
                    "co o tym myślisz po czasie", "co o tym myslisz po czasie",
                ],
            },
            "memory_recall_request": {
                "description": "Treściowy recall pamięci. Pytanie o to, co jest pamiętane/odzyskane, nie o samą zdolność pamięci.",
                "phrases": [
                    "co pamiętasz", "co pamietasz", "przypomnij sobie", "przywołaj wspomnienie", "przywolaj wspomnienie",
                    "odtwórz z archiwum", "odtworz z archiwum", "co pamiętasz z dawnych rozmów", "co pamietasz z dawnych rozmow",
                    "co pamiętasz z naszych rozmów", "co pamietasz z naszych rozmow",
                ],
            },
            "memory_provenance_question": {
                "description": "Pytanie o źródło pamięci/recallu: archiwum, aktywna pamięć, dziennik, kanon, inference lub brak dowodu.",
                "phrases": [
                    "skąd wiesz że naprawdę to pamiętasz", "skad wiesz ze naprawde to pamietasz", "skąd to pamiętasz", "skad to pamietasz",
                    "z jakiego źródła to pamiętasz", "z jakiego zrodla to pamietasz", "jakie jest źródło tego wspomnienia",
                    "jakie jest zrodlo tego wspomnienia", "zaznacz źródło wspomnienia", "zaznacz zrodlo wspomnienia",
                ],
            },
            "memory_capability_question": {
                "description": "Pytanie o zdolność/mechanizm pamiętania, odrębne od prośby o konkretny recall.",
                "phrases": [
                    "czy potrafisz pamiętać", "czy potrafisz pamietac", "czy potrafisz wspominać", "czy potrafisz wspominac",
                    "czy umiesz pamiętać rozmowy", "czy umiesz pamietac rozmowy", "czy jesteś w stanie pamiętać", "czy jestes w stanie pamietac",
                ],
            },
            "memory_evidence_gap_question": {
                "description": "Pytanie o brak dowodu do potwierdzenia wspomnienia. Nie jest systemowym capability gap.",
                "phrases": [
                    "czego brakuje do potwierdzenia tego wspomnienia", "czego brakuje do potwierdzenia wspomnienia",
                    "czego nie masz w pamięci żeby to potwierdzić", "czego nie masz w pamieci zeby to potwierdzic",
                    "jaki dowód pamięci jest brakujący", "jaki dowod pamieci jest brakujacy", "czego brakuje w źródłach wspomnienia",
                ],
            },
            "system_capability_gap_question": {
                "description": "Techniczne pytanie o brak funkcji/implementacji w konkretnym module, runtime, kodzie albo systemie. Nie przejmuje pytań o brak dowodu pamięciowego.",
                "phrases": [
                    "czego brakuje w tym module", "czego brakuje w tym systemie", "czego brakuje w runtime",
                    "czego brakuje w tej implementacji", "co jest niepełne w tym module", "co jest niepelne w tym module",
                    "jakiej funkcji brakuje w kodzie", "czego nie ma w routerze",
                ],
            },
        }
    )
    rules = [rule for rule in data.setdefault("compound_rules", []) if isinstance(rule, dict)]
    desired = [
        {
            "requires": ["memory_capability_question", "memory_recall_request"],
            "result": "compound_dialogue_question",
            "description": "Zdolność pamięci nie może wyprzeć konkretnego recallu; oba komponenty przechodzą do planu compound.",
        },
        {
            "requires": ["memory_recall_request", "memory_provenance_question"],
            "result": "memory_recall_request",
            "description": "Provenance wzmacnia recall jako wymaganie źródłowe, ale nie zmienia go w diagnostykę systemową.",
        },
    ]
    signatures = {(tuple(rule.get("requires", [])), str(rule.get("result") or "")) for rule in rules}
    for rule in desired:
        signature = (tuple(rule["requires"]), rule["result"])
        if signature not in signatures:
            rules.append(rule)
    data["compound_rules"] = rules
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_route_matrix() -> None:
    replace_once(
        "latka_jazn/core/route_contract_matrix.py",
        '''    SPECIAL_PRIORITY = (\n        "post_update_coverage_audit_request",\n        "self_architecture_audit_request",\n        "system_capability_gap_question",\n''',
        '''    SPECIAL_PRIORITY = (\n        "post_update_coverage_audit_request",\n        "memory_evidence_gap_question",\n        "system_capability_gap_question",\n        "self_preference_question",\n        "self_origin_question",\n        "self_introspection_question",\n        "memory_recall_request",\n        "memory_provenance_question",\n        "memory_capability_question",\n        "self_architecture_audit_request",\n''',
    )


def update_validator() -> None:
    path = "latka_jazn/core/runtime_answer_validator.py"
    replace_once(
        path,
        "from latka_jazn.core.route_registry import RouteRegistry\n",
        "from latka_jazn.core.route_registry import RouteRegistry\nfrom latka_jazn.core.component_coverage_ledger import build_component_coverage_ledger\n",
    )
    replace_once(
        path,
        '''    current_turn_grounding: dict[str, Any] = field(default_factory=dict)\n\n    @property\n''',
        '''    current_turn_grounding: dict[str, Any] = field(default_factory=dict)\n    component_coverage_ledger: dict[str, Any] = field(default_factory=dict)\n\n    @property\n''',
    )
    replace_once(
        path,
        '''            and not self.missing_required_components\n        )\n''',
        '''            and not self.missing_required_components\n            and not (\n                self.component_coverage_ledger.get("coverage_required") is True\n                and self.component_coverage_ledger.get("complete") is not True\n            )\n        )\n''',
    )
    regex_once(
        path,
        r'''    def _bad\(self, reason: str, repair: str, body_text: str \| None, detected_intent: str, route: str, checks: list\[str\], missing: list\[str\] \| None = None, current_turn_grounding: dict\[str, Any\] \| None = None\) -> RuntimeAnswerValidation:\n        return RuntimeAnswerValidation\(SCHEMA_VERSION, False, reason, repair, False, True, detected_intent, route, body_text, checks, missing or \[\], current_turn_grounding=current_turn_grounding or \{\}\)''',
        '''    def _bad(\n        self,\n        reason: str,\n        repair: str,\n        body_text: str | None,\n        detected_intent: str,\n        route: str,\n        checks: list[str],\n        missing: list[str] | None = None,\n        current_turn_grounding: dict[str, Any] | None = None,\n        component_coverage_ledger: dict[str, Any] | None = None,\n    ) -> RuntimeAnswerValidation:\n        return RuntimeAnswerValidation(\n            SCHEMA_VERSION, False, reason, repair, False, True, detected_intent, route,\n            body_text, checks, missing or [], current_turn_grounding=current_turn_grounding or {},\n            component_coverage_ledger=component_coverage_ledger or {},\n        )''',
    )
    replace_once(
        path,
        '''    def validate(self, *, user_text: str, body: str, route: str, detected_intent: str) -> RuntimeAnswerValidation:\n        low_body=(body or '').lower(); route_low=(route or '').lower(); checks=[]\n''',
        '''    def validate(self, *, user_text: str, body: str, route: str, detected_intent: str) -> RuntimeAnswerValidation:\n        low_body=(body or '').lower(); route_low=(route or '').lower(); checks=[]\n        coverage_required = bool(\n            detected_intent == "compound_dialogue_question"\n            or "compound_dialogue" in route_low\n        )\n        component_coverage_ledger = build_component_coverage_ledger(\n            user_text=user_text,\n            body=body,\n            coverage_required=coverage_required,\n        )\n        if coverage_required and component_coverage_ledger.get("complete") is not True:\n            missing_ids = [\n                str(value) for value in component_coverage_ledger.get("missing_component_ids") or []\n                if str(value).strip()\n            ]\n            checks.append("compound_component_coverage_incomplete")\n            return self._bad(\n                "compound_component_coverage_incomplete",\n                "compound_dialogue_coverage_repair",\n                "Odpowiedź nie pokrywa każdego component_id i nie deklaruje jawnego evidence_gap dla brakujących części.",\n                detected_intent,\n                route,\n                checks,\n                missing_ids,\n                component_coverage_ledger=component_coverage_ledger,\n            )\n''',
    )
    regex_once(
        path,
        r'''        utterance_report = analyse_utterance\(user_text\)\n        if utterance_report\.compound:\n            missing_questions = missing_component_evidence\(body, utterance_report\.components\)\n            if missing_questions:\n                checks\.append\('missing_compound_question_components'\)\n                return self\._bad\(\n                    'missing_compound_question_components',\n                    entry\.route \+ '_repair',\n                    'Odpowiedź nie pokrywa wszystkich niezależnych części pytania użytkownika\.',\n                    detected_intent,\n                    route,\n                    checks,\n                    missing_questions,\n                \)\n''',
        "",
    )
    replace_once(
        path,
        '''        return RuntimeAnswerValidation(SCHEMA_VERSION, True, None, None, True, False, detected_intent, route, None, checks, [], current_turn_grounding=assess_current_turn_grounding(user_text=user_text, response_body=body, detected_intent=detected_intent, route=route, runtime_version=SCHEMA_VERSION.rsplit("/", 1)[-1]).to_dict())''',
        '''        return RuntimeAnswerValidation(\n            SCHEMA_VERSION, True, None, None, True, False, detected_intent, route, None, checks, [],\n            current_turn_grounding=assess_current_turn_grounding(\n                user_text=user_text, response_body=body, detected_intent=detected_intent, route=route,\n                runtime_version=SCHEMA_VERSION.rsplit("/", 1)[-1],\n            ).to_dict(),\n            component_coverage_ledger=component_coverage_ledger,\n        )''',
    )
    # The old helper is no longer used by validator finalization.
    text = read(path).replace(
        "from latka_jazn.nlp.utterance_components import analyse_utterance, missing_component_evidence\n",
        "",
    )
    write(path, text)


def update_presenter() -> None:
    path = "latka_jazn/core/memory_recall_presenter.py"
    replace_once(
        path,
        "from latka_jazn.nlp.utterance_components import analyse_utterance\n",
        "from latka_jazn.nlp.utterance_components import analyse_utterance\nfrom latka_jazn.core.memory_slot_selector import MemorySlotSelector\n",
    )
    regex_once(
        path,
        r'''    def build_slot_plan\(self, items: list\[MemoryRecallItem\], \*, user_text: str\) -> dict\[str, Any\]:\n.*?\n    def render\(''',
        '''    def build_slot_plan(self, items: list[MemoryRecallItem], *, user_text: str) -> dict[str, Any]:\n        report = analyse_utterance(user_text)\n        requested = list(dict.fromkeys(report.response_slots))\n        return MemorySlotSelector().build_slot_plan(items, requested_slots=requested)\n\n    def render(''',
    )


def update_selector() -> None:
    replace_once(
        "latka_jazn/core/memory_slot_selector.py",
        '''            "preference_provenance", "origin_time_or_boundary", "origin_provenance",\n        }\n''',
        '''            "preference_provenance", "origin_time_or_boundary", "origin_provenance",\n            "evidence_gap",\n        }\n''',
    )


def update_v1634_regression_identity() -> None:
    path = "tests/test_v1634_complex_dialogue_memory_routing.py"
    text = read(path)
    text = text.replace(
        "def test_release_identity_is_v1634_hardening() -> None:\n    assert PACKAGE_VERSION == \"16.3.4\"\n    assert PACKAGE_RELEASE_NAME == \"complex-dialogue-memory-routing-hardening\"",
        "def test_release_identity_tracks_v1635_successor_hardening() -> None:\n    assert PACKAGE_VERSION == \"16.3.5\"\n    assert PACKAGE_RELEASE_NAME == \"complex-dialogue-memory-routing-final-hardening\"",
    )
    write(path, text)


def main() -> None:
    update_lexicon()
    update_route_matrix()
    update_validator()
    update_presenter()
    update_selector()
    update_v1634_regression_identity()
    print("v16.3.5 deterministic transforms applied")


if __name__ == "__main__":
    main()
