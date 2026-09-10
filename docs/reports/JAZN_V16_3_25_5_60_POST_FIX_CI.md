# Jaźń v16.3.25.5.60 — post-fix CI evidence

**Status:** `CI_RERUN_REQUESTED`
**Data:** 2026-09-10
**Branch:** `upgrade/v16.3.25.5.60-main-entrypoint-chatgpt-live-convergence`

Ten plik dokumentuje jawne ponowne uruchomienie pełnych bram CI po poprawieniu aktywnych kontraktów hosta ChatGPT wykrytych przez deterministic pytest.

Poprawka zachowuje nową architekturę v60:
- `run.py` pozostaje cienkim starterem;
- `main.py` pozostaje kanonicznym wykonawczym wejściem i centralnym control plane;
- każda bieżąca wiadomość jest przekazywana verbatim przez ten sam otwarty persistent ChatGPT bridge;
- host ma jawny zakaz parafrazowania wiadomości przed przekazaniem jej do runtime;
- nie przywrócono per-message CLI;
- nie osłabiono ani nie usunięto testów, które wykryły rozjazd dokumentacji.

Pierwszy pełny przebieg wykrył dwa brakujące literalne kontrakty hosta. Kolejny przebieg po ich poprawieniu osiągnął `1553 passed, 2 skipped, 1 failed`; jedynym pozostałym wymaganiem było jawne `Nie parafrazuj wiadomości przed przekazaniem`. Zostało ono dodane do `AGENTS.chatgpt.md` jako zgodne z istniejącym kontraktem verbatim. Ten commit wymusza pełną walidację końcową po tej poprawce.

Nie należy traktować tego dokumentu jako deklaracji `CI_GREEN` ani `MERGE_READY`; takie stany wymagają wyniku GitHub Actions po tym commicie.
