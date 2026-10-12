# Jaźń v16.3.25.3 — release metadata semantics hardening

## Cel

Hotfix rozdziela trzy wcześniej mieszane klasy identyfikatorów:

1. **wersja schematu/kontraktu** — stabilna, zmieniana wyłącznie przy zmianie formatu lub semantyki kontraktu;
2. **wersja runtime/release** — nadal związana z kanonicznym `PACKAGE_VERSION` / `PACKAGE_VERSION_FULL`;
3. **kompatybilność i migracja** — jawna, z rozpoznaniem starszych markerów schematu sprzęgniętych z numerem runtime.

Nie zmieniono historycznych archiwów. `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` nie są edytowane ręcznie; po zmianach kodu mają zostać zsynchronizowane kanonicznym `release_metadata_sync` zgodnie z `AGENTS.md`.

## Dlaczego poprzednia semantyka była błędna

Przed tym hotfixem `latka_jazn/version.py::schema_version()` domyślnie zwracał:

```text
<component>/<PACKAGE_VERSION>
```

W efekcie bump patcha runtime automatycznie zmieniał pozorną wersję każdego kontraktu, nawet gdy format danych się nie zmieniał. Ten wzorzec był wykorzystywany repozytoryjnie przez moduły Core, Memory, Tools, NLP, Bridge, diagnostykę i `main.py`.

Najbardziej krytyczny przypadek znajdował się w release metadata:

- `source_provenance/<runtime patch>`;
- `package_integrity_manifest/<runtime patch>`;
- `base_version`, `runtime_version` i `update_version` zapisywane jako ta sama bieżąca wersja;
- `base_merge_commit` pełniący faktycznie rolę immutable source commit, mimo historycznej nazwy.

To utrudniało odróżnienie zmiany formatu od zwykłego wydania oraz zacierało lineage.

## Nowy model wersjonowania

### A. Stabilne schematy kontraktów

`contract_schema_version(component)` zwraca identyfikator niezależny od `PACKAGE_VERSION`.

Aktualne jawne wersje:

- `source_provenance/v2`;
- `package_integrity_manifest/v2`;
- `voice_source_contract/v2` (zachowanie istniejącego kontraktu);
- pozostałe komponenty korzystające z centralnego `schema_version()` przechodzą na stabilny domyślny `v1`, dopóki ich format nie zostanie świadomie zmieniony.

`schema_version(component)` jest zachowany jako kompatybilny interfejs, ale jego domyślne znaczenie jest teraz kontraktowe. Jawne `schema_version(component, version=...)` zachowuje historyczne zachowanie runtime-coupled wyłącznie dla zgodności; nowy kod powinien używać nazwanej funkcji runtime/release.

### B. Runtime i release

Dodane zostały jednoznaczne funkcje:

- `runtime_version_marker(component)` — zależny od `PACKAGE_VERSION`;
- `release_version_marker(component)` — zależny od `PACKAGE_VERSION_FULL`.

Dzięki temu kod deklaruje intencję zamiast używać słowa `schema` do identyfikowania wydania.

### C. Jawna kompatybilność i migracja

`schema_contract_metadata(component)` publikuje:

- bieżący stabilny schema ID;
- jawnie akceptowane stabilne wersje;
- politykę starszych markerów runtime-coupled;
- docelowy schema ID migracji.

`schema_version_compatibility(component, observed)` rozróżnia:

- `current_contract_schema`;
- `legacy_runtime_coupled_schema` — zgodny, lecz wymagający migracji;
- `unsupported_schema` — niezgodny.

Dzięki temu stary artefakt nie jest ani fałszywie „bieżący”, ani automatycznie odrzucany tylko dlatego, że powstał przed rozdzieleniem semantyki.

## Proweniencja po hotfixie

Nowe dokumenty provenance zawierają osobne pola:

- `schema_version` — format dokumentu;
- `schema_contract` — zasady kompatybilności;
- `runtime_version` — runtime, którego dotyczy artefakt;
- `release_version` — bieżąca tożsamość wydania;
- `source_commit` — immutable code/content commit;
- `source_version` — wersja zadeklarowana przez source commit;
- `lineage.base_branch` — branch bazowy;
- `lineage.base_commit` — rzeczywisty merge-base, gdy jest rozwiązywalny;
- `lineage.base_version` — wersja zadeklarowana w merge-base, gdy jest rozwiązywalna.

