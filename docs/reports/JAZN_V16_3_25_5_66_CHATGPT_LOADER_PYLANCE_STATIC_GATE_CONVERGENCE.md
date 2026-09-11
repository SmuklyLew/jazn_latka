# Jaźń v16.3.25.5.66 — ChatGPT loader + Pylance/Pyright static-gate convergence

## Zakres

Aktualizacja naprawia dwa powiązane problemy obserwowane po wydaniu v16.3.25.5.65:

1. host ChatGPT mógł wykonać zwykłą odpowiedź albo host-tool action przed związaniem bieżącej wiadomości z turą runtime, co pozwalało ominąć accepted-visible-turn lineage i w efekcie pokazać wypowiedź bez kanonicznego `MessageEnvelope`;
2. VS Code/Pylance lokalnie raportował masową serię `reportCallIssue` dla `JaznConfig` (`No parameter named "root"` i analogiczne komunikaty dla istniejących pól) oraz `reportArgumentType` dla `dataclasses.replace`, podczas gdy `JaznConfig` pozostaje standardową `@dataclass(slots=True)` z tymi polami.

## Ustalenia

Lista dostarczona z VS Code zawierała 262 diagnostyki: 256 `reportCallIssue` i 6 `reportArgumentType`. 215 komunikatów dotyczyło samego `root`; pozostałe `No parameter named ...` wskazywały między innymi istniejące pola `allow_network`, `network_time_first`, `rest_*`, `model_adapter`, `local_model_name`, `llm_route_mode` i `allow_paid_openai_api`. Sześć błędów `dataclasses.replace` twierdziło, że `JaznConfig` nie posiada `__dataclass_fields__`.

Bieżący `latka_jazn/config.py` definiuje `JaznConfig` bez własnego `__init__`, przez standardowe `@dataclass(slots=True)`, a wszystkie wskazane pola są jawnie anotowanymi polami klasy. Zgodnie z dokumentacją Pythona `@dataclass` generuje `__init__`, a `dataclasses.replace()` działa na instancjach dataclass i tworzy nową instancję przez ten konstruktor. Nie ma więc podstaw do dodawania ręcznego, wielusetparametrowego `__init__`, usuwania `slots=True` ani kasowania prawidłowych wywołań tylko po to, by uciszyć edytor.

Równolegle wykryto lukę w CI: `pyrightconfig.json` obejmuje aktywne `latka_jazn`, `tests`, `tools`, `CHATGPT_BOOTSTRAP.py`, `main.py` i `run.py`, ale główny release workflow wykonywał Pyright na kodzie produkcyjnym i kilku ręcznie wybranych testach. Osobny workflow pełnego drzewa istniał, lecz był przypięty do historycznego brancha z 2026-09-04, więc nie chronił nowych `fix/**` ani pull requestów do `master`.

## Naprawa

- `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` pozostaje cienkim loaderem, ale teraz jednoznacznie wymaga związania zwykłej wiadomości z bieżącą turą runtime **przed** zwykłą odpowiedzią lub host-tool action. Web/GitHub/image/file są evidence tej samej tury, nie alternatywną ścieżką odpowiedzi. Widoczny tekst nadal wymaga `action=display_exact`, zaakceptowanego `final_visible_text` i poprawnego `MessageEnvelope`; host nie dopisuje nagłówka ręcznie.
- `.vscode/settings.json` wersjonuje wyłącznie ustawienia potrzebne do parity diagnostycznego: `python.analysis.diagnosticsSource = "Pylance + Pyright"` oraz `python.analysis.pyrightVersion = "1.1.411"`, czyli tę samą wersję Pyright, którą repo już przypina w CI. Pozostały lokalny stan VS Code nadal jest ignorowany.
- `.github/workflows/pyright-active-tree-audit.yml` staje się aktywnym gate'em dla `master`, `fix/**`, `hotfix/**`, `update/**`, `upgrade/**`, `tools/upgrade-*` oraz PR do `master`. Uruchamia dokładnie `pyright --project pyrightconfig.json`, więc analizuje cały aktywny zakres zapisany w repo, a nie wybrane pliki.
- nowy test regresyjny konstruuje `JaznConfig` z parametrami występującymi w zgłoszonych diagnostykach i używa `dataclasses.replace`, a także weryfikuje loader, ustawienia Pylance/Pyright oraz aktywny pełnodrzewowy gate CI.

## Dlaczego nie zmieniono `JaznConfig`

Zmiana poprawnego kontraktu runtime w celu dopasowania go do jednego błędnego widoku edytora byłaby ryzykowna. Standardowa dataclass jest tutaj właściwym źródłem konstruktorów i pól. Naprawa zamiast tego wyrównuje silnik diagnostyczny VS Code z kanonicznym Pyright CI oraz dodaje pełny gate, który ujawni każdy rzeczywisty błąd typowania w całym aktywnym drzewie.

## Źródła

- Python 3.12 — `dataclasses`: https://docs.python.org/3.12/library/dataclasses.html
- Microsoft Pylance — Settings and Customization (`diagnosticsSource`, `pyrightVersion`): https://github.com/microsoft/pylance-release/blob/main/README.md
- Microsoft Pylance — Using Pylance with Pyright: https://github.com/microsoft/pylance-release/blob/main/USING_WITH_PYRIGHT.md
- Microsoft Pylance — CI type checking / parity editor–CI: https://github.com/microsoft/pylance-release/blob/main/docs/howto/ci-type-checking.md
- Pyright — configuration and project-based analysis: https://microsoft.github.io/pyright/

## Kryteria akceptacji

Branch nie jest release candidate dopóki pełny `pyright --project pyrightconfig.json`, deterministyczny pytest, compileall, metadata sync i wymagane workflow repozytorium nie przejdą na rzeczywistym headzie brancha. Diagnostyki VS Code należy odświeżyć po pobraniu brancha / scaleniu i ponownym załadowaniu okna edytora, aby Pylance zastosował wersjonowane ustawienia workspace.
