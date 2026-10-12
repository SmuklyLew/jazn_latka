# Jaźń v16.3.25.5.34 — package/runtime/plugin convergence plan

## Cel

Jedna gałąź konwergencyjna realizuje kolejno:

1. Pack Generator `10.1.86.0.114`: SYSTEM z canonical release staging, nie z working tree;
2. finalne `safe extract -> PACKAGE_INTEGRITY_MANIFEST -> SOURCE_PROVENANCE` reverify;
3. Dependency Studio jako jedyny manager zależności: lock/download/verify/wheelhouse/offline install;
4. świeże managed Python environments bez kopiowania ani mutacji istniejącego `.venv`;
5. `jazn.plugins` + PyPA entry points;
6. `archive` jako pierwsza opcjonalna capability/plugin, przy zachowaniu release sidecar `core+archive`;
7. Git i pip jako operator-only capabilities bez automatycznych praw live daemona;
8. doctor/status raportują optional capability readiness oddzielnie od runtime core.

## Niezmienniki

- `run.py` pozostaje jedynym publicznym lifecycle Jaźni.
- Runnable SYSTEM z checkoutu Git powstaje wyłącznie z czystego HEAD.
- `create_release_staging()` materializuje bloby Git; working-tree EOL nie są źródłem release bytes.
- MEMORY pozostaje byte-exact snapshotem wybranego filesystemu.
- runtime nigdy nie pobiera zależności z sieci; instalacja korzysta z verified local wheelhouse, hash lock i wheels only.
- managed venv powstaje od nowa pod finalną ścieżką, przechodzi `pip check`, import smoke i `pip inspect`, a dopiero potem atomowo przełączany jest marker aktywacji.
- optional plugin failure nie może wyłączyć core.
- Git/pip nie są raw command API żywego daemona.

## Etapy i kryteria akceptacji

### A — generator 10.1.86.0.114

- SYSTEM/SYSTEM+MEMORY wybiera `materialize_canonical_staging`;
- checkout Git używa `latka_jazn.tools.release_staging.create_release_staging`;
- export bez `.git` może przejść tylko przez verified-export smoke staging;
- staging inventory pochodzi z wewnętrznego manifestu integralności;
- metadata: `canonical_release_bytes=true`, EOL policy fail-closed.

### B — extract-and-reverify

Po zbudowaniu logicznego ZIP, ale przed split/publikacją:

- preflight nazw i typów ZIP;
- odrzucenie traversal, symlinków, casefold collisions i duplicate members;
- ekstrakcja do świeżego katalogu stagingowego;
- wewnętrzny `PACKAGE_INTEGRITY_MANIFEST.json` musi przejść;
- provenance musi mieć status `verified_export_without_git_history`.

### C/D — dependencies + managed Python

- activation profile = `core`;
- release profile = `core+archive`, aby istniejące sidecary release nadal dostarczały rozszerzoną capability;
- `archive` przeniesione do `[project.optional-dependencies].archive`;
- install: `--no-index --only-binary=:all: --require-hashes --find-links`;
- każdy realny install tworzy nowy, path-stable venv;
- poprzedni aktywny env pozostaje nietknięty aż do pomyślnej weryfikacji nowego;
- aktywacja = atomowa zamiana JSON marker przez `os.replace`.

### E/F — plugin framework + archive

- group: `jazn.plugins`;
- built-in `archive` ma ten sam kontrakt co entry point;
- third-party entry points są domyślnie tylko odkrywane, bez importowania kodu;
- jawne ładowanie izoluje wyjątki jako `quarantined`/`failed`;
- baseline ZIP ze stdlib działa bez archive extras;
- 7z/AES ZIP/RAR są enhanced optional readiness.

### G/H — operator capabilities + doctor

- Git: read/provenance/release/update-staging tylko jawnie przez operatora; brak live daemon `pull/checkout/reset/merge/push`;
- pip: backend Dependency Studio; runtime network disabled;
- doctor/status pokazują plugin i operator capability readiness, ale ich brak nie ustawia `installation_ok=false`.

## Źródła techniczne

- Git `gitattributes`: https://git-scm.com/docs/gitattributes
- Python `venv`: https://docs.python.org/3/library/venv.html
- pip secure installs: https://pip.pypa.io/en/stable/topics/secure-installs/
- PyPA plugin discovery / entry points: https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/
- Python `zipfile`: https://docs.python.org/3/library/zipfile.html

## Final acceptance

Minimalnie: compileall, Pyright active tree, targeted pytest, pełny deterministic pytest bez live_model/live_mcp, release-hardening, persistent runtime E2E, package-distribution cleanroom Windows/Linux i generator SYSTEM integration. PR nie jest gotowy, dopóki wymagane checki GitHub nie są zielone.
