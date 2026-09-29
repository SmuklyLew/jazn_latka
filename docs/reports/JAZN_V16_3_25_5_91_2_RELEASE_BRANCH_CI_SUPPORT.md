# Jaźń v16.3.25.5.91.2 — release branch CI support

## Cel

Domknąć jedyną wartościową różnicę pozostałą po zamkniętym PR #297, bez scalania jego rozbieżnej historii.

Bazą tej poprawki jest aktualny `master` po scaleniu PR #296 i po pełnym zielonym CI.

## Zakres

- `.github/workflows/release-hardening.yml`
  - `release/**` uruchamia workflow po pushu;
  - `release/*` jest dozwolonym targetem dla kanonicznego writer-a metadata;
  - diagnostyka listuje rodzinę `release`.
- `.github/workflows/stable-test-contracts.yml`
  - `release/**` uruchamia synchronizację i walidację katalogu Test Studio.
- `tests/test_release_workflow_hardening.py`
  - kontrakt wymaga `release/**` w obu workflow;
  - kontrakt wymaga `release/*` w allowliście writer-a metadata.
- `latka_jazn/version.py`
  - wersja `16.3.25.5.91.2-release-branch-ci-support`.

## Lineage

- baza: `8497a0d4a2e714dcc8040d33338c4f87a6560b8c`;
- poprzednia linia: `16.3.25.5.91.1-chatgpt-plugin-runtime-ci-convergence`;
- PR #297 zamknięty jako superseded przez #296;
- nie przenosimy starszej wersji testu update-continuation z #297.

## Metadata i katalog testów

`SOURCE_PROVENANCE.json`, `PACKAGE_INTEGRITY_MANIFEST.json` i katalog Test Studio mają być synchronizowane przez istniejące kanoniczne workflow repozytorium po source commicie, zamiast ręcznej edycji.

## Kryterium merge

PR może być scalony dopiero po zielonych workflow uruchomionych ze świeżej gałęzi.


## Walidacja iteracyjna

Pierwszy pełny deterministic suite wykrył jeden rzeczywisty fail:
`tests/test_chatgpt_capability_loader_convergence.py` nadal wymagał wersji
`16.3.25.5.91.1-chatgpt-plugin-runtime-ci-convergence`.

Kontrakt został zaktualizowany do:
`16.3.25.5.91.2-release-branch-ci-support`.
Zmiana jest ponownie przepuszczana przez pełne CI; nie osłabiono ani nie pominięto testu.
