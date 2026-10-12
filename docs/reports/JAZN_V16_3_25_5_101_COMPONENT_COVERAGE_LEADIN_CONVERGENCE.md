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


## Dokończenie audytu regresyjnego

Dalsza reprodukcja na dokładnym kodzie brancha wykazała dwa dodatkowe przypadki,
których początkowy test nie obejmował:

- dyrektywa stylu odpowiedzi, np. `Powiedz prawdę.`, pozostawała osobnym
  komponentem bez celu semantycznego i przed listą pytań mogła ponownie
  utworzyć niemożliwy obowiązek coverage;
- początkowe markery `self_knowledge` i `self_assessment` były zbyt szerokie
  (`jestem`, `kanon`, `o sobie`) i pozwalały jednemu fragmentowi odpowiedzi
  fałszywie pokryć inny cel semantyczny.

Reguła lead-in została dlatego rozszerzona tylko o wąskie dyrektywy sposobu
odpowiedzi (`prawdę`, `szczerze`, `wprost`, `dokładnie`) i działa wyłącznie,
gdy po nich istnieje rzeczywisty kolejny cel. Samodzielna dyrektywa nadal jest
zachowywana. Markery introspekcyjne zostały zawężone do sygnałów właściwych dla
konkretnej intencji, dzięki czemu coverage pozostaje fail-closed.

Test regresyjny obejmuje teraz bezpośrednio `RuntimeAnswerValidator`, dodatnie
przejście dokładnej wiadomości źródłowej oraz ujemne przypadki cross-coverage.
Przed zmianą aktywnego testu jego poprzednia zatwierdzona postać została
zachowana bajt w bajt w `tests/archive/`.

## Dodatkowy blocker bazowy wykryty podczas pełnej walidacji

Pełna walidacja ujawniła niezależny błąd istniejący już w bazowym
`16.3.25.5.100`: `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` przekraczał
kontraktowy limit 5000 znaków. Nie podniesiono limitu testu. Loader został
skrócony do cienkiej warstwy discovery/bootstrap, zachowując wymagane granice
`remote_runtime`, verified SYSTEM ZIP, `AGENTS.md`, właściwego runbooka hosta
i finalizacji.


## CI closure po pierwszym wdrożeniu

Rzeczywiste runy GitHub Actions ujawniły dwa dodatkowe gate'y repozytorium.
`Stable test contracts` odrzucił wersjonowaną nazwę aktywnego testu, dlatego
regresję przeniesiono do stabilnej nazwy
`tests/test_component_coverage_leadin_convergence.py`, a poprzednie zatwierdzone
wersje zachowano w `tests/archive/`.

Pełny `release-hardening` pokazał też drift kontraktu wydania: aktywne
`startup_contract.json` oraz dwa release-identity testy nadal wskazywały
`16.3.25.5.100-chatgpt-bootstrap-progress-convergence`. Aktywne kontrakty zostały
przeniesione na `16.3.25.5.101-component-coverage-leadin-convergence`; historyczny
raport wersji .100 i snapshoty pozostają bez zmian.

Loader został skompresowany bez podnoszenia limitu 5000 znaków i zachowuje
literalne kontrakty wymagane przez testy host-executor, Library bootstrap,
bezpieczną materializację ZIP, MEMORY attach oraz zwracanie tool evidence do tej
samej tury. Lokalny zestaw krytycznych gate'ów po tych zmianach: 190/190.
