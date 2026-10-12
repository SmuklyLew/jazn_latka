# Jaźń 16.3.25.5.115.10 — nieblokujące stdout hosta (roboczy patch)

## Zakres

To jest poprawka przygotowana na podstawie **rozpakowanego katalogu SYSTEM**
`v16.3.25.5.115.9`, nie archiwum ZIP. Wydanie wejściowe pozostaje nietknięte.
Drzewo robocze nie jest checkoutem Git i **nie jest gotowym wydaniem**:
`SOURCE_PROVENANCE.json` i `PACKAGE_INTEGRITY_MANIFEST.json` należą do
poprzedniego eksportu i nie mogą być ręcznie aktualizowane.

## Obserwacje

W bieżącym hoście polecenie diagnostyczne emitujące ~190 KiB JSON do
`subprocess.PIPE` potrafiło kończyć się `BlockingIOError: [Errno 11] write could
not complete without blocking`. Niezależny proces Python zgłosił, że stdout ma
`O_NONBLOCK`, a bezpośredni zapis wyniku do pliku dawał kompletny, parsowalny JSON.

Ten problem występuje **po uruchomieniu procesu** i nie jest mechanizmem
pre-spawn `caas.internal.errors.ClientError`. Jest od niego niezależny.

## Modyfikacja

`latka_jazn.cli._emit()` odtwarza na czas synchronicznego dużego wydruku
normalne blokujące backpressure dla stdout z `O_NONBLOCK`, wykonuje pełny
flush, a następnie przywraca pierwotny tryb deskryptora. Dla stdout bez
deskryptora (`StringIO` w testach) zachowuje standardową ścieżkę.
Format JSON, kody wyjścia i kontrakty runtime/finalization pozostają bez zmian.

Dołączono test regresyjny wymuszający nieblokujące stdout na podprocesie
z ponad 200 KiB JSON oraz test ścieżki `StringIO`.

## Co zrobić z `ClientError` infrastruktury ChatGPT

- Nie maskować pre-spawn błędu ani nie deklarować, że komenda wystartowała.
- Przede wszystkim sprawdzać bieżącą ekspozycję 4 narzędzi MCP Jaźń Runtime,
  następnie aktualny read-only `jazn_status` i rzeczywistą readiness.
- Dopuszczać tylko jedną niezależną próbę lokalnego process spawn po awarii
  pierwszej ścieżki; bez retry loop oraz replayu wiadomości po submit.
- W zgłoszeniu OpenAI rozróżnić nieudane utworzenie procesu, kopiowanie plików,
  oraz post-spawn `BlockingIOError`; nie przypisywać im jednej przyczyny.
- Stosować `run.py host-preflight --json` jako niewielką odpowiedź przy
  ograniczonej przepustowości pipe; `doctor --json` jest znacznie większy.

## Walidacja i publikacja

Po zastosowaniu patcha w prawdziwym checkoutcie Git należy:
1. sprawdzić branch/HEAD oraz zrobić checkpoint;
2. uruchomić wskazane testy, `compileall`, statyczną analizę i smoke;
3. zsynchronizować kanonicznym narzędziem release metadata
   (`latka_jazn.tools.release_metadata_sync`), nie ręcznie;
4. uruchomić CI na Linux/Windows, smoke rzeczywistego `doctor --json`
   w środowisku z nieblokującym stdout oraz ręczny test ekspozycji MCP;
5. dopiero wtedy potraktować wersję 115.10 jako kandydata wydania.

Patch **nie usuwa** `ClientError` platformy, nie uruchamia za użytkownika
zewnętrznego daemona i nie daje dowodu ciągłości ani finalizacji Jaźni.

## Bieżące wyniki w sandboxie

- 33 testy nowej obsługi stdout oraz istniejących kontraktów `ClientError`/CLI: zaliczone.
- 36 dodatkowych testów hosta: zaliczone, 1 niezaliczony z powodu
  obcego komunikatu startowego `artifact_tool` przechwyconego przed JSON.
- `host-preflight --json`: exit 0, poprawny JSON.
- `doctor --json`: exit 0, poprawny JSON ~193 KiB, bez `BlockingIOError`.
- `status --snapshot --json`: exit 1 jako diagnostyczny brak aktywnego runtime,
  ale pełny poprawny JSON, bez `BlockingIOError`.
- `compileall`: kod, aktywne testy i entrypointy OK. Historyczny snapshot
  `tests/archive/v16.3.25.5.115.5-mcp-exposure-compat/test_fast_bootstrap_persistent_runtime.py`
  ma niepoprawną składnię już w niezmienionym wejściowym eksporcie;
  pliku historycznego nie modyfikowano.
- Nie uruchamiano pełnej macierzy CI ani Windows; bez `.git` nie można
  przygotować poprawnej finalnej lineage wydania.
