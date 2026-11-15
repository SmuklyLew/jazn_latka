from __future__ import annotations
from typing import Any
import re
from latka_jazn.core.route_handler_base import RouteHandlerResult

GREETING_AT_START_RE = re.compile(
    r"^\s*(?:cześć|czesc|hej|witaj|dzień dobry|dzien dobry|dobry wieczór)\b",
    re.IGNORECASE,
)


class RuntimeSourceHandler:
    name = "RuntimeSourceHandler"
    route = "runtime_source"
    handled_intents = ('runtime_source_question', 'runtime_exact_quote_request')
    def handle(self, text: str, context: dict[str, Any] | None = None) -> RouteHandlerResult:
        ctx=context or {}; last=ctx.get('last_turn') or {}; body=ctx.get('body') or ''; intent=ctx.get('intent','runtime_source_question')
        source={'runtime':'JaznEngine.process_turn','handler':self.name,'intent':ctx.get('intent'),'route_registry':ctx.get('route_entry')}
        if intent == 'runtime_exact_quote_request':
            if last:
                runtime_text = last.get('runtime_text') or ''
                visible_text = last.get('visible_text') or ''
                prior_source = last.get('source_origin') or {}
                source_summary = {
                    'source_origin': prior_source.get('source_origin'),
                    'source_origin_detail': prior_source.get('source_origin_detail'),
                    'handler_name': prior_source.get('handler_name'),
                    'route': prior_source.get('route') or last.get('route'),
                    'trace_id': prior_source.get('trace_id') or last.get('trace_id'),
                }
                answer = (
                    "exact_runtime_text poprzedniej zapisanej tury:\n"
                    f"{runtime_text}\n\n"
                    f"template_origin: {last.get('template_origin') or {}}\n"
                    "runtime_vs_visible_boundary: powyższy cytat pochodzi z pola `runtime_text` checkpointu; "
                    f"pole `visible_text` {'jest identyczne' if runtime_text == visible_text else 'różni się od runtime_text'}.\n"
                    f"source_origin_detail: {source_summary}"
                )
            else:
                answer = (
                    "Nie ma poprzedniego checkpointu, więc nie mogę uczciwie podać exact_runtime_text. "
                    "template_origin: brak; runtime_vs_visible_boundary: brak danych; "
                    "source_origin_detail: turn checkpoint nie istnieje."
                )
        else:
            # A mixed greeting + provenance question should answer both parts.
            # Runtime source remains deterministic and must not impersonate an LLM.
            greeting = "Cześć! " if GREETING_AT_START_RE.match(text) else ""
            answer = (
                greeting
                + "Tę informację o pochodzeniu przygotowuje handler runtime_source Jaźni. "
                "Nie oznacza to, że tę odpowiedź wygenerował model językowy. "
                "Źródło wcześniejszej odpowiedzi sprawdzam w zapisanych metadanych jej tury, a nie zgaduję."
            )
            if last:
                answer += " Dostępny jest checkpoint ostatniej tury."
            elif body:
                answer += " Bazowa treść bieżącej tury pochodzi z ConversationResponder."
        return RouteHandlerResult(self.name,self.route,answer,intent=intent,data={'source_origin_answer':source,'last_turn':last},sources=[source],required_components=ctx.get('required_components',[]),satisfied_components=['exact_runtime_text','template_origin','runtime_vs_visible_boundary','source_origin_detail','handler_name'],confidence=0.95,source_origin_detail='runtime_source_handler')