Dla zgodności z istniejącymi readerami pozostają legacy aliases:

- `base_merge_commit -> source_commit`;
- `base_version -> source_version`;
- `update_version -> release_version`.

Stare pola nie zostały po cichu przedefiniowane. Ich znaczenie jest zachowane, a poprawna nowa semantyka ma osobne pola.

## Manifest integralności po hotfixie

Kanoniczny release manifest publikuje:

- `schema_version = package_integrity_manifest/v2`;
- `schema_contract`;
- `release_version`;
- `artifact_identity.runtime_version`;
- `artifact_identity.package_version`;
- `artifact_identity.release_version`;
- legacy alias `version -> release_version`.

Weryfikacja hashy i rozdział static/mutable pozostają niezależne od tej zmiany.

## Audyt repozytorium

Repo-wide wyszukiwanie wykazało centralne użycie `schema_version()` w aktywnych modułach m.in.:

- Core: startup, daemon/autostart, runtime session, host pre-response, chat command, candidate guard, memory recall observability/presenter, epistemic ledger, typed memory policy, secure host gateway, Voice E2E;
- Memory: dziennik, raw importer/status, requirements ledger, session continuity, recall contract, runtime persistence/install, living memory gateway;
- NLP: dictionary readiness;
- Tools: chat export importer, Memory Rebuild source fidelity/union oraz release tooling;
- CLI/entrypoints: diagnostics i `main.py`.

Zamiast ręcznie utrzymywać kilkadziesiąt niezależnych numerów zależnych od patcha runtime, usunięto źródło błędu centralnie: domyślne `schema_version()` ma teraz semantykę stabilnego kontraktu. Miejsca, które naprawdę wymagają identyfikatora runtime/release, mają oddzielne funkcje.

Historyczne kopie w `.archives` oraz dokumenty archiwalne nie są migrowane przez hotfix.

## Testy regresyjne dodane w branchu

`tests/test_release_metadata_semantics_v163253.py` sprawdza:

1. niezależność schema ID od `PACKAGE_VERSION`;
2. jawne runtime/release markers;
3. klasyfikację legacy runtime-coupled schema jako zgodnej migracji, nie jako bieżącego schematu;
4. rozdział schema/release/source/legacy aliases w provenance;
5. rzeczywisty lineage merge-base w canonical release metadata;
6. stabilny schema ID canonical i generic package integrity manifest.

Pełny wynik testów musi pochodzić z rzeczywistego uruchomienia pytest/CI. Sam zapis zmian w GitHub nie jest dowodem wykonania testów.

## Źródła projektowe

### Semantic Versioning 2.0.0

https://semver.org/

SemVer definiuje znaczenie numeru wydania/publicznego API: patch oznacza kompatybilną poprawkę, minor kompatybilną funkcjonalność, major zmianę niekompatybilną. Numer wydania nie jest automatycznie wersją każdego serializowanego schematu używanego wewnątrz aplikacji.

### SLSA v1.2 — Provenance

https://slsa.dev/spec/v1.2/provenance

SLSA definiuje provenance jako weryfikowalną informację opisującą skąd pochodzi artefakt oraz gdzie, kiedy i jak został wytworzony. W modelu SLSA identyfikacja artefaktu, build/source provenance i wersja formatu atestacji są odrębnymi pojęciami.

### SLSA Build Provenance

https://slsa.dev/spec/v1.2/build-provenance

Predicate type ma własną wersję kontraktu. Zmiany kompatybilne i niekompatybilne formatu są wersjonowane według semantyki samego formatu, a nie numeru wersji opisywanego artefaktu.

### JSON Schema — Specification / dialects

https://json-schema.org/specification

https://json-schema.org/understanding-json-schema/reference/schema

JSON Schema rozdziela wersję/dialekt schematu od danych, które są przez ten schemat opisywane. `$schema` identyfikuje semantykę języka schematu, a migracje między draftami są osobnym procesem.

## Zakres świadomie niezmieniony

- Memory Rebuild semantics;
- prywatna pamięć;
- Voice runtime readiness;
- attachment ingress;
- dream/cloud/cognitive redesign;
- historyczne `.archives`;
- ręczne hashe w canonical release metadata.
