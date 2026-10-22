# Studio Startu 0.3 — pulpit operatorski

Wersja 0.3 dodaje osobny moduł GUI: tools/jazn_start_studio_dashboard.py.
Pulpit wyświetla niezależne stany Jaźni, Ollamy, MEMORY i MCP. Stan zadania
nie jest stanem samej usługi i nie potwierdza finalizacji tury w ChatGPT.

## Uruchomienie

    python -X utf8 tools/jazn_start_studio.py --check
    python -X utf8 tools/jazn_start_studio.py --text
    python -X utf8 tools/jazn_start_studio.py --studio

Linux: python3 zamiast python. GUI wymaga graficznego Tcl/Tk; CLI i check nie importują Tk.
Pulpit odczytuje lokalny status Jaźni i API Ollamy w osobnym wątku automatycznie
co około 30 sekund (lub po kliknięciu Odśwież). Nie uruchamia usług w tle.

## Prawdomówność statusów

- Jaźń: dopiero zbieżność active_state=active_trusted, endpoint_identity_matches,
  endpoint_heartbeat_fresh oraz endpoint_reachable daje status zweryfikowanego
  żywego daemona. Otwarty port 8787 nie wystarcza. Rozbieżność wersji procesu
  i kodu na dysku jest pokazywana jawnie; nigdy nie wykonujemy automatycznego restartu.
- Ollama: HTTP 200 i poprawna lista modeli /api/tags dowodzi działania API,
  nie zdolności Jaźni do wygenerowania odpowiedzi.
- MEMORY: brak jawnego full_autobiographical_recall_ready lub continuity_ready
  oznacza stan niezweryfikowany lub częściowo gotowy.
- MCP: lokalna gotowość transportu nie jest zaakceptowaną turą ChatGPT.

Przy zajętych portach 8787/11434 Studio pomija start drugiej kopii i zgłasza
informację, a nie czerwony błąd. W zakładce Zadania i logi każda komenda ma
osobne okno, logi i świadomą akcję start / stop. Eksport logu jest ręczny.

## Ważna uwaga dotycząca MCP 2026-07-28

Obecne zadanie mcp_probe wykonuje legacy initialize / tools/list w osobnym
procesie stdio. Nowsze serwery mogą korzystać ze stateless server/discover
i metadanych protokołu per request. Wynik probe nie dowodzi zgodności
wszystkich rewizji, zewnętrznego OAuth ani faktycznego przekazania wiadomości.
Probe nie wywołuje narzędzi konwersacyjnych.

## Testy

    python -X utf8 -m py_compile tools/jazn_start_studio.py tools/jazn_start_studio_dashboard.py
    python -X utf8 -m pytest -q tests/test_jazn_start_studio.py tests/test_jazn_start_studio_dashboard.py
    python -X utf8 tools/jazn_start_studio.py --check

Sprawdź też manualnie --studio na Windows i Linux z dostępnym wyświetlaczem.
Na Linux headless uruchamiaj --check albo --text.

Oficjalne materiały:
- https://docs.python.org/3/library/tkinter.html
- https://docs.python.org/3/library/subprocess.html
- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio
- https://docs.ollama.com/api/tags

---

# Jaźń — Studio Startu 0.2 (Windows i Linux)

Entry point: tools/jazn_start_studio.py. To osobny operator procesu, a nie alternatywny runtime Jaźni. Polecenia SYSTEM przechodzą wyłącznie przez run.py → main.py.

## Start

Windows / PowerShell:

    python -X utf8 tools/jazn_start_studio.py --check
    python -X utf8 tools/jazn_start_studio.py --text
    python -X utf8 tools/jazn_start_studio.py --studio

Linux / Bash:

    python3 tools/jazn_start_studio.py --check
    python3 tools/jazn_start_studio.py --text
    python3 tools/jazn_start_studio.py --studio

Tkinter jest opcjonalny w trybie tekstowym i diagnostycznym. W trybie GUI wymagany jest serwer graficzny. Poza katalogiem repo użyj --root /sciezka/do/jazn_latka. Opcjonalnie --python wskazuje venv, --ollama plik executable, --model nazwę zainstalowanego modelu.

Tekstowy interfejs: list, start <id>, stop <id>, log <id>, check, quit. W GUI dwuklik zadania otwiera niezależne okno logów. Zamknięcie okna logów nie zatrzymuje procesu.

## Profile

- Jaźń: status --json, host-preflight --json, --model-adapter-status, --llm-route-status, start.
- Pamięć: diagnostyka normalizacji, wake-state oraz archiwum bez mutacji danych.
- Ollama: modele CLI, /api/tags, /api/generate, aplikacja Windows, ollama serve, logi aplikacji/serwera.
- MCP: tunnel_bootstrap.py --help oraz lokalne initialize / tools/list przez stdio. Żadne tools/call ani wiadomość użytkownika nie są wysyłane przez probe.

## Ograniczenia i bezpieczeństwo

1. Nie jest tworzony EXE ani ukryty skrypt PowerShell. Kod używa subprocess.Popen z listą argumentów i shell=False. PowerShell i Bash są środowiskami uruchomienia aplikacji, nie otrzymują interpolowanych niezweryfikowanych komend.
2. Każde działanie wymaga jawnego polecenia. --check tylko czyta lokalne pliki i porty. Port 8787 nie dowodzi aktywności Jaźni: potrzebny jest zweryfikowany run.py status --json.
3. Studio kończy tylko swoje własne procesy potomne. Nie używa taskkill /T /F ani automatycznej eskalacji do SIGKILL. Istniejący daemon, uruchomiony poza Studio, pozostaje nietknięty. run.py start może wystartować trwały daemon i zakończyć starter: Studio nie przypisuje sobie własności daemona.
4. MCP stdout służy wyłącznie do JSON-RPC. Studio czyta odpowiedzi protokołu w osobnym probe i nie przechwytuje połączenia ChatGPT. stderr jest odczytywany jako diagnostyka. Nie oznaczamy OAuth, tunelu ani finalizacji tury jako gotowych.
5. Logi w pamięci mają limit 2500 linii na profil, redakcja sekretów jest best-effort. Eksportowane logi należy przejrzeć przed udostępnieniem.
6. Ostrzeżenie antywirusa wobec historycznego EXE nie jest traktowane jako false positive. Nie zaleca się przywracania go z kwarantanny bez analizy.

## Kontrola

    python -X utf8 -m py_compile tools/jazn_start_studio.py
    python -X utf8 -m unittest tests.test_jazn_start_studio -v
    python -X utf8 tools/jazn_start_studio.py --check

Na Windows sprawdź --studio z wieloma oknami logów. Linux headless: --text i --check, bez Tkinter. W CI można użyć pytest dla test_jazn_start_studio.py.

To nadal operator — nie oznacza to, że lokalny model jest faktycznie wybrany przez Jaźń, ani że ChatGPT zaakceptował widoczną turę. Brak trwałej kontroli procesu Ollama GUI oraz brak testów OAuth i zewnętrznego tunelu są jawne.

## Referencje

- https://docs.python.org/3/library/subprocess.html
- https://docs.python.org/3/library/tkinter.html
- https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- https://docs.ollama.com/api/tags
- https://docs.ollama.com/api/generate
- AGENTS.md, AGENTS.codex.md, AGENTS.ollama.md
