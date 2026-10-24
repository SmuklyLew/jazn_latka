# Studio Jaźni .76 — lokalny test .75 i naprawa ścieżki GUI

## Potwierdzony odbiór lokalny .75 (2026-10-24)

Operator wykonał na Windows dwie odrębne tury przez `run.py --chat-ollama`,
daemon `127.0.0.1:8877`, izolowany workspace
`D:\.AI\jazn_pr416_runtime`, `JAZN_MEMORY_MODE=off`,
model `gemma3:latest`, `session_id=pr416-continuity-check-01`.

1. Pierwsza wiadomość zawierała kod próbny; odpowiedź `OK.`, exit 0.
2. Druga wiadomość żądała odtworzenia kodu bez jego powtórzenia w pytaniu;
   model zwrócił poprawny kod (z końcową kropką), exit 0.

**Wniosek ograniczony:** jedna udana dwuetapowa ciągłość kontekstu CLI.
Nie jest to test persystencji po restarcie, pełnej integracji GUI,
pamięci prywatnej ani całej semantyki wieloturowej.
Nie umieszcza się identyfikatora ani treści próby w repozytorium.

## Poprawka oprogramowania

- `ChatClient` korzysta z poprawnego `--chat-ollama` i dołącza
  `--daemon-host/--daemon-port` wyprowadzone z *walidowanego*
  `Settings.daemon_url`.
- `--daemon-result` wznawia `request_id` na tym samym endpointzie.
  Checkpoint sesji zawiera URL lokalnego daemona; zmiana endpointu
  przy oczekującym żądaniu powoduje fail-closed zamiast poll innej instancji.
- Wybrany port jest przekazywany także przez GUI do start/stop/restart,
  status i doctor; `restart` ma wspólne parametry dla stop/start/status.
- Publiczne `run.py` pozostaje cienkim launcherem, `main.py`
  właścicielem runtime. Nie użyto stopowania obcych PID-ów.
- Numer wydania: `16.3.25.5.116.0.34.76`; paczka, startup i
  wdrożeniowy kontrakt MCP są spójne. Metadane integracyjne synchronizuje
  kanoniczne GitHub Actions `manifest_sync`, a nie ręczne hashowanie.

## Manualny odbiór GUI — DO WYKONANIA na Windows

Przy działającej .75 na 8877 **nie podmieniaj plików procesu .75**.
Nową .76 pobierz do osobnego katalogu, z osobnym workspace i portem
(np. 8878), po teście integralności i tożsamości nowego daemona.
W GUI wybierz właściwy Python, model Ollama, `daemon_url` dla .76,
następnie uruchom kontrolę statusu, lokalny czat, wyślij jedną
wiadomość i sprawdź poprawnie zaakceptowaną finalizację.
Zakończ klienta przyciskiem Rozłącz transport i połącz ponownie;
zachowaj sesję i sprawdź drugą turę. Przy nierozstrzygniętym
`request_id` wywołaj **Wznów wynik**, a nie **Wyślij**.

Po zaliczeniu tego testu (i dopiero wtedy) wykonaj kontrolowany restart
WYŁĄCZNIE .76 na 8878, ponownie sprawdź `active_root`, PID,
`instance_id`, a potem sprawdź trwałość sesji osobnym testem.
Nie zatrzymuj .42 na 8787 ani .75 na 8877.

Dodatkowe warunki PR #415/#416 pozostają: pełna migracja studiów,
host-local MCP/ChatGPT, offline EXE, Avast i dostępność.
Nie oznaczaj PR jako merge-ready bez ich rozliczenia.

Oficjalne referencje:
https://docs.python.org/3/library/urllib.parse.html
https://doc.qt.io/qtforpython-6/PySide6/QtCore/QUrl.html
https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/viewing-workflow-run-history
