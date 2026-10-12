# Jaźń v16.3.25.5.115.21.5 — integracja startup + P1 MEMORY

## Zakres i lineage

Baza: `upgrade/v16.3.25.5.115.21.4-active-memory-readiness-p1` (`21820fff2`).
Drugi rodzic integracyjny: `fix/v16.3.25.5.115.18.2-chatgpt-startup-evidence-hardening` (`9bd05eef7`).
Wspólny `master` przed integracją: `48168b74c`.

- Zachowano implementację P1: uwierzytelnione, tylko do odczytu active-MEMORY evidence, bez deklaracji recall/continuity i bez aktywacji danych.
- Dołączono maszynowy kontrakt startup evidence, poprawki hostowego loadera, pakowania, ChatGPT plugin prompt, dokładnych Files identyfikatorów i testy `test_chatgpt_startup_evidence_hardening.py`.
- Scalono konfliktujące pola `startup_contract.json`, `deployment.contract.json`, testów tożsamości wydania oraz katalog testów Studio; nie przywracano testów skasowanych później na gałęzi P1.
- Zachowano historyczne kopie poprzednio aktywnych testów w `tests/archive`.
- `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` należy wygenerować wyłącznie kanonicznym `release_metadata_sync` / GitHub `manifest_sync` — nie edytować ręcznie.

## Warunki konieczne PR -> master

1. `python -X utf8 -m compileall -q latka_jazn tests main.py run.py`.
2. `python -X utf8 -m pytest -q -m "not live_model and not live_mcp"` (pełny test deterministyczny).
3. `python -X utf8 run.py doctor --json`, `python -X utf8 run.py package-smoke --profile system --json`, Pyright oraz CI Ubuntu/Windows.
4. Metadane wydania zsynchronizowane kanonicznym `release_metadata_sync`, idempotentne na finalnym HEAD.
5. Sprawdzenie `diff --check`, archiwów testów, kontraktów release i reguł GitHub protection/rulesets.
6. Opcjonalny test E2E z rzeczywistym SYSTEM ZIP (SHA-256/CRC, dokładne `file_id`, daemon/status i zaakceptowane `display_exact`).
7. Dla pełnego recall osobne, prawdziwe MEMORY: nie utożsamiać obserwacji SQLite z jej aktywacją i ciągłością.

Nie zamykać PR ani nie deklarować merge-ready, dopóki wymagane, obserwowane kontrole są zielone. Nie scalaj automatycznie.
