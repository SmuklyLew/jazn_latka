# Jaźń v16.3.25.5.99 — PDF capability / offline dependency convergence

## Cel

Ta aktualizacja usuwa fałszywą zależność aktywacji Jaźni od biblioteki PDF,
bez osłabiania zabezpieczeń dependency layer ani bez dodawania sieciowego
`pip install` do bootstrapu runtime.

Stan, który ujawnił problem, był następujący: host miał `pypdf 5.9.0`, podczas
gdy bieżące wydanie deklarowało `pypdf>=6.19.0,<7` jako bazową zależność
`project.dependencies`. Dependency preflight traktował więc brak zgodnej wersji
jak brak activation-required `core` i blokował start całego runtime.

## Ustalenia

1. Aktywny kod runtime nie importuje `pypdf` i zwykły start/dialog Jaźni nie
   wymaga API PDF.
2. `pypdf` jest capability dokumentową, a nie warunkiem lifecycle, pamięci,
   finalizacji ani routingu rozmowy.
3. Projekt ma już kanoniczny, fail-closed mechanizm dystrybucji zależności:
   Wheelhouse Contract v3, hash-lock, dependency sidecar, clean-room replay i
   instalację offline z `--no-index --only-binary=:all: --require-hashes`.
4. PyPI opublikowało `pypdf 6.19.0` 2026-09-16 jako uniwersalny wheel
   `pypdf-6.19.0-py3-none-any.whl`. Jego SHA-256 to
   `7e5d6e730e7dae87d560a2cee218b852f6498c8be61966f3cd02ead971e48d14`.
5. Wydanie 6.19.0 zawiera poprawkę bezpieczeństwa ograniczającą rozmiar
   alfabetycznych page labels. Minimalna wersja `>=6.19.0,<7` pozostaje więc
   zachowana dla capability PDF.

## Zmiana architektoniczna

### Activation

`activation_profiles=["core"]` pozostaje bez zmian.

`pypdf>=6.19.0,<7` zostaje przeniesione z:

`[project].dependencies`

do:

`[project.optional-dependencies].pdf`

oraz profilu `pdf` o roli `runtime_optional`.

W rezultacie brak lub niezgodna wersja `pypdf` nie blokuje zwykłego startu,
statusu, dialogu ani transportu ChatGPT/Ollama.

### Release

Standardowy release sidecar nadal dostarcza pypdf. Jawny release profile zmienia
się z:

`core+archive`

na:

`core+archive+pdf`.

Sześć istniejących target-specific hash-locków (Windows/Linux x64,
Python 3.12/3.13/3.14) zostaje przeniesionych do nowej ścieżki bez ręcznego
przepisywania zawartości. Wheel pypdf pozostaje przypięty do 6.19.0 i tego
samego SHA-256.

### Bootstrap

Nie powstaje żaden fallback sieciowy.

Bootstrap nadal:
- akceptuje zgodny ambient/managed activation core;
- może użyć wyłącznie zweryfikowanego lokalnego wheelhouse/sidecara;
- instaluje offline przez `--no-index`, `--find-links`,
  `--only-binary=:all:` i `--require-hashes`;
- fail-closed odrzuca brakujący, zmieniony lub niedopasowany dependency artifact.

## Naprawiony drift diagnostyczny

`main.py` mówił, że aktywacja wymaga „required core+archive Python dependencies”.
Było to niespójne z registry, gdzie activation profile już wcześniej wynosił
wyłącznie `core`. Komunikat został poprawiony na
„activation-required core Python dependencies”.

## Zmieniane obszary

- `pyproject.toml`;
- `latka_jazn/resources/dependencies/profiles.json`;
- release locks i ich README;
- workflow `dependency-artifacts`;
- workflow `package-distribution-cleanroom`;
- `main.py` truth boundary;
- wersja i startup contract;
- testy Dependency Studio / archive / ChatGPT identity;
- nowy test `test_pdf_dependency_capability_convergence.py`;
- dokumentacja polityki zależności i Dependency Studio.

## Błędy wykryte podczas implementacji i naprawione od razu

1. **Cross-target replay używał starego zestawu profili.**
   Po zmianie ścieżki locka na `core+archive+pdf` workflow nadal wywoływał
   Dependency Studio z `--profile core --profile archive`. Dałoby to inny
   `dependency_contract_fingerprint` niż natywny sidecar. Replay został
   zsynchronizowany do `core,archive,pdf`.

2. **Clean-room polegał na przypadkowym stanie GitHub runnera.**
   Historyczny test zakładał brak `py7zr/pyzipper`, ale po przeniesieniu
   `pypdf` poza core nie dowodziło to już braku activation dependencies.
   Consumer tworzy teraz izolowany `venv --without-pip`, bez system
   site-packages, i jawnie potwierdza brak `packaging`, `tzdata`, `pypdf`,
   `py7zr` i `pyzipper` przed testem offline handoff.

3. **Test prestart był związany z poprzednią nazwą i komendą workflow.**
   Poprzednia wersja testu została zachowana append-only w `tests/archive/`,
   a aktywny kontrakt sprawdza nowy dependency-empty bootstrap i wykonywanie
   `run.py` przez izolowany interpreter.

4. **Release-hardening dry-run nie obejmował PDF.**
   Macierz targetów została rozszerzona z `core,archive` do
   `core,archive,pdf`, aby walidować ten sam profil, który jest faktycznie
   transportowany w release sidecarze.

## Acceptance

Branch nie jest release candidate dopóki nie przejdą rzeczywiste:
- aktywne testy pytest;
- compileall;
- release-hardening / metadata sync;
- dependency-artifacts dla wspieranych targetów;
- opposite-OS lock replay;
- package-distribution clean-room;
- doctor i package smoke tam, gdzie workflow je wykonuje.

Nie wolno zastępować tych dowodów samym faktem, że deklaracje TOML/JSON są spójne.

## Źródła zewnętrzne

- PyPI, pypdf 6.19.0:
  https://pypi.org/project/pypdf/6.19.0/
- pypdf upstream release 6.19.0:
  https://github.com/py-pdf/pypdf/releases/tag/6.19.0
- pypdf security documentation:
  https://pypdf.readthedocs.io/en/stable/user/security.html
- pip install documentation (`--no-index`, `--find-links`):
  https://pip.pypa.io/en/stable/cli/pip_install/

## Truth boundary

Ta zmiana nie twierdzi, że pypdf jest zbędny dla funkcji PDF. Twierdzi tylko,
że funkcje PDF nie są warunkiem aktywacji podstawowego runtime Jaźni.
Capability PDF pozostaje fail-closed względem własnej zależności i jest nadal
transportowana w zweryfikowanym release sidecarze.
