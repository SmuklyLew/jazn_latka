# Jaźń v16.3.25.5.60 — post-fix CI evidence

**Status:** `CI_RERUN_REQUESTED`
**Data:** 2026-09-10
**Branch:** `upgrade/v16.3.25.5.60-main-entrypoint-chatgpt-live-convergence`

Ten plik dokumentuje jawne ponowne uruchomienie pełnych bram CI po poprawieniu dwóch aktywnych kontraktów hosta ChatGPT wykrytych przez deterministic pytest.

Poprawka zachowuje nową architekturę v60:
- `run.py` pozostaje cienkim starterem;
- `main.py` pozostaje kanonicznym wykonawczym wejściem i centralnym control plane;
- każda bieżąca wiadomość jest przekazywana verbatim przez ten sam otwarty persistent ChatGPT bridge;
- nie przywrócono per-message CLI;
- nie osłabiono ani nie usunięto testów, które wykryły rozjazd dokumentacji.

Poprzedni pełny przebieg release-hardening miał wszystkie bramy kodowe, Pyright, compileall, audyty, Windows tests, dependency matrix oraz persistent-runtime E2E zielone; jedyną przyczyną fail były dwa literalne wymagania w `tests/test_runtime_owned_agent_boundaries.py`. Ten commit ma wymusić pełną walidację po ich naprawieniu.

Nie należy traktować tego dokumentu jako deklaracji `CI_GREEN` ani `MERGE_READY`; takie stany wymagają wyniku GitHub Actions po tym commicie.
