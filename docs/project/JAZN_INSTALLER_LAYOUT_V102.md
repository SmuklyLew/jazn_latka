# Jaźń v102 — wybór lokalizacji Pythona

Installer `setup.ps1`/`setup.sh` to cienkie launchery wspólnego rdzenia.
Dependency Studio pozostaje jedynym wykonawcą zweryfikowanych instalacji.

## Pierwsza instalacja

Domyślnie instalacja wybiera `--layout project` tworzący świeży
`$ROOT/.venv`. Oba profile `core`, `run-studio`, `mcp-http` instalują się
do tego samego interpretera, ze zweryfikowanego wheelhouse:
`--no-index --require-hashes --only-binary=:all:`.
Po `pip check`, import smoke i `pip inspect` aktualizowany jest marker.

Istniejącego `.venv` nigdy nie nadpisujemy. Naprawa i aktualizacja mogą
wybrać `--layout managed`, który tworzy nowy zweryfikowany interpreter
obok dotychczasowego. To zachowuje istniejące instalacje v101 i możliwość
kontrolowanego rollbacku. Szybki `doctor` niczego nie instaluje i nie
uruchamia daemona.

## Maintenance i zakres

Venv jest odtwarzalne i **nieprzenośne**; nie zastępuj go przez rename.
Przejście aktywnej instancji na inny interpreter wymaga oddzielnego,
świadomie zatwierdzonego maintenance i weryfikacji po zamknięciu procesu.
Nie wykonujemy cichej migracji już działających kopii.

MEMORY, markery, logi, ustawienia operatora i wheelhouse pozostają poza
`.venv`. Programy systemowe (Python bazowy, Ollama, Git, cloudflared)
wykrywa się lub konfiguruje z udziałem użytkownika; bez zgody nie
instaluje się nowych programów ani nie publikuje publicznego MCP.

Źródła:
- https://docs.python.org/3/library/venv.html
- https://pip.pypa.io/en/stable/topics/secure-installs/
