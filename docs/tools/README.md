# Tool domain documentation

Ten katalog zawiera aktywne kontrakty operatorskie i dokumentację narzędzi, których ścieżki są częścią bieżących testów lub procedur repozytorium.

## Current

- `MEMORY_SQLITE_TEST_04.md` — aktywny, testowany kontrakt operatorski Testu 04;
- `PRIVATE_MEMORY_VALIDATION.md` — aktywny, testowany kontrakt prywatnej walidacji pamięci dla Issue #59;
- `JAZN_DEPENDENCY_STUDIO.md` — Wheelhouse Contract v3, natywne locki, cross-target replay, offline bootstrap środowiska Python i dependency readiness Jaźni;
- `JAZN_PYTHON_RUNTIME_BUNDLE.md` — zweryfikowany przenośny interpreter i vendoring z Wheelhouse Contract v3;
- `../runtime/JAZN_PACK_GENERATOR_V101860114_CANONICAL_SYSTEM_RELEASE.md` — aktywny kontrakt Pack Generator 10.1.86.0.114: canonical SYSTEM release + extract-and-reverify; MEMORY pozostaje folder snapshotem.
- `../runtime/JAZN_PACK_GENERATOR_V101860113_FOLDER_SNAPSHOT.md` — historyczny kontrakt selected-folder v113 zachowany jako kontekst migracji.

Poprzednie kontrakty Pack Generatora, w tym v10.1.86.0.112 z fail-closed EOL, są historyczne. Materiał bezpośrednio wycofany w aktualizacji v113 znajduje się w `.archives/package_generator_pre_v101860113/`.

Logika `package_distribution`, wheelhouse i Python runtime bundle pozostaje osobnym subsystemem Jaźni i nie jest częścią archiwizera.

Architektura i ogólna dokumentacja pamięci znajduje się w `../memory/`. Jawnie zakończone lub superseded noty narzędziowe są w `../archive/tools/` albo w repozytoryjnym `.archives/`, zależnie od kontraktu pochodzenia.

Nie przenoś dokumentu z tego katalogu tylko dlatego, że dotyczy pamięci, jeżeli jego ścieżka jest częścią testowanego kontraktu operatora. Najpierw należy zmienić sam kontrakt i jego testy w osobnym patchu systemowym.
