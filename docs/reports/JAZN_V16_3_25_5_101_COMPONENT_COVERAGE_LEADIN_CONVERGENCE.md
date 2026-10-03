# Jaźń v16.3.25.5.101 — component coverage lead-in convergence

## Problem

W wiadomościach wieloczęściowych krótki wstęp dyskursywny, np. `To powiedź.`,
mógł zostać wydzielony przez `_split_meaningful_components()` jako osobny
komponent. Po normalizacji Unicode forma `powiedź` jest już sprowadzana do
`powiedz`, więc literówka z `ź` nie była pierwotną przyczyną. Komponent był
następnie klasyfikowany jako `directive` i zachowywany przez
`analyse_utterance()`, mimo że nie niósł własnego celu semantycznego.

`component_coverage_ledger` działa fail-closed. Dla komponentu bez
`semantic_intents` wymaga przynajmniej jednego `anchor_hit`. Wstęp
`To powiedź.` nie ma stabilnej kotwicy odpowiedzi: `powiedz` jest stopwordem,
a `to` jest zbyt krótkie dla tokenizatora. Taki komponent stawał się więc
niemożliwym obowiązkiem coverage i blokował finalizację.

## Dodatkowy problem ujawniony podczas implementacji

Po usunięciu samego lead-inu pytania `Co wiesz o sobie?`, `Jak się czujesz?`
i `Co uważasz o sobie?` nadal nie miały własnych intencji semantycznych.
Coverage mogło przez to zależeć od literalnych anchorów drugiej osoby, podczas
gdy prawidłowa odpowiedź używa pierwszej osoby.

## Zmiana

- pomijany jest wyłącznie wąski, generyczny lead-in przed późniejszym realnym celem;
- samodzielne i niegeneryczne dyrektywy pozostają komponentami;
- dodano `self_knowledge`, `self_affect` i `self_assessment`;
- dodano first-person-compatible markery coverage;
- memory guard pozostaje fail-closed i nie został osłabiony;
- dodano regresję na dokładną wiadomość oraz warianty `powiedz/powiedź`.

## Granica bezpieczeństwa

Zmiana nie uznaje automatycznie komponentów bez intencji za pokryte. Fail-closed
coverage pozostaje aktywne poza wąsko rozpoznanym lead-inem.
