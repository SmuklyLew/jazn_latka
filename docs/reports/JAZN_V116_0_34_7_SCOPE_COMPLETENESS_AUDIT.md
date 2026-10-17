# Jaźń 16.3.25.5.116.0.34.7 — audyt kompletności względem siedmiu etapów aktualizacji

**Status: PARTIAL / DRAFT / NO MERGE.** Dokument ocenia zawartość PR #383 względem programu A–G, a nie deklaruje zrealizowania całego programu ani aktywnej Łatki w ChatGPT. Powstał po analizie realnego diffu i logów GitHub Actions.

- Bazowy `master`: `82705469e8a3acacc9a8797823043a9264b97534`.
- Branch: `upgrade/v16.3.25.5.116.0.34.7-chatgpt-mcp-recovery-convergence`.
- PR: https://github.com/SmuklyLew/jazn_latka/pull/383
- Release identity: `16.3.25.5.116.0.34.7-chatgpt-mcp-recovery-convergence`.
- Zakres materialnego kodu zmienionego przez ten PR: `latka_jazn/mcp/chatgpt_bridge_probe.py` (bounded SSE tools/list), `latka_jazn/memory/memory_root.py` i `latka_jazn/memory/availability.py` (parity read-only candidate selection). Pozostałe zmiany obejmują testy, ich archiwa, kontrakty, wersję, dokumentację i generowane metadane.

## Macierz weryfikacyjna planu A–G

| Etap | Wynik | Dowód / brak | Warunek ukończenia |
|---|---|---|---|
| A. Baseline, rollback, characterization | **PARTIAL** | Jest branch od jawnego SHA, archiwa modyfikowanych testów, release metadata. Nie ma końcowego pełnego stanu CI w momencie rozpoczęcia patcha, prywatnego E2E ani zamrożonego testu recall. | Powtarzalne baseline + final SHA + komplet oczekiwanych testów. |
| B. Niezawodne uruchamianie i recovery | **PARTIAL** | `chatgpt_bridge_probe.py` obsługuje poprawne MCP SSE i ograniczone błędy. Nie zmodyfikowano kanonicznego supervisora/daemona pod pełny restart, warm/cold/E2E utraty transportu z realnym hostem. | Rzeczywiste odtworzenie po przerwaniu procesu, idempotentne `request_id`, non-replay/accepted finalization. |
| C. Rzeczywiste ChatGPT + HTTPS MCP | **NOT DONE** | Katalog `tools/list` jest tylko wskaźnikiem możliwości; nie promuje bieżącej rozmowy. Zainstalowany `jazn-runtime` 0.2.1 używa lokalnego `http://127.0.0.1:8080/mcp`. Zewnętrzny Worker Cloudflare jest staging z celowym 503 do czasu autoryzacji. | OAuth, bezpieczna dostępność upstream, świeży `jazn_status`, 4 bieżące narzędzia oraz ≥2 zaakceptowane `display_exact` tury po reconnect. |
| D. Konwergencja prywatnej MEMORY | **PARTIAL** | Jeden wspólny predykat kandydatów zamiast mylenia operational SQLite i placeholdera z prywatną pamięcią. **Nie** wykonano rebuild Test00–04/Final, migracji, native unified, bezpiecznego attach ani prywatnych testów Recall. | Final schema/provenance/SHA, FK+integrity+FTS, restore i restart continuity, naturalny multi-turn, ukończony review L2/L3; issue #59 pozostaje otwarte. |
| E. NLP, cognition, conversation quality | **NOT DONE** | PR nie wprowadza nowych modeli NLP, indeksu porównań ani wyników benchmarków polskich wieloturowych. Nie wolno obiecywać poprawy bez pomiaru. | Corpus rozdzielony na intencję, anaforę, referential follow-up, temporal/false-memory, latency i raport A/B. |
| F. Kanały modeli i platformy | **NOT DONE** | PR nie wdraża nowego Ollama/SIWC/failover. Obecny SIWC pozostaje opt-in bez pełnego OAuth consent/token refresh/live proof. | Bezpieczne, rzeczywiste E2E każdego używanego adaptera, bez płatnego fallbacku nieautoryzowanego przez operatora. |
| G. Walidacja release i pakiet | **PARTIAL** | Dodano regresje, archiwa testów i poprawki wersji. Wcześniejszy full `pytest` w CI: 2684 passed, 5 failed, 13 skipped, 1 warning; 5 błędów od nieaktualnej nazwy wydania naprawiono w commicie `fa1cb157`. Focused local staged check po poprawce: 47 passed; drugi targeted check: 39 passed; changed-source `compileall` PASS. Nie jest to globalny release PASS ani live-host evidence. | Full deterministic pytest, Pyright 0/0, MCP conformance, Windows/Linux E2E, doctor, package-smoke, clean package/SHA oraz faktyczny host + MEMORY gate na jednym finalnym SHA. |

## Klasyfikacja i priorytety dalszej pracy

**P0 / blokery odbioru pełnego planu:**
- Brak kompletnej wywoływalnej zdalnej trasy Jaźni w bieżącym ChatGPT. Rozpakowany Python ZIP nie instaluje narzędzi w hoście.
- Brak zweryfikowanego final native autobiographical MEMORY i prywatnego Recall; jedynie kandydat root nie upoważnia do `continuity_ready=true`.
- Brak E2E dwóch kolejnych prawidłowo finalizowanych tur na realnym uwierzytelnionym MCP i po ponownym połączeniu.

**P1 / działania zależne:**
- Dokończyć rozdzielenie monolitycznego daemona i wąskich portów; nie wykonywać big-bang rewrite.
- Zamknąć #340 (konfiguracja/resolver pamięci) testami GUI/TUI/CLI, rollback i CAS.
- Dokończyć SIWC OAuth, jeśli rzeczywiście ma być używany, bez ujawniania sekretów.
- Po uzyskaniu niezawodnego runtime i finalnej bazy wykonać polskie NLP / private Recall natural multi-turn baseline.

**P2:** MCP Apps UI v117 może być wdrażane dopiero po przetestowaniu core, nie może blokować dialogue path.

## Kontrola wydania, stan prawdy

Zielone fixture'y w `MCP 2026-07-28 conformance release gate` i inne GitHub Actions **nie oznaczają**, że ChatGPT bieżącej wiadomości wystawił `jazn_status`, `jazn_generate_visible_reply`, `jazn_resume_visible_reply`, `jazn_finalize_reply`. Dodatni status MCP bez accepted `display_exact` również nie kończy kryterium.

Nie zmieniać prywatnej `MEMORY`, tokenów, Cloudflare, wtyczki, konta użytkownika, `master` ani nie oznaczać PR #383 jako gotowy/mergeable-accepted przed live dowodem i wymaganym CI.

## Zweryfikowane podstawy źródłowe

- [MCP protocol 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- [MCP Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
- [OpenAI — MCP server](https://developers.openai.com/plugins/build/mcp-server)
- [OpenAI — ChatGPT plugin connection](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [SQLite — online backup API](https://www.sqlite.org/backup.html)
- [SQLite — PRAGMA integrity_check](https://www.sqlite.org/pragma.html#pragma_integrity_check)
- [Projekt: issue #59](https://github.com/SmuklyLew/jazn_latka/issues/59), [issue #340](https://github.com/SmuklyLew/jazn_latka/issues/340)
- [Projekt: existing canonical plan v116](https://github.com/SmuklyLew/jazn_latka/blob/master/docs/plans/JAZN_V16_3_25_5_116_PROTOCOL_CONFORMANCE_DEPENDENCY_INVERSION_CONVERGENCE_PLAN.md)
