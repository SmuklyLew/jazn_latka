# TPA 2.0 — checkpoint

## A. Tożsamość

- Repozytorium: SmuklyLew/jazn_latka.
- Branch: `latka_work/tpa-2-auto-acceptance-history`.
- Worktree: `D:\.AI\jazn_branchs\tpa-2-auto-acceptance-history`.
- Baza: `origin/master`, `55948d3813664923ae64c6e24f345369632a1b24` (fetch wykonany).
- HEAD: commit zawierający ten checkpoint; odczytaj `git rev-parse HEAD`.
  Nie wpisujemy samoodnoszącego się SHA do zawartości commita.
- Wersja etapu I: `16.3.25.5.116.0.34.94.6.43-tpa-durable-history`.
- Data: 2026-10-30 (Europe/Warsaw).

## B. Prace i mapa modułów

Etap I / P0: wdrożony stan zbiorczy wszystkich 22 scenariuszy, niezależne kanały
regresja/live/pełny odbiór, ostatnia próba i ostatni potwierdzony sukces,
aktualność SHA/wersji oraz weryfikacja JUnit i hashy dowodów operatora.
Historyczny PASS bez materiału nie jest wyświetlany jako potwierdzony sukces.
Późniejsze NOT_RUN nie przesłania starszej próby. Regresja nie promuje full_gate.

- `tpa_current_state.py`: nowa projekcja odczytowa, odbudowywana z raportów.
- `tpa_reports.py`: niezmienne, redagowane `revision-*.json`, flush/fsync przed
  zamianą `report.json`/`report.txt`; jawne odzyskanie z kompletnych rewizji
  zachowuje uszkodzone oryginały pod unikalnymi nazwami.
- `tpa_view.py`: domyślnie stan zbiorczy; osobny zakres historii run_id;
  7 kolumn; odzyskanie wybranego uszkodzonego raportu; nie zmienia lifecycle.
- Nowe testy: `test_tpa_2_current_state.py`, `test_tpa_2_history_qt.py`.
- `latka_jazn/version.py`: podniesienie wersji; metadane wyłącznie generatorem.
- Plan: `docs/plans/TPA_2_0_IMPLEMENTATION_PLAN.md`.

Przeczytano pełne AGENTS.md, AGENTS.codex.md, referencję operacyjną i politykę
struktury/deps oraz moduły reports/triage/guidance/view/catalog/engine/paths,
release_identity i local_acceptance. Nie trzeba ponownie badać całego repo.
Nie zmieniono istniejących testów ani historycznych snapshotów.
Rewizje są dziennikiem pojedynczego przebiegu; indeks nie jest źródłem prawdy.
Oryginalne ręczne wyniki v1 pozostają w istniejącym „Starsze wyniki” i nie są
promowane do automatycznych wyników v2. Nie wymyślono migracji nieznanych schematów.

## C. Walidacja

Interpreter testowy: `D:\.AI\codex_tasks\tpa-2-validation-venv\Scripts\python.exe`
(osobny venv z Python 3.14, system-site-packages, PySide6-Essentials 6.12.0).
Brak Qt w zastanych interpreterach; zainstalowano deklarowane opcjonalne Qt
wyłącznie do nowego venv. Nie instalowano nic do środowiska Jaźni.

- Pierwszy zestaw: **52 passed**, 33.84 s.
- Szerszy TPA przed poprawką layoutu: **113 passed, 2 failed, 1 skipped**.
  Dowiązanie Windows: ograniczenia procesu testowego. Retest z odpowiednimi
  uprawnieniami: PASS. Układ 860×580: poprawiono odstępy panelu, zachowując test.
- Retest układu i szerokości: **2 passed**, 1.41 s.
- Końcowy przebieg wszystkich TPA: **115 passed, 1 skipped**, 33.96 s.
  Komenda: wybrane przez `rg --files tests -g test_jazn_tpa*.py -g test_tpa_2*.py`
  aktywne testy (bez archive), `python -X utf8 -m pytest -q <pliki> --tb=short
  --basetemp=D:\.AI\codex_tasks\tpa-2-stage1-final-pytest
  --junitxml=D:\.AI\codex_tasks\tpa-2-stage1-final-junit.xml`.
- `py_compile` zmienionych modułów: PASS; `git diff --check`: PASS.
- Pełne pytest, doctor, package-smoke, Pyright, końcowe CI: jeszcze NOT RUN.
- Fizyczne Windows/DPI/EXE, rzeczywista Ollama i pełny odbiór operatorski:
  NOT RUN; testy Qt offscreen nie zastępują tych odbiorów.

## D. Pozostałe prace

1. P1: resolver origin/master (domyślnie), branch, PR, merge-result, lokalny
   SYSTEM i zweryfikowany ZIP. Powiązać SHA/wersję/integralność ze źródłem
   faktycznie wykonywanych testów. Detached worktree i osobne zasoby przebiegu.
