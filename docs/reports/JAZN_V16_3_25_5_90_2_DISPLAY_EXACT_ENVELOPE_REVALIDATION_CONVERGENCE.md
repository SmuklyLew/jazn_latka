# Jaźń v16.3.25.5.90.2 — display_exact envelope revalidation convergence

## Cel

Ta aktualizacja domyka lukę pozostałą po v16.3.25.5.90.1. Poprzedni patch zaostrzył phase-2 i
routing diagnostyki nagłówka, ale canonical host pre-response gate nadal mógł przyjąć gotowy mapping
z `action=display_exact` bez ponownego sprawdzenia, czy widoczny tekst rzeczywiście zawiera pełny
`MessageEnvelope`.

To jest istotne dla przypadku zaobserwowanego w ChatGPT: pierwsza tura może zostać poprawnie
sfinalizowana, a kolejna odpowiedź hosta nie może odziedziczyć poprzedniego `display_exact`,
ominąć świeżej lineage ani pokazać tekstu bez nagłówka.

## Przyczyna

`latka_jazn/core/chatgpt_host_pre_response_gate/_core.py::_presentation_from()` prawidłowo
wydobywał gotowy packet hosta, ale `run_host_pre_response_gate()` traktował
`action=display_exact` jako wystarczającą deklarację adaptera. Dla takiego gotowego packetu
sprawdzano bieżące turn/trace binding oraz niepusty `final_visible_text`, lecz nie wykonywano
ostatniej niezależnej walidacji kształtu koperty przed pokazaniem tekstu.

W efekcie adapter mógł dostarczyć np.:

```text
🕒 2026-08-28 12:00:00
🌿 Łatka
Treść bez wymaganej pustej linii.
```

i przejść przez pre-response gate, mimo że nie jest to prawidłowy `MessageEnvelope`.

## Naprawa

### Ostatni gate `display_exact`

`latka_jazn/core/chatgpt_host_pre_response_gate/_runner.py` dodaje niezależną
`_display_exact_message_envelope_valid()`, która bezpośrednio przed pokazaniem tekstu wymaga:

- nagłówka `🕒 YYYY-MM-DD HH:MM:SS`;
- niepustej linii stanu/autora;
- pustej trzeciej linii;
- niepustego body;
- zgodności timestampu z metadanymi packetu, jeżeli są obecne;
- zgodności `state_emoticon` i `author_label` z metadanymi packetu, jeżeli są obecne.

Walidacja jest wykonywana zarówno dla bezpośredniego `display_exact`, jak i wyniku
`generate_then_finalize`. Niepoprawna koperta kończy się fail-closed
`RUNTIME_MESSAGE_ENVELOPE_INVALID` / `host_diagnostic`.

### Kolejne tury

Loader ChatGPT doprecyzowuje, że każda kolejna wiadomość wymaga świeżej lineage tury i nie wolno
dziedziczyć `display_exact` ani koperty z poprzedniej wiadomości. Reguła ma aktywny test kontraktowy.

### Regresje

`tests/test_host_pre_response_gate.py` obejmuje teraz:

- bezpośredni `display_exact` bez pełnej koperty → `host_diagnostic`;
- sfinalizowany `display_exact` bez pełnej koperty → `host_diagnostic`;
- dwie kolejne zwykłe wiadomości → dwa osobne wywołania runtime, dwa różne turn bindingi i dwa
  pełne `MessageEnvelope`;
- istniejące poprawne fixture zostały dostosowane do rzeczywistego formatu koperty z pustą linią.

Przed zmianą istniejące aktywne testy zostały zachowane byte-for-byte w `tests/archive/`, zgodnie
z polityką repozytorium.

## Wersja

`16.3.25.5.90.2-display-exact-envelope-revalidation-convergence`

## Weryfikacja

Na etapach przed finalnym `release-hardening` potwierdzono:

- `pyright-active-tree-audit`: success;
- `Stable test contracts`: success;
- `host-spawn-memory-convergence`: success;
- `javascript-node24-contract`: success.

Finalny release candidate pozostaje fail-closed: merge-ready można deklarować dopiero po zielonym
`release-hardening` dla aktualnego HEAD, w tym pełnej deterministic suite, Windows targeted checks,
clean checkout guard i release finalization.

## Granica prawdy

Ten patch wzmacnia wszystkie wspierane ścieżki repozytorium, ale nie może fizycznie zmusić
zewnętrznego hosta ChatGPT do wywołania runtime, jeżeli host całkowicie ominie projektowy ingress.
Dlatego repo utrzymuje dwie niezależne warstwy: kodowy pre-response gate oraz loader/runbook
wymagający runtime-first dla każdej kolejnej wiadomości. Gdy gate jest wywołany, niepełna koperta
nie może już zostać uznana za `display_exact`.
