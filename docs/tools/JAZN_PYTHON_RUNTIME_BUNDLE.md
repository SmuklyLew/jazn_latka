# Jaźń Python Runtime Bundle — prywatny interpreter i automatyczny target

## Status

`16.3.25.5.15-python-runtime-bundle-auto-target` wprowadza kontrakt prywatnego interpretera CPython jako osobnego, weryfikowanego artefaktu release. Repozytorium nie przechowuje binarnych runtime'ów Pythona. Kod źródłowy przechowuje generator, walidator, selektor targetu, bootstrap i launchery; gotowe runtime ZIP-y są artefaktami dystrybucyjnymi.

## Dlaczego nie kopiujemy `.venv` ani `site-packages`

CPython dokumentuje, że środowiska `venv` są zasadniczo nieprzenośne, ponieważ skrypty zawierają absolutne ścieżki do interpretera. Dlatego Jaźń nie transportuje gotowego `.venv` i nie kopiuje losowego `site-packages` z hosta jako źródła prawdy.

Źródło: https://docs.python.org/3/library/venv.html

Zależności Pythona są najpierw rozwiązywane jako zweryfikowany wheelhouse Jaźni, a następnie — podczas budowy runtime bundle na natywnym targetcie i tej samej wersji CPython — instalowane do kontrolowanego katalogu `packages/` przez builder Python. Runtime użytkownika nie pobiera ich z sieci.

## Windows

Dla Windows preferowanym upstreamem jest oficjalny CPython embeddable package. Python opisuje go jako minimalne, prawie całkowicie odizolowane środowisko przeznaczone do bycia częścią innej aplikacji. Dokumentacja zaleca, aby third-party packages instalował instalator aplikacji, a nie aby embedded Python był zarządzany jak zwykłe środowisko przez `pip`.

Źródło: https://docs.python.org/3/using/windows.html#the-embeddable-package

Plik `._pth` dostarczany z embedded distribution ogranicza `sys.path`, ignoruje registry i zmienne środowiskowe oraz uruchamia isolated mode. Jaźń dodatkowo startuje interpreter z `-I`, czyści `PYTHONPATH`, `PYTHONHOME`, user-site/venv state i przechodzi przez `jazn_runtime_bootstrap.py`, który dodaje wyłącznie:

1. root kodu Jaźni;
2. `packages/` z runtime bundle;
3. ścieżki stdlib/private runtime należące do bieżącego interpretera.

Źródło: https://docs.python.org/3/library/sys_path_init.html#pth-files

## Linux

CPython nie publikuje oficjalnego odpowiednika Windowsowego embeddable ZIP dla wszystkich targetów Linux. Kontrakt Jaźni dopuszcza przygotowany runtime z jawnie zapisanym providerem i source reference. Jednym z możliwych, jawnie audytowanych upstreamów jest Astral `python-build-standalone`, który publikuje target-specific przenośne CPython-y i rekomenduje warianty `*-unknown-linux-gnu` do pracy z compiled extensions.

Źródła:

- https://github.com/astral-sh/python-build-standalone/blob/main/docs/running.rst
- https://github.com/astral-sh/python-build-standalone/blob/main/docs/quirks.rst

Provider nie jest automatycznie zaufany przez nazwę. Release Jaźni musi przypiąć konkretny source artifact, jego SHA-256, licencje/provenance i wynik natywnego cleanroomu. `glibc` i `musl` są osobnymi targetami; selektor nie zgaduje ich zgodności.

## Target

Kanoniczny target runtime zawiera:

- platform alias (`windows-x64`, `windows-arm64`, `linux-x64`, `linux-arm64`, ...);
- CPython minor (`3.12`, `3.13`, `3.14`);
- implementation (`cp`);
- ABI (`cp312`, `cp313`, `cp314`);
- architecture;
- libc family dla Linux (`glibc` albo `musl`).

Przykładowe identyfikatory:

```text
windows-x64-py314
windows-x64-py313
linux-x64-glibc-py314
linux-x64-musl-py314
```

Domyślna preferencja selektora to `3.14 -> 3.13 -> 3.12`. Operator może wymusić minor przez `JAZN_PYTHON_VERSION`. Brak zgodnego targetu kończy się fail-closed; nie jest zastępowany podobnie nazwaną paczką.

## Artefakty

Pojedynczy runtime ZIP zawiera przygotowany prywatny interpreter oraz:

```text
JAZN_PYTHON_RUNTIME_MANIFEST.json
packages/
<interpreter i stdlib/runtime files>
```

