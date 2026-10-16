# Jaźń 16.3.25.5.116.0.34.4 — ChatGPT host pre-spawn evidence / recovery

## Incydent (16 października 2026)

W bieżącej zwykłej rozmowie ChatGPT brak wywoływalnych `jazn_status`, `jazn_generate_visible_reply`, `jazn_resume_visible_reply`, `jazn_finalize_reply`.
Lokalna próba uruchomienia procesu zakończyła się `ClientError` **przed** wejściem do kodu Jaźni.
Repozytorium ani ZIP nie może nadać narzędziu hosta uprawnień do uruchamiania procesów ani samodzielnie zarejestrować wtyczki dla bieżącej wiadomości.

## Zakres zmiany

- `negotiate_chatgpt_ingress` przyjmuje opcjonalny, host-observed `host_executor_pre_spawn_error`; tylko cztery jawne typy, nigdy pełne teksty wyjątków.
- Osobno raportuje błąd konkretnej powierzchni oraz sukces niezależnego executora; nie fałszuje stanu filesystemu, archiwum, daemona ani widocznej odpowiedzi.
- Zwraca read-only wskazówkę recovery: użyj już zweryfikowanej zdalnej Jaźni, kontynuuj lokalny bootstrap po dowodzie procesu albo skonfiguruj/wybierz właściwy MCP bez ponawiania blokowanego executora.
- Nie zmienia routingu rzeczywistej tury, nie omija OAuth, nie tworzy fałszywej pamięci, nie replayuje wiadomości i nie inicjuje operacji zewnętrznej.
- Nowe testy pokrywają wszystkie typy pre-spawn, sukces alternatywy i odrzucanie surowych/wrażliwych błędów.

## Kroki operatora (rzeczywista naprawa dostępności)

1. Na stale działającym hoście (Windows/daemon/serwer) użyj zweryfikowanego SYSTEM i wykonaj `py -X utf8 run.py host-preflight --json`, `py -X utf8 run.py start`, `py -X utf8 run.py status --json`. Wymagaj `conversation_ready=true` oraz poprawnej wersji.
2. Udostępnij zewnętrzny, uwierzytelniony MCP HTTPS `/mcp` albo OpenAI Secure MCP Tunnel dla właściwego planu. `127.0.0.1` we wtyczce Desktop nie jest serwerem dostępnym z ChatGPT web.
3. Odrębnie sprawdź `/healthz`, `/readyz`, OAuth i `run.py mcp-probe --check-chatgpt-tool-catalog`; nie ujawniaj sekretów, nie wyłączaj kontroli tokenów.
4. Zainstaluj/wybierz właściwe połączenie w bieżącej wiadomości ChatGPT (po zmianach Refresh/recreate zgodnie z uprawnieniami workspace). Wezwij realne `jazn_status`, sprawdź cztery narzędzia, dwie niezależne tury i zaakceptowane `action=display_exact`.
5. Żaden zielony GitHub Actions ani ten branch nie jest dowodem wdrożonego zewnętrznego serwera, aktywnego tunelu lub dostępności narzędzi w tym czacie.

## Weryfikacja wymagana przed merge

`python -X utf8 -m pytest -q tests/test_chatgpt_host_pre_spawn_evidence.py tests/test_chatgpt_ingress_capability.py`

`python -X utf8 -m compileall -q latka_jazn tests main.py run.py`

`python -X utf8 -m pytest -q -m "not live_model and not live_mcp"`

`python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json`

`python -X utf8 run.py doctor --json`, `python -X utf8 run.py package-smoke --profile system --json`

Na gałęzi `fix/*` workflow `release-hardening` może wygenerować aktualne `SOURCE_PROVENANCE.json` i `PACKAGE_INTEGRITY_MANIFEST.json`; nie edytować ręcznie.

## Źródła

- OpenAI: https://help.openai.com/en/articles/20001256-plugins-in-chatgpt
- OpenAI: https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt
- MCP: https://modelcontextprotocol.io/specification/2026-07-28
- Projekt: `AGENTS.md`, `AGENTS.codex.md`, `AGENTS.chatgpt.md`, `docs/runtime/CHATGPT_MCP_CONNECTION_RECOVERY.md`

**Granica:** To patch diagnostyczny. Nie naprawia platformowego `ClientError` przed utworzeniem procesu; dostępność rozmowy wymaga zewnętrznego wdrożenia i testu w rzeczywistym ChatGPT.
