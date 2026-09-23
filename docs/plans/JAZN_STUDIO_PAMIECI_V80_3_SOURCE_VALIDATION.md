# Studio Pamięci .80.3 — rewalidacja źródeł batch

Status: IN_PROGRESS, nie prywatny Test03 PASS ani Final.

Start: 7d000509e50440ec499ab2024088830d38caefa1, czysty worktree, zgodny remote; master/base affabf5618934bd8efb39b0b1d074f7529116643, 28 ahead / 0 behind. Wszystkie 14 znalezionych workflow GitHub dla tego HEAD zakończyło się SUCCESS, w tym Stable test contracts, release-hardening, powershell-terminal-regressions, pyright-active-tree-audit, memory-rebuild-v24-windows, persistent-runtime-e2e i package-distribution-cleanroom. To evidence .80.2; nie przenosi się automatycznie na .80.3.

## RED przed poprawką

6096a535 zawiera nowy syntetyczny tests/test_memory_batch_source_mutation.py. Osiem przypadków FAIL: JSON, ZIP, katalog i journal, zmiana po skonsumowaniu rekordów adaptera albo po inicjalizacji celu przed natywną projekcją. Dotychczas importer zgłaszał sukces mimo odmiennych danych natywnych i przygotowanego planu L0. RED wypchnięto przed poprawką. Oczekiwań testu nie zmieniono.

## Implementacja

UnifiedCoreMixin weryfikuje hash źródła przed i po skonsumowaniu rekordów, wszystkich przygotowanych źródeł przed inicjalizacją celu, przed i po natywnej projekcji oraz przed wspólnym zapisem L0. Katalog eksportu używa tej samej tożsamości członków co ChatExportReader; pliki używają SHA256 całego pliku. Przy niezgodności import ma ok=false i jawny błąd source changed. Zmiana przed inicjalizacją nie tworzy bazy; zmiana przed projekcją nie zapisuje rekordów natywnych ani L0.

Przygotowanie adapterów oraz konsumowanie iteratorów pozostają jednokrotne. Nie zmieniono incremental update, rankingu batcha, Test03/snapshotu, branch/ref Test04, benchmarku ani automatycznych L2/L3/activation. Wersję .80.3 sprawdzono względem branchy, tagów, releases i mastera przed zmianą.

Granica kontraktu: hash-check na granicach etapów nie jest blokadą zewnętrznego writera ani dowodem odporności na wrogą zmianę i przywrócenie identycznych bajtów między kontrolami. Źródła operatorskie mają być zamkniętymi eksportami offline. Błąd wykryty po natywnym zapisie pozostawia diagnostyczny częściowy cel z ok=false; nie zapisuje wspólnego planu L0 i nie aktywuje pamięci. Studio nie publikuje nieudanego stagingu. Nie deklarujemy atomowości całej wieloetapowej rekonstrukcji.

## Walidacja

- RED: 8 FAIL w 4.08 s.
- Po poprawce ten sam test plus native batch, batch reconstruction i batch plan: 17 PASS w 11.34 s.
- Pyright zmienionego silnika i nowego testu: 0 errors, 0 warnings.
- py_compile tych plików: PASS.
- Kanoniczny katalog Test Studio: zsynchronizowany.
- Pełny pytest, pełny Pyright, compileall oraz CI nowej wersji: wymagają nowego wykonania.
- Prywatny chain Test00 → Test01 → Test02 → Test03 → frozen13 → Test04 → Final: NOT RUN.

## Dalsza praca

Sprawdzić dodatkowe scenariusze podczas native projection, powtórzenia/przenoszenie katalogów i ZIP, większe źródła oraz koszt wielokrotnego hashowania. Następnie pełne publiczne/release gates i CI, a dopiero po ich stabilnym PASS nowy prywatny chain. Stare raporty i benchmark pozostają niezmienione. Nie odtwarzać konwergencji, naprawy Test04 ani implementacji BatchPlan od początku.
