# Dokumentacja Jaźni — mapa i źródła prawdy

Dokumentacja jest porządkowana według **właściciela, aktualności i poziomu dowodu**, a nie według przypadkowej historii nazw plików.

## Zacznij tutaj

1. [`../AGENTS.md`](../AGENTS.md) — router odpowiedzialności agentów/hostów;
2. [`project/CURRENT_STATE.md`](project/CURRENT_STATE.md) — bieżący snapshot mastera, aktywnych branchy i kolejności pracy;
3. [`plans/16.6.0-final-convergence/ROADMAP.md`](plans/16.6.0-final-convergence/ROADMAP.md) — kanoniczna roadmapa programu v16;
4. [`project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`](project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md) — przekrojowy kontrakt pojęć i granic naukowych;
5. [`plans/17.0.0-measured-architecture-consolidation/PLAN.md`](plans/17.0.0-measured-architecture-consolidation/PLAN.md) — warunkowy plan v17 uruchamiany dopiero po evidence z v16.6.

## 1. Project-wide — `docs/project/`

Bieżące kontrakty, audyty i oceny wspólne dla wielu release'ów:

- `CURRENT_STATE.md` — aktualny snapshot techniczny i branch ownership;
- `PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md` — kanoniczne definicje Jaźni, ciągłości, pamięci, affect i granic epistemicznych;
- `REPOSITORY_CONVERGENCE_AUDIT_2026-09-01.md` — audyt master/branch/docs po zmianach loadera i Pack Generatora;
- `RELEASE_TIMELINE.md` — indeks release'ów, decyzji i archiwalnych dowodów;
- `system-evaluation/` — przekrojowa ocena v16.6→v17+ oraz datowane research addenda.

Datowany audyt pozostaje snapshotem swojej epoki. Nowy stan dopisuje się jako nowy dokument lub jawny current-state overlay zamiast przepisywać historyczne ustalenia.

## 2. Plan-owned — `docs/plans/`

Zawiera aktywne i planowane roadmapy/plany wykonawcze. Każdy plan powinien mieć właściciela treści i `STATUS.md`.

Obecnie nadrzędne:

- `16.3.25.4-memory-rebuild-v4/` — aktywna równoległa implementacja Memory Rebuild v4; jej branch roboczy może mieć nowszy `PLAN/STATUS` niż master do chwili merge;
- `16.3.26-attachment-ingress/` — kolejny release po bezpiecznym domknięciu/synchronizacji Memory Rebuild;
- `16.4-to-16.6-cognitive-hardening/` — przekrojowe kryteria evidence;
- `16.6.0-final-convergence/` — główna roadmapa kończąca program v16;
- `17.0.0-measured-architecture-consolidation/` — future/conditional; bez implementacji przed finalnym v16.6 evidence.

Pliki w `docs/plans/` o dawnych nazwach mogą być krótkimi compatibility pointerami prowadzącymi do kanonicznej lokalizacji. Pointer nie jest drugim źródłem prawdy.

## 3. Domain docs

Żywa dokumentacja techniczna:

- `docs/memory/` — recovery, Memory Rebuild, recall, source fidelity i pamięć;
- `docs/runtime/` — host/runtime/finalization/workspace i loader projektu ChatGPT;
- `docs/nlp/` — polskie zasoby językowe i kontrakty NLP;
- `docs/packaging/` — pakowanie, sidecary i attach;
- `docs/tools/` — aktywne kontrakty operatorskie;
- `docs/templates/` — wersjonowane szablony acceptance/evidence.

Stabilnych ścieżek operatorskich nie przenosi się tylko dla estetyki, jeżeli są częścią testowanego kontraktu.

## 4. Historical — `docs/archive/`

Archiwum przechowuje zakończone lub zastąpione:

- plany i roadmapy;
- raporty release/implementacji/research;
- review;
- patche;
- historyczne dokumenty hosta i narzędzi.

**Nie aktualizuj historycznego snapshotu tak, aby wyglądał jak dokument bieżący.** Stare SHA, ścieżki, wersje, niezielone wyniki i odrzucone eksperymenty są częścią wartości archiwum.

Jeżeli aktywny dokument chce odwołać się do raportu po reorganizacji, powinien wskazywać `docs/archive/...`, a nie nieistniejące dawne `docs/reports/...`.

## 5. Zasada bieżącej prawdy

Dla stwierdzeń typu `active`, `working`, `verified`, `accepted`, `merged` kolejność dowodu jest następująca:

```text
aktualne AGENTS*
-> aktualny kod / testy / machine-readable evidence
-> CURRENT_STATE + aktywny PLAN/STATUS
-> przekrojowe docs/project
-> historyczne docs/archive
```

Lokalizacja pliku, nazwa brancha, zielony dawny raport albo licznik `ahead` nie są samodzielnym dowodem, że branch jest nowszym systemem niż master.

## 6. Documentation convergence / gardening

Przy każdej większej konwergencji sprawdzaj co najmniej:

- martwe linki i dawne lokalizacje `docs/reports/`;
- stale current-version labels w dokumentach aktywnych;
- czy dokument nie wskazuje superseded branchu jako bieżącego;
- czy aktywny branch ma jawnego właściciela scope;
- czy current docs nie kopiują runbooków z `AGENTS*`;
- czy archiwa pozostały niezmienionymi snapshotami;
- czy nowe capability mają evidence i acceptance gate, a nie tylko opis.

Pełny release history/change-log jest indeksowany w [`project/RELEASE_TIMELINE.md`](project/RELEASE_TIMELINE.md).