2. P2: zależności preflight → regresja → daemon → dwie zaakceptowane tury →
   reconnect → resume tego samego nierozstrzygniętego request_id → własny restart.
   Oddzielne timeouty faz i jawne BLOCKED dla zależnych kroków.
3. P3: kreator kolejnych półautomatycznych odbiorów, trwały plan/resume,
   przyciski uruchom/odbiór/kontynuuj/checkpoint/historia. Zapis obserwacji
   ma nadal wymagać rzeczywistego wykonania i materiału z hashami.
4. Dalsze utwardzenie: kontrola aktualnego źródła w chwili zapisu obserwacji,
   ponowna walidacja 12 odbiorów zależnych studios-parity, wielkość historii
   i retencja (bez automatycznego usuwania), import znanych starszych schematów
   tylko na podstawie rzeczywistych fixture'ów, bez zgadywania formatu.
5. Etap V: szersza regresja z runbooka, idempotencja metadanych, Draft PR i
   potwierdzenie CI dla końcowego SHA. Nigdy merge bez osobnej zgody.

## E. Bezpieczeństwo i budżet

Główny `D:\.AI\jazn_latka_master` pozostał na master; kod edytowano wyłącznie
w osobnym worktree. Nie odczytywano prywatnych raportów/MEMORY ani baz.
Nie uruchamiano, nie zatrzymywano ani nie przejmowano produkcyjnego daemona.
Testy korzystają z fixture'ów i własnych procesów; nie wykonywano cleanup
cudzych zasobów. Pozostawiono testowy venv i raporty poza Git.
Nie wykonywano reset/rebase/force-push/merge. Wymagane uprawnienia Git i
testu dowiązań uzyskano przez mechanizm hosta, zgodnie z autoryzacją zadania.

Ostatni odczyt: 19% całej puli 300 minut, 57% tygodnia. Minimum 30% puli musi
pozostać niewykorzystane. Sprawdź aktualny licznik przed wznowieniem; historyczny
odczyt nie dowodzi stanu następnej sesji. Nie używano płatnych API ani agentów.

## F. Wznowienie

```powershell
Set-Location D:\.AI\jazn_branchs\tpa-2-auto-acceptance-history
git status --short --branch
git rev-parse HEAD
git ls-remote origin refs/heads/latka_work/tpa-2-auto-acceptance-history
git log -5 --oneline
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
```

Porównaj lokalne i zdalne SHA oraz PR/CI. Odczytaj AGENTS.md i AGENTS.codex.md,
ten checkpoint i plan. Następny krok: dokończ walidację/push etapu I, następnie
przeczytaj pełne `tpa_live.py` i kanoniczny kontrakt izolacji przed P1.
Powtarzaj tylko testy zależne od nowych zmian; końcowy gate musi dotyczyć
aktualnego HEAD. Ukończenie wymaga wszystkich warunków TPA 2.0 z planu,
rzeczywistych dowodów, branch/PR oraz jawnego rozdzielenia odbiorów manualnych.
Cały Goal pozostaje NIEUKOŃCZONY do spełnienia wszystkich wymagań.

## PROMPT_DO_KONTYNUACJI

Kontynuuj autonomicznie TPA 2.0 w SmuklyLew/jazn_latka, branch
latka_work/tpa-2-auto-acceptance-history, worktree
D:\.AI\jazn_branchs\tpa-2-auto-acceptance-history. Najpierw sprawdź licznik
wykorzystania 300-minutowej puli i tygodnia; nie przekraczaj 70% całej puli,
zostaw minimum 30%. Odczytaj AGENTS.md, AGENTS.codex.md, plan i checkpoint
docs/plans/TPA_2_0_*.md. Potwierdź HEAD, czystość, zdalny SHA, PR i CI.
Zachowaj wdrożoną trwałą historię i zbiorczy stan 22 scenariuszy. Implementuj
następne etapy w kolejności P1 izolowane źródło master/SHA, P2 plan zależności
i timeouty, P3 półautomatyczny kreator, następnie regresje i Draft PR do master.
Używaj kanonicznego run.py → main.py i Controller/ChatClient; nie dodawaj
lifecycle ani finalizatora. Nierozstrzygniętą turę wznawiaj z tym samym
request_id. Nie dotykaj prywatnej MEMORY, aktywnych markerów i obcego daemona.
PASS regresji nie jest pełnym odbiorem. Nie zmieniaj starych testów bez
append-only archiwizacji. Po każdym etapie testy, checkpoint, commit, push
i potwierdzenie SHA. Gdy budżet niewystarczający, pozostaw zweryfikowany etap
z wypchniętym checkpointem i dokładną listą braków. Nie deklaruj ukończenia
całości bez rzeczywistych dowodów. Nie wykonuj merge.
