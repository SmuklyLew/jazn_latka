# Jaźń v16.3.25.5.34 — package/runtime/plugin convergence

## Zakres

Wydanie scala jeden kontrakt release/dependency/capability bez tworzenia równoległego lifecycle do `run.py`.

### Package layer

- Pack Generator `10.1.86.0.114` rozdziela MEMORY snapshot od runnable SYSTEM release;
- SYSTEM używa canonical `create_release_staging()` dla Git checkoutu;
- finalny ZIP przechodzi bezpieczną ekstrakcję i reverify wewnętrznych integrity/provenance gates;
- exact duplicate ZIP members są odrzucane.

### Dependency/runtime layer

- `core` jest jedynym activation-required Python profile;
- `core+archive` pozostaje release profile dla sidecarów;
- `py7zr`, `pyzipper`, `rarfile` przechodzą do optional group `archive`;
- instalacja nadal jest wheel-only/hash-locked/offline;
- realny install tworzy świeży venv bez kopiowania i bez mutowania istniejącego środowiska;
- activation marker przełącza się dopiero po pełnym verify.

### Plugin/operator layer

- wprowadzono `jazn.plugins` / PyPA entry points;
- archive jest pierwszą built-in optional capability;
- stdlib ZIP pozostaje baseline, enhanced formats mogą być degraded bez blokowania core;
- Git/pip otrzymują jawne, read/inspect/operator-scoped capability reports; live daemon nie dostaje automatycznych praw do mutacji repo ani instalacji sieciowych.

### Doctor/status

Plugin i operator capability readiness są raportowane oddzielnie i nie wchodzą do `installation_ok` jako wymagane checki.

## Uzasadnienie źródłowe

Git dokumentuje, że `text` normalizuje LF w indeksie, a checkout może konwertować do CRLF. Python dokumentuje `venv` jako disposable i nieprzenośne. pip rekomenduje hash-checking i binary-only dla secure installs. PyPA rekomenduje entry points do publikowania i odkrywania pluginów. Python `zipfile` ostrzega przed ekstrakcją bez wcześniejszej inspekcji.

Źródła:

- https://git-scm.com/docs/gitattributes
- https://docs.python.org/3/library/venv.html
- https://pip.pypa.io/en/stable/topics/secure-installs/
- https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/
- https://docs.python.org/3/library/zipfile.html
