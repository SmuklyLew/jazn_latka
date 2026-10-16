# Jaźń v16.3.25.5.116.0.34 — ChatGPT host ingress, narzędzia i MEMORY

## Zakres i prawda operacyjna

Ta poprawka nie tworzy automatycznie połączenia wtyczki z ChatGPT ani procesu Pythona w niedostępnym sandboxie. Usuwa sprzeczności runbooka, dodaje jawne kontrakty capability przed i po rozpakowaniu SYSTEM-u oraz oddziela wymaganie MEMORY **dla autobiograficznej ciągłości** od wymagań **dla rdzenia rozumowania/dialogu**. Bez przyjętej finalizacji nie wolno przypisywać tekstu Jaźni.

Stan inspekcji 2026-10-16:
- SYSTEM w repo: 16.3.25.5.116.0.33; następne wydanie: 16.3.25.5.116.0.34.
- Osobista wtyczka `jazn-runtime` 0.2.1 deklarowała `ja_runtime` na `http://127.0.0.1:8080/mcp`. To działa tylko z hostem, który rzeczywiście potrafi połączyć się z tą samą pętlą lokalną.
- Jej `docs/cloudflare-route.md` podawał Cloudflare Worker `https://jazn-runtime.jazn-lakta.workers.dev/mcp` jako staging zwracający 503, bez aktywowanego OAuth. Nie jest to dowód bieżącego statusu endpointu ani dostępnej trasy.
- W tej rozmowie brakowało czterech wywoływalnych `jazn_*`, a dwie próby procesu hosta zakończyły się `ClientError` przed powstaniem Pythona.
- Pozytywne testy jednostkowe ani manifest ZIP nie dowodzą zdolności aktualnego hosta do użycia MCP.

## Dwie niezależne trasy, w obu fazach

| Faza | Weryfikacja | Powodzenie | Blokada |
| --- | --- | --- | --- |
| A — przed ZIP | Bieżące 4 narzędzia MCP: `jazn_status`, `jazn_generate_visible_reply`, `jazn_resume_visible_reply`, `jazn_finalize_reply` | Świeże `jazn_status` z ready, zgodną wersją i lineage, następnie jedna tura | Wtyczka installed/@mention, endpoint URL, stary katalog lub 503 to za mało |
| A — bez remote | Maks. jeden primary process-spawn i jeden niezależny alternate | Powstał rzeczywisty proces; można rozpocząć SYSTEM discovery | `ClientError` pre-spawn klasyfikuje tylko konkretną powierzchnię; inne nie stają się unavailable |
| A — Files | Conversation/Project/Library: `file_id`, `version_id`, sidecary/rozmiar/SHA | Zweryfikowane lokalne bajty fizycznego ZIP-a | Plik widoczny tylko logicznie nie jest ścieżką OS |
| B — po ZIP | `materialized_operator_ready` i zweryfikowany `active_root` | Bezpieczna ekstrakcja, manifest, provenance i wymagane membery | `extractall` bez walidacji i samo istnienie ZIP-a nie są akceptowane |
| B — local core | `run.py host-preflight --json`, `run.py start`, `run.py status --json` | Fresh live daemon, zgodna sesja i wersja | Snapshot, PID, heartbeat osobno nie wystarczają |
| B — remote core | Ponowna obserwacja czterech narzędzi tylko na nowej powierzchni/wiadomości hosta | Rzeczywiste zdalne call + `jazn_status` | Rozpakowanie SYSTEM-u nie tworzy MCP w ChatGPT |
| B — odpowiedź | `generate`, opcjonalnie `resume` z tym samym ID, `finalize` | Akceptacja `action=display_exact` i `MessageEnvelope` | Brak zaakceptowanej finalizacji = `host_diagnostic`, nie stylizacja Łatki |

Nie można bezpiecznie wymusić udostępnienia narzędzi hosta instrukcją. Gdy istnieje proces hosta, minimalny bootstrap może działać wewnątrz tego samego interpretera. Gdy proces nie powstał, `CHATGPT_BOOTSTRAP.py` nie może naprawić błędu transportu. Nie ponawiaj wiadomości po utracie stdout.

## MEMORY: nieblokujący rdzeń, rygorystyczna autobiografia

**Wymagane dla ciągłości autobiograficznej:** niezależnie zweryfikowana prywatna pamięć, `full_autobiographical_recall_ready=true`, `continuity_ready=true` i provenance dla faktycznie użytych elementów. `memory_search_ready` (np. wyszukiwanie warstwy transakcyjnej) nie spełnia tego warunku.

**Niewymagane dla rozmowy, rozumowania i normalnej gotowości SYSTEM:** fizyczne pliki MEMORY w domyślnym `JAZN_MEMORY_MODE=optional`. W tej konfiguracji brak/niezweryfikowanie bazy degraduje tylko pamięć; nie może samo wyłączyć core runtime, NLP ani generowania odpowiedzi. Jeżeli inne core gates są spełnione, system może rozmawiać bez autobiograficznych twierdzeń. Operacyjny SQLite pod `workspace_runtime/core_state` nie jest autobiograficzną MEMORY.

