# Jaźń v16.3.25.5.64 — visible-turn / TTY / host-route convergence

## Problem

Zaobserwowany objaw był jednoznaczny: po użyciu narzędzia hosta odpowiedź pojawiła się bez kanonicznej koperty `MessageEnvelope` (`🕒 ...`, `<state_emoticon> Łatka`, pusta linia, body). Żywy daemon nie jest wystarczającym dowodem autorstwa odpowiedzi. Brak koperty oznacza przerwanie accepted-visible-turn lineage.

Reprodukcja na v16.3.25.5.63 pokazała, że sam runtime dla zwykłej tury zwracał `action=generate_then_finalize`, `accepted_visible_turn_ready=false` i wymagał phase-2. Oznacza to, że runtime nie autoryzował tekstu bez nagłówka; host ominął wejście/finalizację tej konkretnej tury.

Audyt wykazał także dwa powiązane problemy implementacyjne:

1. `host_tool_turn_policy` nie rozpoznawał URL/media lookup wystarczająco wcześnie, więc np. link YouTube lub prośba o odsłuch mogła nie dopuścić `web.run` w kontrakcie zwykłej rozmowy.
2. `runtime_chat.py` wyprowadzał `process_persistence` bezpośrednio z `stdin.isatty()` (`persistent_terminal` vs `ephemeral_stdin_pipe`). To miesza właściwość urządzenia terminalowego z długością życia procesu/transportu.

## Granica techniczna

Kod lokalnego runtime może działać fail-closed od chwili, gdy host wywoła `run.py` i utworzy kontrakt tury. Nie może przechwycić tekstu, który platformowy host wyświetli całkowicie poza runtime. Dlatego naprawa obejmuje zarówno kontrakty kodowe, jak i cienki loader/runbook hosta: każda zwykła wiadomość po aktywacji runtime musi najpierw wejść do runtime; wynik Web/GitHub/image/file jest pośrednim evidence; po narzędziu host wraca do tego samego requestu/tury i finalizuje go przed widoczną odpowiedzią.

## TTY/PTTY

`isatty()` jest sygnałem związania strumienia z terminalem, a nie dowodem trwałości procesu ani obecności człowieka. Python dokumentuje `IOBase.isatty()` jako test połączenia strumienia z terminalem/TTY. Microsoft dokumentuje ConPTY jako warstwę hostowania aplikacji znakowych, w której wejście i wyjście mogą płynąć przez pipe'y, a aplikacja hostująca odpowiada za prezentację i wejście użytkownika.

W Jaźni oznacza to:

- TTY/PTTY jest capability **terminalowego UX** (kursor, VT, raw/cbreak, interaktywny selector);
- ChatGPT GUI/tool host może prawidłowo działać jako non-TTY;
- long-lived pipe może utrzymywać jeden proces; samo non-TTY nie oznacza `ephemeral`;
- samo TTY nie oznacza `persistent`;
- trwałość ChatGPT transportu wynika z process handle/streaming capability albo z daemon-bound transactional lineage.

Źródła:
- Python `io.IOBase.isatty()`: https://docs.python.org/3/library/io.html#io.IOBase.isatty
- Microsoft, Pseudoconsoles: https://learn.microsoft.com/en-us/windows/console/pseudoconsoles
- Microsoft, CreatePseudoConsole: https://learn.microsoft.com/en-us/windows/console/createpseudoconsole
- Microsoft, Windows Console and Terminal Definitions: https://learn.microsoft.com/en-us/windows/console/definitions

## Zmiany v64

- `runtime_environment.py` rozdziela `io_surface`, `terminal_ui_mode` i `tty_controls_enabled` od transport persistence.
- `runtime_chat.py` nie nazywa non-TTY pipe'a efemerycznym; persistence jest jawnie związana z długością życia procesu.
- `host_tool_turn_policy.py` rozpoznaje URL/media lookup i wymusza semantykę: tool result = intermediate, same-turn resume + finalization + accepted visible turn + MessageEnvelope.
- istniejący `turn_authority_runtime_overlay.py` nadal przenosi `host_tool_turn_policy` do kontraktu host generation i wymaga runtime finalization po tool-use; nowe pola polityki v64 rozszerzają ten istniejący gate.
- `CHATGPT_PROJECT_INSTRUCTIONS.txt` doprecyzowuje runtime-first także przed zwykłym użyciem narzędzi, same-turn resume oraz fail-closed po utracie koperty; szczegółowy `AGENTS.chatgpt.md` już wcześniej wymagał powrotu do tej samej tury i finalizacji.
- dodano testy regresyjne non-TTY ChatGPT, TTY terminal, redirected stdin, URL/media tooling i loader/finalization.

## Warunek sukcesu

Naprawa nie polega na ręcznym dopisywaniu nagłówka. Sukces oznacza, że po tool-use zwykła wypowiedź może zostać pokazana wyłącznie jako zaakceptowany `display_exact` z kopertą po finalizacji tej samej tury; w przeciwnym razie host pokazuje diagnozę techniczną.
