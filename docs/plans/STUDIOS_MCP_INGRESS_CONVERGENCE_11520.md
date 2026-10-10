# Integracja Studio P0 i odzyskiwania MCP ingress — v16.3.25.5.115.20

## Źródła i pochodzenie

- Pierwszy rodzic: `fix/v16.3.25.5.115.18.2-mcp-ingress-job-recovery` @ `e702f3ec8b7880b747adf75e7b4c08f3698d02d5`.
- Drugi rodzic: `fix/studios-p0-integrity-memory-paths` @ `251eecb6cb7d85c98f44a7905e4b843147a6732b`.
- Wspólna baza: `48168b74ccfce42318c2568fbc78433c6051a0d5`.
- PR historyczny P0: https://github.com/SmuklyLew/jazn_latka/pull/341; issue https://github.com/SmuklyLew/jazn_latka/issues/340.

## Decyzje integracyjne

1. Pierwsza gałąź pozostaje właścicielem poprawek diagnostyki MCP, statusu utraconych zadań, CLI i runtime daemon.
2. Wszystkie funkcjonalne zmiany P0 (poza metadanymi wydania i konfliktem wersji/katalogu testów) przejęto jako odpowiednie bloby Git z dokładnego drzewa drugiej gałęzi. Dotyczy to izolacji danych operatorskich, resolverów MEMORY, konfiguracji, testów i dokumentacji.
3. Konflikt katalogu kontraktów rozwiązano jako sumę 2157 definicji: 2123 z gałęzi MCP, 2150 z gałęzi P0, z siedmioma unikalnymi MCP i 34 unikalnymi P0; wspólne wpisy miały identyczną treść. Wersja katalogu wynosi `16.3.25.5.115.20`. Wymagany ponowny kanoniczny `sync_contract_catalog.py --check`.
4. Wersja SYSTEM: `16.3.25.5.115.20-studios-mcp-ingress-convergence`. Kontrakt deployment MCP otrzymał tę samą wersję.
5. Nie kopiowano `PACKAGE_INTEGRITY_MANIFEST.json` ani `SOURCE_PROVENANCE.json` z P0. Wymagane wygenerowanie przez kanoniczny `release_metadata_sync` po zapisaniu commitów; istniejące metadane bazy są nieaktualne do tego momentu.
6. Nie modyfikowano prywatnych danych MEMORY/SQLite, nie wykonywano restartu produkcyjnego runtime ani merge do master.

## Bramy odbioru — OPEN / NOT VERIFIED

- `python -X utf8 tools/jazn_tests_studio/sync_contract_catalog.py --check`
- `python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json` oraz `--check`; metadane tylko narzędziem kanonicznym/CI.
- `python -X utf8 -m compileall -q latka_jazn tools main.py run.py`
- `python -X utf8 -m pytest -q -m "not live_model and not live_mcp"`
- Pyright; `run.py doctor --json`; `run.py package-smoke --profile system --json`.
- CI: Windows, persistent-runtime-e2e, release-hardening, Studio/MEMORY/SQLite, MCP ingress, test contracts; sprawdzić wyniki dla finalnego SHA.
- GUI/EXE, host E2E i pełne pozostałe etapy Studio P1–P3 pozostają odrębnym zakresem.

**Stan: integracja kodu w gałęzi roboczej, nie release candidate.** Samo zapisanie merge commita nie stanowi dowodu zaliczenia powyższych bram.

## Naprawa CI po integracji — v16.3.25.5.115.20.1 (2026-10-10)

- Ubuntu `release-hardening` na poprzednim commicie: **2361 PASS, 10 FAIL, 6 SKIP**.
- Dziewięć błędów wynikało z wersji `16.3.25.5.115.18.1` utrwalonej w `startup_contract.json` i pięciu aktywnych testach wobec wydania `16.3.25.5.115.20`.
- Jeden błąd wymagał historycznego katalogu `tools/jazn_pack_generator_app` jako celu ustawień, choć Studio P0 kieruje zapisywalny stan do `~/.jazn/tools/jazn-pack-generator` lub jawnego `JAZN_OPERATOR_STATE_ROOT`.
- Wersja `16.3.25.5.115.20.1-studios-mcp-ingress-ci-hardening` jest jawnie testowana i spójna z runtime/MCP/startup. Test ustawień sprawdza izolowaną zewnętrzną ścieżkę i brak zapisów podczas odczytu.
- Zachowano oryginały sześciu modyfikowanych testów bajt w bajt w `tests/archive/v16.3.25.5.115.20-pre-ci-hardening/`.
- Kanoniczne `sync_contract_catalog.py --write` oraz `release_metadata_sync --write` pozostają wyłącznymi narzędziami synchronizacji. Wynik CI i `package-smoke` wymagają ponownej weryfikacji na nowym SHA.
- Nie ruszono prywatnej MEMORY ani działającego daemona.

## Ponowna walidacja Windows na zsynchronizowanym katalogu — 2026-10-10

- Pierwszy pełny `powershell-terminal-regressions` na commicie `666d0f87` zakończył się `2354 passed, 1 failed, 7 skipped`. Jedyny test `tests/test_test_suite_governance.py::test_contract_catalog_covers_every_active_definition` zastał wcześniejszy katalog z `test_settings_live_with_tool_app`, gdy kod zawierał już `test_settings_live_outside_verified_system`.
- Kanoniczny workflow `Stable test contracts` zsynchronizował `tools/jazn_tests_studio/test_contracts.json` na późniejszym HEAD `513e48e0`: 2157 pozycji; nowy identyfikator testu jest obecny, stary usunięty; wersja katalogu `16.3.25.5.115.20.1`.
- Ubuntu `release-hardening` i pozostałe 10 workflow na `666d0f87` zakończyły się sukcesem. Nie traktuje się tego jako zaliczenia Windows full suite na nowszym SHA.
- Niniejszy commit dokumentacyjny jest nowym eventem push po synchronizacji katalogu, żeby uruchomić pełne CI z aktualnym katalogiem; nie zmienia testów ani ich kryteriów akceptacji.
- Finalny GO zależy od nowego `powershell-terminal-regressions` i `release-hardening` oraz pozostałych wymaganych workflow; jeśli którykolwiek zawiedzie, pozostawić Draft.
