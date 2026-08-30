# Tool domain documentation

Ten katalog zawiera aktywne kontrakty operatorskie i dokumentację narzędzi, których ścieżki są częścią bieżących testów lub procedur repozytorium.

## Current

- `MEMORY_SQLITE_TEST_04.md` — aktywny, testowany kontrakt operatorski Testu 04;
- `PRIVATE_MEMORY_VALIDATION.md` — aktywny, testowany kontrakt prywatnej walidacji pamięci dla Issue #59.

Architektura i ogólna dokumentacja pamięci znajduje się w `../memory/`. Jawnie zakończone lub superseded noty narzędziowe są w `../archive/tools/`.

Nie przenoś dokumentu z tego katalogu tylko dlatego, że dotyczy pamięci, jeżeli jego ścieżka jest częścią testowanego kontraktu operatora. Najpierw należy zmienić sam kontrakt i jego testy w osobnym patchu systemowym.
