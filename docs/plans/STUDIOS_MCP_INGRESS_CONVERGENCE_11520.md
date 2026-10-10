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