Manifest `jazn_python_runtime_manifest/v1` przechowuje pełny inventory plików, rozmiary, SHA-256, target, interpreter relative path, provider/source reference i kontrakt izolacji.

Zestaw wielu runtime'ów używa:

```text
JAZN_PYTHON_RUNTIME_SET.json
JAZN_PYTHON_RUNTIME_INDEX.tsv
```

JSON jest kanonicznym kontraktem programu. TSV jest minimalnym indeksem bootstrapowym dla launcherów systemowych, zanim dostępny jest Python Jaźni.

## Vendoring zależności

`python_runtime_studio build --dependency-bundle ...` może przygotować `packages/` wyłącznie ze zweryfikowanego `jazn_dependency_wheelhouse/v2`. Builder Python musi odpowiadać temu samemu OS/architecture/Python/ABI/libc co target runtime. Instalacja używa:

```text
python -m pip install
  --no-index
  --only-binary=:all:
  --require-hashes
  --find-links <verified wheelhouse>
  -r JAZN_WHEELHOUSE_REQUIREMENTS.txt
  --target <runtime>/packages
```

Następnie wykonywany jest import-smoke direct requirements. Nie ma fallbacku do PyPI ani sdistów.

## CLI

Wykrycie hosta:

```text
python -X utf8 -m latka_jazn.tools.python_runtime_studio --json detect-host
```

Budowa przygotowanego runtime bundle:

```text
python -X utf8 -m latka_jazn.tools.python_runtime_studio --json build \
  --project-root . \
  --runtime-root <prepared-runtime> \
  --output <runtime.zip> \
  --target windows-x64 \
  --python-version 3.14 \
  --provider python.org-embeddable \
  --source-reference <pinned-upstream-artifact> \
  --interpreter python.exe \
  --dependency-bundle <verified-wheelhouse>
```

Linux wymaga jawnego `--libc-family glibc|musl`.

Weryfikacja:

```text
python -X utf8 -m latka_jazn.tools.python_runtime_studio --json verify --bundle <runtime.zip>
```

Zbudowanie katalogu wielu targetów:

```text
python -X utf8 -m latka_jazn.tools.python_runtime_studio --json build-set \
  --output-dir <dir> \
  --bundle <runtime-a.zip> \
  --bundle <runtime-b.zip>
```

## Package Distribution

`latka_jazn.tools.package_distribution` przyjmuje powtarzalne `--python-runtime-bundle`. Zweryfikowany runtime sidecar musi zgadzać się z `--target` i `--python-version`. System ZIP otrzymuje wirtualne, zahashowane `JAZN_PYTHON_RUNTIME_SET.json` i `JAZN_PYTHON_RUNTIME_INDEX.tsv`; runtime ZIP pozostaje osobnym outputem z rolą `python-runtime`.

To zachowuje rozdział odpowiedzialności:

```text
SYSTEM source ZIP
+ verified dependency sidecar
+ verified Python runtime sidecar
= portable execution set
```

## Startup

Windows `JAZN.cmd`:

1. jeśli istnieje `JAZN_PYTHON_RUNTIME_SET.json`, nie zaczyna od globalnego `py.exe`/`python.exe`;
2. uruchamia stdlib/systemowy PowerShell bootstrap;
3. wybiera zgodny runtime według OS/arch/Python preference;
4. weryfikuje outer SHA-256;
5. bezpiecznie materializuje ZIP do host-level `workspace_runtime/local_resources/python_runtime/runtimes/`;
6. weryfikuje manifest i każdy plik;
7. uruchamia prywatny interpreter przez `-I -X utf8` i `jazn_runtime_bootstrap.py`.

Dopiero brak runtime-set contractu oznacza thin/developer fallback do Pythona hosta.

POSIX `./jazn` korzysta z bootstrap indexu i outer SHA-256; do pierwszej materializacji runtime ZIP wymaga lokalnego `unzip` oraz `sha256sum`/`shasum`. Już zmaterializowany runtime nie potrzebuje sieci. Linux target selection zawsze uwzględnia libc.

## Granica prawdy

- Runtime ZIP i jego manifest nie dowodzą aktywnej Jaźni; są wyłącznie zweryfikowanym interpreterem wykonawczym.
- `JAZN_PYTHON_RUNTIME_SET.json` nie pozwala na network fallback.
- Filename nie jest dowodem targetu; liczą się manifest, SHA i zgodność hosta.
- Repo nie przechowuje binarnych runtime'ów, wheelhouse'y ani gotowych environmentów.
- Aktualizacja upstream Pythona lub dependencies wymaga nowego verified artifactu i testów cleanroom; runtime nie aktualizuje się sam podczas tury rozmowy.
