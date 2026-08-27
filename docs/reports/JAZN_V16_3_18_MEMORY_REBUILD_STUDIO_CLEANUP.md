# Jaźń v16.3.18 — finalizacja pojedynczego Memory Rebuild Studio

## Cel

Wydanie `16.3.18-memory-rebuild-unified-studio-cleanup` domyka konwergencję interfejsu Memory Rebuild rozpoczętą w v16.3.17. Po tej zmianie kod dostarczany w pakiecie ma jeden kanoniczny interfejs Studio i jeden cienki punkt zgodnościowy.

## Kanoniczne wejścia

- `latka_jazn/tools/memory_rebuild_app/studio.py` — jedyny właściciel powłoki Studio, stron TESTY / PROJEKTOWANIE / USTAWIENIA i routingu akcji interfejsu.
- `latka_jazn/tools/memory_rebuild_app/studio_workflows.py` — bezpośrednie workflow operatorskie do aktualnego silnika.
- `latka_jazn/tools/memory_rebuild_app/studio_dialogs.py` — wspólny backend dialogów i theme.
- `latka_jazn/tools/memory_rebuild_app/tui_v24.py` — wyłącznie cienki adapter kompatybilności publicznego `run_studio_v24`; nie posiada własnego menu i deleguje do `studio.py`.

## Usunięte implementacje

Z drzewa źródłowego usuwane są nieużywane, zastąpione warstwy:

- `studio_p0.py`
- `studio_v16314.py`
- `studio_v16316_settings.py`
- `tui.py`
- `tui_candidates.py`
- `tui_common.py`
- `tui_export.py`
- `tui_import.py`
- `tui_paths.py`
- `tui_tests.py`

Nie są to usunięcia silnika pamięci ani obsługi zgodności pięciobazowej. Historyczny tryb `tools/memory_rebuild_legacy_v24.py` pozostaje osobnym, jawnym trybem zgodności uruchamianym przez launcher.

## Granice bezpieczeństwa

Zmiana nie modyfikuje prywatnych danych pamięci i nie commituję żadnych baz SQLite, WAL/SHM, eksportów rozmów, ZIP-ów ani sekretów. Nie zmienia także twardych blokad automatycznej akceptacji doświadczeń, L2/L3 ani automatycznej aktywacji runtime.

## Walidacja

Test regresyjny wymaga jednocześnie, aby:

1. kanoniczne `studio`, `studio_workflows` i `tui_v24` nie importowały żadnej z usuniętych warstw;
2. dziesięć wymienionych modułów fizycznie nie było dostarczanych w katalogu pakietu;
3. `tui_v24.py` nadal istniał jako adapter kompatybilności;
4. wersja wydania była zgodna z `16.3.18-memory-rebuild-unified-studio-cleanup`.

`PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` nie są edytowane ręcznie. Po otwarciu PR do `master` ich synchronizację wykonuje kanoniczny job `manifest_sync` workflow `release-hardening`, zgodnie z `AGENTS.md`.
