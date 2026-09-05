# Tool domain documentation

Ten katalog zawiera aktywne kontrakty operatorskie i dokumentację narzędzi, których ścieżki są częścią bieżących testów lub procedur repozytorium.

## Current

- `MEMORY_SQLITE_TEST_04.md` — aktywny, testowany kontrakt operatorski Testu 04;
- `PRIVATE_MEMORY_VALIDATION.md` — aktywny, testowany kontrakt prywatnej walidacji pamięci dla Issue #59;
- `JAZN_DEPENDENCY_STUDIO.md` — Wheelhouse Contract v3, natywne locki, cross-target replay, offline bootstrap środowiska Python i dependency readiness Jaźni;
- `JAZN_PYTHON_RUNTIME_BUNDLE.md` — zweryfikowany przenośny interpreter i vendoring z Wheelhouse Contract v3;
- `../runtime/JAZN_PACK_GENERATOR_V101860111_ARCHIVER.md` — aktywny kontrakt czystego archiwizera Pack Generator 10.1.86.0.111.

Poprzedni `../runtime/JAZN_PACK_GENERATOR_V101860_CROSS_TARGET.md` opisuje historyczny kontrakt generatora 10.1.86.0. Logika `package_distribution`, wheelhouse i Python runtime bundle pozostaje osobnym subsystemem Jaźni i nie jest częścią nowego archiwizera.

Architektura i ogólna dokumentacja pamięci znajduje się w `../memory/`. Jawnie zakończone lub superseded noty narzędziowe są w `../archive/tools/`.

Nie przenoś dokumentu z tego katalogu tylko dlatego, że dotyczy pamięci, jeżeli jego ścieżka jest częścią testowanego kontraktu operatora. Najpierw należy zmienić sam kontrakt i jego testy w osobnym patchu systemowym.