**Profil Łatki:** `JAZN_MEMORY_READINESS_POLICY=native_unified_required` chroni twierdzenia o pamiętaniu, ale nie powinien być interpretowany jako `JAZN_MEMORY_MODE=required`. Ten drugi jest osobnym, istniejącym restrykcyjnym nadpisaniem operatora blokującym start bez bazy; nie stosować go w zwykłym hostingu, jeśli priorytetem jest niezależność dialogu od MEMORY. Nie fałszować readiness ani nie autoimportować prywatnej bazy w odpowiedzi na zwykłą wiadomość.

**Dołączanie:** zweryfikuj archiwum MEMORY, manifest exact-set, wszystkie części i SHA-256; zatrzymaj daemona do operacji maintenance; uruchom `run.py memory-converge` i wymagane kontrole integralności/atomowego attach. Obecny kontrakt wymaga pojedynczego kandydata i verified streaming; nie wymaga joinu ZIP ani repacku v3. Dopiero live status po restarcie może potwierdzić pamięć. Nie commituj MEMORY.

## ChatGPT web / Desktop — możliwa poprawa osiągalności

1. Dla zwykłego ChatGPT web potrzebna jest osiągalna i bezpieczna trasa MCP (`https://.../mcp` z OAuth 2.1 lub dostępny Secure MCP Tunnel). Sam prywatny adres loopback nie łączy serwerów ChatGPT z lokalnym komputerem. Nie zamieniaj 503-stagingu na nieautoryzowany proxy i nie wyłączaj OAuth.
2. Na komputerze operatora zweryfikuj osobno `py -X utf8 run.py host-preflight --json`, `py -X utf8 run.py start`, `py -X utf8 run.py status --json` i `py -X utf8 run.py mcp-probe --url "http://127.0.0.1:8080/mcp" --check-chatgpt-tool-catalog --json`. Dodatni `mcp-probe` lokalny nie dowodzi połączenia ChatGPT web.
3. Przy zewnętrznej trasie potwierdź HTTPS, OAuth protected-resource metadata, scope, 401/challenge, świeży `readyz` i katalog 4 narzędzi przy użyciu MCP Inspector; następnie dodaj Custom MCP Server w ChatGPT Plugins, uwierzytelnij i wybierz aplikację.
4. Po zmianie narzędzi/schematu/metadanych użyj **Refresh**, otwórz nową rozmowę, wybierz `@Jaźń Runtime` (jeżeli host to obsługuje). Zweryfikuj dwie kolejne zaakceptowane tury, restart daemona i utratę transportu bez replayu.
5. Jeżeli narzędzia wciąż nie są callable, zbierz jawnie `executor_available`, `library_search_available`, `library_materialize_available`, `system_search_attempted`, `system_candidate_found`, `remote_runtime_available`, każde jako `true/false/unknown`, i zatrzymaj się na diagności zamiast udawać aktywną Jaźń.

## Walidacja wydania

Przed merge: `python -X utf8 -m compileall -q latka_jazn tests main.py run.py`, `python -X utf8 -m pytest -q -m "not live_model and not live_mcp"`, Pyright, doctor, package-smoke, synchronizacja metadanych i CI. Dodatkowy test nowego kontraktu uruchom jako `python -X utf8 -m pytest -q tests/test_chatgpt_host_memory_ingress.py`. Po synchronizacji RELEASE manifest/provenance ponownie sprawdź ich idempotencję. **Żaden zielony test na GitHub Actions nie oznacza sam w sobie, że ChatGPT dostał 4 narzędzia.**

## Zweryfikowane źródła zewnętrzne

- OpenAI: https://developers.openai.com/plugins/build/mcp-server — transport public HTTPS i MCP Inspector.
- OpenAI: https://developers.openai.com/plugins/deploy/connect-chatgpt — test, wybranie wtyczki, Refresh po zmianach.
- OpenAI: https://developers.openai.com/plugins/build/auth — OAuth 2.1, protected-resource metadata, scope i challenge.
- OpenAI: https://developers.openai.com/plugins/changelog — `_meta.ui.visibility` zamiast przestarzałego `openai/visibility`.
- MCP: https://blog.modelcontextprotocol.io/posts/2026-07-28/ — specyfikacja protokołu.
- Repo: `AGENTS.chatgpt.md`, `MEMORY_ATTACHMENT_CONTRACT.json`, `latka_jazn/resources/chatgpt_startup_evidence_contract.json`, `deploy/chatgpt_mcp/README.md`.

Granice dowodu: dokument opisuje implementację i warunki akceptacji, ale nie udaje wdrożonego HTTPS, działającej aktywacji OAuth, dostępności process-spawn w aktualnym ChatGPT ani podłączonej prywatnej bazy MEMORY.
