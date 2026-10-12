# Jaźń v16.3.25.5.83 — ChatGPT Library discovery convergence

## Problem

Hostowy runbook ChatGPT traktował `/mnt/data` jako pierwszy lokalny kandydat na paczkę, ale nie definiował obowiązkowego kroku discovery dla logicznej Biblioteki ChatGPT ani sposobu przejścia z uchwytu Library/File do fizycznego pliku dostępnego dla Pythona. W praktyce poprawny SYSTEM ZIP mógł być dostępny w Bibliotece, a mimo to host kończył discovery po inspekcji lokalnego filesystemu.

## Zmiana

Wydanie 16.3.25.5.83 rozdziela dwie powierzchnie evidence:

- lokalny filesystem (`/mnt/data`, materializowany root, host-level workspace);
- logiczne powierzchnie plików hosta (Biblioteka ChatGPT, pliki rozmowy i Projektu, gdy host udostępnia taką capability).

Jeżeli SYSTEM ZIP nie jest lokalnie dostępny, ale logiczna powierzchnia plików jest dostępna, host ma przeszukać ją przed zadeklarowaniem braku paczki. Uchwyt logiczny (`file_id`, ścieżka Library itp.) nie jest ścieżką OS. Wybrany plik musi zostać zmaterializowany jako dokładne surowe bajty do kontrolowanej lokalnej ścieżki, a lokalna kopia musi ponownie przejść kontrolę rozmiaru i zaufanego SHA-256 przed użyciem istniejącego `CHATGPT_BOOTSTRAP.py`.

Konflikt kilku kandydatów tego samego wydania co do rozmiaru, SHA-256 lub metadanych kończy się fail-closed. Brak capability Library jest klasyfikowany jako niedostępność tej powierzchni, nie jako dowód braku pliku. MEMORY pozostaje niezależną paczką danych i nigdy nie staje się `active_root`.

## Zakres

- `AGENTS.chatgpt.md` — pełny kontrakt discovery/materializacji;
- `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` — cienki loader przypominający o dodatkowej powierzchni;
- `tests/test_chatgpt_library_discovery.py` — regresja discovery, granicy logical-path/OS-path, fail-closed i SYSTEM/MEMORY;
- `latka_jazn/version.py` — bump wydania do 16.3.25.5.83.

## Evidence zewnętrzne

OpenAI dokumentuje Bibliotekę jako powierzchnię, w której użytkownik może odnajdywać i ponownie wykorzystywać pliki przesłane lub utworzone w ChatGPT, a następnie dodawać je do rozmów. To uzasadnia traktowanie Library jako odrębnej powierzchni discovery zamiast utożsamiania jej z lokalnym mountem kontenera.

- OpenAI Help Center, "Using Library to manage files in ChatGPT": https://help.openai.com/en/articles/20001052

## Granica odpowiedzialności

Zmiana nie dodaje logiki domenowej do `run.py`, nie omija `main.py`, nie zmienia bezpiecznego ekstraktora i nie tworzy nowego runtime. Naprawia wyłącznie hostowe discovery przed istniejącym bootstrapem.
