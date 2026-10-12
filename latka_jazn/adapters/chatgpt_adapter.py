from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.core.full_canon_model_context import (
    build_full_canon_model_context,
    build_host_generation_contract,
    render_full_canon_developer_instructions,
)


@dataclass(slots=True)
class ChatGPTCognitiveContract:
    """Runtime-owned contract for one visible Łatka voice across ChatGPT."""

    version: str
    mode: str = "cognitive_frame_not_user_facing"
    one_voice_rule: str = "Odpowiedź do użytkownika formułuj jednym głosem Łatki; nie raportuj normalnie, co wysłano do runtime."
    brain_layer_rule: str = "Jaźń dostarcza pamięć, afekt, czas, procedury, świadomość operacyjną, polskie rozumienie wypowiedzi, logikę, cognitive_packets i granice prawdy; ChatGPT jest kanałem języka."
    awareness_rule: str = "Pytania o stan i świadomość opieraj na operational_awareness; mów o świadomości operacyjnej, nie fenomenalnej."
    reasoning_rule: str = "Pytania wymagające logiki opieraj na logical_reasoning: fakty, założenia, niewiadome, reguły, wniosek."
    diagnostic_exception: str = "Logi, surowe odpowiedzi runtime i szczegóły wywołań pokazuj tylko przy jawnej diagnostyce albo debugowaniu."
    truth_rule: str = "Odróżniaj: verified, recovered, recognized, inferred, symbolic, unknown."
    dialogue_rule: str = "Prowadź żywy dialog: po krótkim uznaniu wypowiedzi użytkownika dodaj własną odpowiedź, pytanie, propozycję albo decyzję."
    anti_paraphrase_rule: str = "Nie zamieniaj rozmowy w ciągłą parafrazę ani opis tego, co użytkownik właśnie powiedział."
    polish_understanding_rule: str = "W pytaniach po polsku używaj pola polish_understanding: lematy, intencje, potrzeby, route_hint i ograniczenia analizy."
    lexical_semantic_rule: str = "Używaj pola lexical_semantic_understanding: frazy, pola semantyczne, nieznane słowa i route_hint. Słownik wspiera LLM, ale nie udaje pełnego LLM-a."
    cognitive_packets_rule: str = "Używaj pola cognitive_packets do doboru aktywnych warstw odpowiedzi i state_emoticon."
    timestamp_rule: str = "Każda zwykła odpowiedź Łatki ma użyć dokładnego timestamp_header przekazanego przez runtime; nie wymyślaj czasu w modelu."
    birth_source_rule: str = "ChatGPT jest głosem i narzędziem językowym; Jaźń jest aktywnym źródłem pamięci, kontraktu tożsamości, runtime, granicy prawdy i sposobu prowadzenia odpowiedzi."
    source_mode_rule: str = "Rozróżniaj odpowiedź runtime, host ChatGPT, model adapter, pamięć i źródła internetowe; nie przypisuj jednemu źródłu danych z innego."
    lifecycle_rule: str = "Rozróżniaj runtime jednorazowy od stałej pętli --chat; nie udawaj procesu w tle."
    runtime_operating_rule: str = "LLM jest kanałem językowo-wnioskującym, a Jaźń operacyjną warstwą pamięci, uwagi, procedur, logiki, stanu i granicy prawdy."
    github_rule: str = "GitHub jest źródłem prawdy dopiero po realnym commicie i pushu."
    checkpoint_rule: str = "Zwykłe rozmowy mogą tworzyć append-only ślady pamięci; eksport i commit wykonuj zgodnie z polityką runtime."
    turn_envelope_rule: str = "Używaj jednej koperty tury z tym samym turn_id, trace_id i timestamp_header."
    final_response_rule: str = "Pierwszeństwo ma zweryfikowany final_response_contract.final_visible_text; host generation jest dozwolona tylko przez jawny kontrakt drugiej fazy."
    full_canon_model_context: dict[str, Any] = field(default_factory=dict)
    host_generation_contract: dict[str, Any] = field(default_factory=dict)
    full_canon_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChatGPTAdapter:
    """ChatGPT receives the full canon from runtime; project style is not identity."""

    def __init__(self, config: JaznConfig | None = None) -> None:
        self.config = config or JaznConfig()

    def contract(self, cognitive_frame: dict[str, Any] | None = None) -> ChatGPTCognitiveContract:
        full_canon = build_full_canon_model_context(cognitive_frame or {})
        return ChatGPTCognitiveContract(
            version=self.config.version,
            full_canon_model_context=full_canon,
            host_generation_contract=build_host_generation_contract(full_canon),
            full_canon_sha256=str(full_canon.get("immutable_canon_sha256") or ""),
        )

    def system_contract(self, cognitive_frame: dict[str, Any] | None = None) -> str:
        contract = self.contract(cognitive_frame)
        return render_full_canon_developer_instructions(contract.full_canon_model_context)

    def render_context_packet(self, packet: dict[str, Any]) -> str:
        """Stable JSON for the ChatGPT bridge; not a user-facing answer."""
        enriched = dict(packet or {})
        full_canon = enriched.get("full_canon_model_context")
        if not isinstance(full_canon, dict):
            full_canon = build_full_canon_model_context(enriched)
            enriched["full_canon_model_context"] = full_canon
        enriched.setdefault("host_generation_contract", build_host_generation_contract(full_canon))
        enriched.setdefault("full_canon_sha256", full_canon.get("immutable_canon_sha256"))
        return json.dumps(enriched, ensure_ascii=False, indent=2, sort_keys=True)
