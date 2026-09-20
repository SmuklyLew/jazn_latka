# Studio Pamięci .80.4 — Test03 wymaga poprawnych buildów

Status IN_PROGRESS. To nie jest prywatna akceptacja ani Final.

## Zweryfikowany poprzedni etap

Wersja .80.3 na d2505b3d3b68bc7fb628c8685c7ea56c621c035b: pełny aktywny pytest 1772 PASS, 6 SKIPPED, 1 warning w 487.48 s. Pełny Pyright 0 errors, 1 odziedziczone ostrzeżenie __all__ w host pre-response gate. compileall aktywnego drzewa PASS. Metadane write/check PASS; po włączeniu wyłącznie metadanych bota ponowna synchronizacja nie generowała diffu. Push i zdalny SHA potwierdzone, drzewo czyste.

Dodatkowe syntetyczne próby .80.3: cztery formaty odrzucają zmianę podczas native projection przed zapisem L0; ZIP i katalog zachowują pełny snapshot po relokacji, zmianie nazw, reverse i powtórzeniach oraz zachowują wszystkie lokalizatory w raporcie. Większy batch 2000 rekordów dziennika / 1000 bieżących rewizji: równe pełne snapshoty normal/reverse, FK PASS, 1.63 s. Te próby są evidence syntetycznym, nie prywatnym Test03.

## Nowy RED

Przegląd wykazał, że validate_test03 sprawdzał gotowość unii i zgodność snapshotów, ale ignorował powodzenie samych buildów i projekcji. Dwa nieudane importy z równymi częściowymi bazami mogły otrzymać PASS. Nowy tests/test_protocol_test03_failed_build_regression.py: 10 FAIL przed poprawką (build A/B, projekcja A/B, brak builda; raport bezpośredni oraz artifact details). RED został zapisany i wypchnięty w edd65399 przed zmianą implementacji; oczekiwania pozostały niezmienione.

## Naprawa właściciela

validate_test03 nadal wymaga source_union_ready, branch_union_not_blocking i normal_reverse_semantic_reconciliation. Dodatkowo wymaga jawnego ok=true dla initialized/import/validation obu buildów oraz poprawnych projekcji z raw_l0_unchanged=true. Brak wyniku lub błędy są blockerem. Nie zmniejszono zakresu porównania snapshotów, nie zmieniono benchmarku ani żadnych automatycznych promocji. Test04 branch/ref i kontrakty mastera pozostają bez zmian.

Wersję .80.4 sprawdzono jako wolną w branchach, tagach, releases i masterze przed poprawką. Po naprawie: 48 PASS w 10.88 s (nowy RED, istniejący protocol engine, source mutation, native batch i Studio). Pyright zmienionego walidatora i nowego testu: 0 errors, 0 warnings. Pierwsza próba pakietu wskazała nieistniejącą nazwę test_memory_studio.py i nie zebrała testów; poprawna nazwa test_jazn_memory_studio.py użyta w powyższym zakończonym przebiegu.

## Pozostało

Pełny aktywny pytest/Pyright/compileall i CI .80.4, finalne release/governance gates oraz nowy prywatny chain Test00 → Test01 → Test02 → Test03 → frozen13 → Test04 → Final. Wyniki .80.3 pozostają historycznym evidence. Benchmark ponownie sprawdzony bez zmiany SHA256 21753c142113c7c02600c75de0859b17d03b572656d7cd4d2bf6e76a1098fc8e. Prywatnego chaina jeszcze nie rozpoczęto. Kontynuować z aktualnego HEAD i świeżego CI; nie odtwarzać poprzednich merge ani napraw batch/Test04.
