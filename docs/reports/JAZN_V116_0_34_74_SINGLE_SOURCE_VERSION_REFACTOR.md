# Jaźń .74 — kanoniczna pojedyncza wersja

## Decyzja

`latka_jazn/version.py` ma teraz jedyny edytowalny numer `PACKAGE_VERSION`.
`DISTRIBUTION_VERSION = PACKAGE_VERSION` pozostaje publicznym aliasem zgodności,
a nie drugim edytowalnym stringiem. `PACKAGE_RELEASE_NAME` nadal określa
wewnętrzny opis wydania, ale nie jest częścią dystrybucyjnej wersji Python.

Setuptools w `pyproject.toml` odczytuje bezpośrednio statyczny literal
`latka_jazn.version.PACKAGE_VERSION`. Jest to zgodne z jego obsługą
`[tool.setuptools.dynamic] version = {attr = "..."}`.

## Bezpieczeństwo i kompatybilność

- `core/version_source.py` akceptuje wyłącznie literalne przypisania lub
  konkretny alias `DISTRIBUTION_VERSION = PACKAGE_VERSION` po literalnym
  `PACKAGE_VERSION`; nie wykonuje kodu ani arbitralnych wyrażeń.
- `tools/release_metadata_sync.py` używa tego samego bezpiecznego czytnika,
  również podczas odczytu pliku z wcześniejszego commita Git.
- `tools/jazn_version_rebuild.py` dla nowych wydań zapisuje wersję bez
  `v` i zachowuje alias, ale nadal odczytuje historyczne dwa literały
  oraz wersje `v...`. Dodatkowy segment oznacza rozszerzenie numeru,
  nie osobny niezależny identyfikator.
- Audyt wersji i Version Rebuild rozpoznają zarówno kanoniczny
  `pyproject.toml`, jak i historyczne pliki ze starym atrybutem.
- Format liczbowy `N(.N)*` jest zgodny z PEP 440; uproszczenie całego
  wielosegmentowego schematu nie jest częścią tego refaktoringu.

## Odbiór

Zachować dotychczasowe testy, dodać testy aliasu AST, braku wykonania
kodu, kompatybilności starego formatu, zapisu Version Rebuild i statycznego
`pyproject.toml`. Nie zgłaszać gotowości do merge bez końcowego CI
dla `source SHA`, zatwierdzonej synchronizacji manifestów i wszystkich
wcześniej otwartych warunków PR #416.

Źródła:
- https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html
- https://packaging.python.org/en/latest/specifications/version-specifiers/
- https://peps.python.org/pep-0621/
