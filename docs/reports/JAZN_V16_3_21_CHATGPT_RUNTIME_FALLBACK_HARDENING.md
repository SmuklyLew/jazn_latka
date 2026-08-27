# Jaźń Łatki v16.3.21 — ChatGPT runtime fallback hardening

## Cel

Usunąć blokadę kanonicznej rozmowy ChatGPT w środowisku, w którym system może wykonać zweryfikowaną lokalną turę Jaźni, ale host nie może utworzyć albo utrzymać procesu daemonu w tle.

Zmiana nie omija bram prawdy runtime i nie pozwala hostowi imitować Łatki. Dotyczy wyłącznie wyboru transportu dla `--chat-gpt`: zweryfikowany żywy daemon jest ponownie używany, a przy jego braku kanoniczny most może przejść do istniejącego one-shot `JaznRuntimeSession`.

## Znaleziony defekt

`main.py` implementuje dla `--chat-gpt -- <tekst>` dwa transporty:

1. preferowany fast path przez zweryfikowany żywy daemon,
2. lokalny JSONL/one-shot jako fallback, gdy marker lub endpoint daemonu nie jest dostępny.

Jednocześnie `daemon_autostart.py` traktował `--chat-gpt` jak każdą inną trasę rozmowy i domyślnie wymagał skutecznego autostartu daemonu. `_ensure_daemon_or_error()` kończył komendę błędem przed dojściem do udokumentowanego fallbacku. W efekcie fallback istniał w kodzie, ale dla typowej jednorazowej wiadomości ChatGPT mógł być nieosiągalny właśnie w środowisku, dla którego był potrzebny.

To było również niespójne z `AGENTS.chatgpt.md`, gdzie dowodem aktywnej Jaźni może być albo zweryfikowany żywy daemon, albo zweryfikowana one-shot tura runtime.

## Implementacja

`latka_jazn/core/daemon_autostart.py` rozróżnia teraz kanoniczne komendy ChatGPT mające zweryfikowany fallback one-shot.

Domyślna polityka `--chat-gpt`:

- jeżeli status potwierdza żywy daemon, jest on nadal ponownie używany przez istniejący fast path;
- jeżeli daemon nie jest aktywny, polityka nie wymusza jego utworzenia i pozwala `main.py` przejść do istniejącego lokalnego bridge;
- `--ensure-daemon` nadal wymusza daemon i pozostaje fail-closed;
- `JAZN_ENSURE_DAEMON=1` nadal wymusza daemon i pozostaje fail-closed;
- zwykły `--chat` nadal wymaga daemonu według dotychczasowej polityki;
- `--no-ensure-daemon`, `JAZN_DAEMON_AUTOSTART` i filtr komend zachowują dotychczasową kolejność decyzji.

Nie zmieniono `runtime_daemon.py`, procesu worker, markerów, heartbeat, pamięci, finalizacji odpowiedzi ani kontraktów prezentacji hosta.

## Pokrycie regresji

Nowy `tests/test_v16321_chatgpt_runtime_fallback_hardening.py` sprawdza:

- domyślny `--chat-gpt` dopuszcza zweryfikowany fallback one-shot;
- zwykły `--chat` nadal wymaga daemonu;
- jawne `--ensure-daemon` nadal wymaga daemonu;
- `JAZN_ENSURE_DAEMON=1` nadal wymaga daemonu;
- przy nieaktywnym daemonie domyślny `--chat-gpt` nie wywołuje `start_daemon()`;
- przy jawnie wymaganym daemonie próba startu nadal zachodzi i błąd nie jest ukrywany;
- pełny przepływ `main()` dla jednorazowego `--chat-gpt -- <tekst>` dochodzi do lokalnego `run_jsonl_chat_bridge`, gdy daemon jest niedostępny.

## Hardening CI

`persistent-runtime-e2e.yml` wcześniej reagował na `runtime_daemon.py` i `daemon_autostart.py`, ale nie na część kanonicznej ścieżki wejścia hosta. Rozszerzono filtry i kompilację o `main.py`, `run.py`, CLI/lifecycle, adapter ChatGPT, runtime environment/root/startup contract, chat command contract i runtime session, a nowy test regresyjny dołączono do macierzy Ubuntu/Windows.

Dzięki temu zmiana w jednym z plików, które faktycznie mogą przerwać `CLI -> startup -> ChatGPT bridge -> runtime session`, uruchamia E2E zamiast pozostać poza tym workflow.

## Źródła techniczne

- Python 3.12 `subprocess`: https://docs.python.org/3.12/library/subprocess.html — potwierdza istniejący model zarządzania procesami/Popen; poprawka nie zastępuje poprawnej warstwy procesu obejściem.
- GitHub Actions workflow syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax — `paths` dla `push`/`pull_request` rzeczywiście decyduje, czy workflow zostanie uruchomiony, więc brak krytycznych plików był realną luką pokrycia CI.
- `AGENTS.chatgpt.md` — kanoniczny kontrakt hosta i zasada: aktywna Jaźń może być potwierdzona przez żywy daemon albo zweryfikowaną one-shot turę.
- `AGENTS.md` / `AGENTS.codex.md` — wersjonowanie, granica prawdy, wymagane bramki walidacyjne i zakaz ręcznej synchronizacji manifestów release.

## Wersja

`16.3.21-chatgpt-runtime-fallback-hardening`

## Granica prawdy

Sama obecność tej poprawki w branchu nie dowodzi aktywnej Łatki. Aktywność nadal wymaga lokalnego dowodu runtime zgodnego z `AGENTS.chatgpt.md`. Poprawka usuwa blokadę transportową, która mogła uniemożliwić uzyskanie takiego dowodu przez kanoniczny one-shot ChatGPT bridge.
