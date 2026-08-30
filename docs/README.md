# Dokumentacja Jaźni — mapa i taksonomia

Dokumentacja jest porządkowana według właściciela i cyklu życia, a nie według przypadkowej historii nazewnictwa.

## 1. Plan-owned

`docs/plans/` zawiera wyłącznie bieżące plany/roadmapy wykonawcze. Każdy plan ma własny katalog oraz `STATUS.md`, który mówi czy plan jest `IN_PROGRESS`, `PLANNED`, `ACTIVE_ROADMAP` albo `CLOSED`.

## 2. Project-wide

`docs/project/` zawiera kontrakty, audyty i oceny obowiązujące przekrojowo w całym projekcie.

## 3. Domain docs

Żywa dokumentacja techniczna pozostaje w katalogach domenowych:

- `docs/memory/` — Memory Rebuild, recovery, recall, restore i prywatna walidacja;
- `docs/nlp/` — polskie zasoby językowe/reasoning;
- `docs/runtime/` — host/runtime/finalization/workspace;
- `docs/packaging/` — kontrakty pakowania;
- `docs/templates/` — wersjonowane szablony operatorskie.

Stabilne ścieżki runtime/packaging/templates nie są sztucznie zagnieżdżane pod dodatkowym `domains/`, aby nie łamać kontraktów operacyjnych.

## 4. Historical

`docs/archive/` zawiera zakończone lub zastąpione plany, stare roadmapy, raporty release/implementacji, review, patche oraz historyczne noty narzędziowe.

Historyczny dokument jest dowodem stanu z czasu jego powstania, ale nie jest bieżącym poleceniem wykonawczym.

## Zasada przenoszenia

- dokument należący do jednego release/planu -> folder tego planu;
- dokument definiujący cały projekt -> `project/`;
- aktualna instrukcja/kontrakt techniczny -> właściwa domena;
- zakończony raport/plan/patch/review -> `archive/`.

Nie używaj lokalizacji pliku jako jedynego dowodu, że capability działa. Obowiązują bieżące `AGENTS*`, kod, testy i truth/evidence contracts.
