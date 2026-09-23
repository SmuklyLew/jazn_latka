# Jaźń Studio Pamięci — checkpoint przerwy 2026-09-18

## STAN

PAUSED na wyraźną prośbę użytkownika przy limicie poniżej 10%. Nie rozpoczynać następnego etapu przed wznowieniem. To checkpoint odzyskiwalnej pracy, nie DONE ani release candidate.

Repozytorium: SmuklyLew/jazn_latka. Worktree: `D:\.AI\jazn_branchs\jazn-studio-pamieci`. Wersja: `16.3.25.5.80.1-jazn-studio-pamieci-test04-ref-contract`. Master sprawdzony również przez git ls-remote: `affabf5618934bd8efb39b0b1d074f7529116643`. Branch zawiera ten master; merge-base jest równy masterowi. Przed zapisaniem niniejszego raportu: 20 ahead / 0 behind master, git status --porcelain=v1 pusty.

Wszystkie uruchomione w tej turze polecenia zakończyły się. Pełny pytest jest zakończony; nie ma procesu do wznawiania ani oczekiwania. Nie uruchomiono nowego prywatnego chaina Test00–Final.

## WYKONANE

Od checkpointu implementacji `0d7440719d979f6b759a4ca6b4ee36bc9aa6db09`:

- `19794d32abd077562870c66a05c3dbb4ce1f0e2a`: kanoniczne metadane .76; push zweryfikowany. BatchPlan i rozdział batch/incremental pochodzą z 0d744071, nie odtwarzać ich od początku.
- Po wznowieniu zweryfikowano obecność obu commitów na aktywnym branchu i czysty worktree. Nowy master był o 246 commitów dalej od bazy 9d38a294; Studio miało 15 własnych commitów.
- `037adcdd`: zwykły merge aktualnego mastera affabf56. Zachowano dokładnie 152 zmienione ścieżki mastera poza czterema plikami governance. Konflikty: version.py, test_contracts.json, PACKAGE_INTEGRITY_MANIFEST.json, SOURCE_PROVENANCE.json. Nie cherry-pickowano ani nie mergowano osobno historycznego host-handoff brancha. Master .79.3 wymagał nowego wolnego numeru .80; historię .75/.76 zachowano.
- `052ad40ebf53587a789c1d897570c64d18a80102`: wygenerowane i niezależnie sprawdzone metadane .80; push zweryfikowany.
- `241eb89b`: naprawa Test04 w ProtocolRequest, Python CLI i PowerShell. Usunięto produkcyjny EXPECTED_BRANCH wskazujący historyczny branch. Oczekiwany branch/ref przekazywany jest jawnie. Brak obu blokuje wykonanie. Podany ref musi rozwiązać się dokładnie do HEAD; oba oczekiwania oznaczają obowiązek spełnienia obu. Dirty-tree gate pozostał niezależny. Dodano testy realnych syntetycznych repozytoriów Git i odmowy PowerShell, zaktualizowano dokumentację oraz kanoniczny katalog testów. Wersja .80.1 sprawdzona jako wolna.
- `46ad2c05bff9b86e110124637e7b5331909a69ad`: kanoniczne metadane Test04; commit wypchnięty i zdalnie potwierdzony.
- `f27cc2cc3a22c6e362fd3318332a6a137c57b0e4`: append-only uzupełnienie archiwum do kanonicznego pełnego snapshotu 312 plików aktywnych testów z pre-change commita 052ad40e. Użyto oryginalnych blobów Git, tree `95f78f9fac6cf14e2c2f805e85ce660061fd021e`. Wcześniejszy pojedynczy snapshot i jego manifest nie zostały zmienione. To było ostatnie polecenie wykonywane w chwili prośby o przerwę.

Nie zmieniano prywatnych źródeł, nie promowano L2/L3, nie aktywowano runtime ani nie osłabiano walidatora/snapshotu Test03.

## TESTY

Wyniki historyczne i bieżące należy rozróżniać:

| Zakres | Wynik i granica dowodu |
|---|---|
| Syntetyczny RED przed batch fix | 2 FAIL, 1 PASS; utrwalony przed 0d744071 |
| Ten sam niezmieniony test po batch fix | 3 PASS na .76 |
| Ukierunkowany pakiet pamięci .76 | 48 PASS |
| Nowe kontrakty batcha .76 | 4 PASS, w tym sześć permutacji trzech źródeł i jawny incremental |
| Pyright trzech plików silnika .76 | PASS, 0 errors, 0 warnings |
| Po ponownej konwergencji .80: batch, Studio, ingress, pre-response, executor epoch | 48 PASS w 6.49 s |
| Istniejący Test04 + nowy kontrakt repozytorium | 30 PASS w 5.99 s |
| Pełny Pyright w pierwotnym Pythonie | FAIL: 9 brakujących importów opcjonalnego mcp-http, 1 warning |
| Pełny Pyright w izolowanym środowisku z zależnościami mastera | PASS: 0 errors, 1 warning, exit 0 |
| compileall: latka_jazn, tests, tools, main.py, run.py; archive wyłączone | PASS, exit 0 |
| Pełny aktywny pytest .80.1, bez live_model/live_mcp | **FAIL: 1761 passed, 6 skipped, 1 failed, 1 warning; 471.57 s; exit 1** |
| Niezmieniona bramka governance po f27cc2cc | **5 PASS w 0.76 s** |
| Pełny pytest po f27cc2cc | NOT RUN — przerwa użytkownika; nie przedstawiać wcześniejszego pełnego FAIL jako PASS |
| Syntetyczna próba native ChatGPT + journal, normal/reverse | **FAIL semantycznej równości**, oba importy ok; różni się wyłącznie import_conflicts |
| Metadane .76, .80 i .80.1 przed końcowym raportem/uzupełnieniem archiwum | Każde kanoniczne --write i niezależne --check: PASS |
| Pełne CI / końcowe release gates / prywatna akceptacja nowego silnika | NOT RUN / niepotwierdzone; brak podstaw do DONE |

Jedyny pełny pytest FAIL: `tests/test_test_suite_governance.py::test_snapshot_manifest_is_byte_exact`, KeyError `snapshot_source` w dodanym pojedynczym manifeście archiwum. Przyczynę uzupełniono pełnym kanonicznym snapshotem, a nie zmianą testu. Ostrzeżenie pytest dotyczy celowego duplicate ZIP name w teście tamper. Ostrzeżenie Pyright pochodzi z mastera: `chatgpt_host_pre_response_gate/_core.py:324`, reportUnsupportedDunderAll.

Logi i środowisko pozostają lokalnie poza repo, w `D:\.AI\codex_tasks\jazn-studio-pamieci`:

- pytest-v80-convergence.log; pytest-test04-ref-contract.log; pytest-v80-1-full.log;
- pyright-v80-1-full.log (brak deps), pyright-v80-1-environment-full.log (PASS), compileall-v80-1.log;
- native-batch-v80-1-probe.json;
- metadata-v80-convergence-{write,check}.json; metadata-v80-1-test04-{write,check}.json;
- tooling/validation-v80-1/Scripts/python.exe: izolowane venv z system-site-packages; doinstalowane wyłącznie tam deklarowane mcp==2.2.0, pydantic>=2.7, starlette>=0.48.0;
- dokładne wersje: tooling/validation-v80-1-installed.txt, przebieg instalacji: tooling/validation-v80-1-dependencies.log.

## WYKRYTE PROBLEMY

1. **Test03 nadal ma rzeczywistą lukę w natywnej projekcji.** Prywatna, ale całkowicie syntetyczna próba dwóch eksportów tej samej rozmowy z odmienną treścią oraz dwóch wariantów dziennika dała poprawne importy i różne snapshoty wyłącznie w tabeli import_conflicts. `ChatExportArchiveStore._record_conflict()` w `latka_jazn/tools/chat_export_store.py` używa `uuid.uuid4()` dla conflict_id. Kolumna słusznie pozostaje w porównaniu semantycznym. Nie wolno usuwać jej ze snapshotu ani rozluźniać Test03. Publiczny test RED tego dodatkowego przypadku NIE ZOSTAŁ JESZCZE DODANY; naprawa właściciela NIE ZOSTAŁA ROZPOCZĘTA.
2. Przy projektowaniu stabilnego conflict_id użyć tożsamości źródła (`import_sources.sha256`), rozmowy, incoming raw/semantic tree i semantycznego planu konfliktu. `ConversationPlan` udostępnia incoming/active_semantic_tree_sha256 i to_dict(). `parent_conflicts()` zwraca node IDs, nie conflict IDs. Zachować idempotencję, foreign keys, resolution_status/reason i incremental semantics; nie używać losowego import_id do rankingu/tożsamości.
3. Początkowy manifest pojedynczego snapshotu Test04 był niezgodny z formatem branch snapshot. Uzupełnienie f27cc2cc daje pełny niezmienny snapshot i zaliczoną bramkę; pełny pakiet nie został po nim powtórzony.
4. Nadal wymagają przeglądu: zmiana źródła między przygotowaniem batcha a native projection, trwałość oryginalnych lokalizatorów (obecnie source_locators w raporcie), przypadki przenoszenia i powtarzania źródeł ChatGPT/journal, wydajność dużych batchy. Przygotowanie adaptera raz i jednokrotne konsumowanie iteratora muszą pozostać zachowane.
5. Nie traktować 3 PASS regresji analizy utworów jako dowodu pełnego Test03 dla rozmów z konfliktami.

## POZOSTAŁO

- Dodać minimalny publiczny native-conflict RED (normal/reverse, najlepiej też zmiana nazw/położenia); zachować jego asercje po pierwszym błędzie. Następnie naprawić tożsamość konfliktu u właściciela i uzyskać GREEN, z osobnymi checkpointami.
- Zweryfikować pozostałe ścieżki batch/native i aktualizacji przyrostowej, bez uzależnienia od lokalnej ścieżki/kolejności.
- **Test04: kontrakt branch/ref jest naprawiony i testowany; prywatny etap Test04 NIE JEST wykonany.** Nie mylić naprawy operatora z akceptacją protokołu Studia.
- Po ostatecznej zmianie semantyki wykonać NOWY spójny prywatny chain Test00 → Test01 → Test02 → Test03 PASS → zamrożony benchmark 13 przypadków → Test04 → Final. Stare PASS/FAIL są tylko historyczne. Nie używać starego skryptu wznowienia powiązanego z .71.
- Benchmark `recall-source-acceptance.json` ponownie sprawdzony: SHA256 `21753c142113c7c02600c75de0859b17d03b572656d7cd4d2bf6e76a1098fc8e`; nie zmieniać przypadków/progów.
- Po zmianach ponowić odpowiednie testy, pełny aktywny pytest, Pyright, compileall i obowiązkowe governance/release/CI. Końcowe metadane tylko kanonicznym generatorem.
- Przed nową zmianą sprawdzić zajęte wersje/branche/tagi/master, bez przepisywania .75/.76/.80 historii.
- Master affabf56 jest zawarty. Przy wznowieniu wykonać fetch i ponowny audyt, ponieważ zdalny master może znów się przesunąć. Nie odtwarzać już wykonanych merge'ów.

## NASTĘPNY KROK

Po jawnej kontynuacji przeczytać ten raport, AGENTS.md, AGENTS.codex.md; sprawdzić git status/branch/HEAD/log i fetch origin --prune. Potwierdzić obecność 0d744071, 037adcdd, 241eb89b i f27cc2cc. Następnie jako pierwszą zmianę napisać publiczny test regresyjny native import_conflicts i potwierdzić RED, zanim zostanie zmieniony writer. Nie rozpoczynać prywatnego długiego rebuilda przed naprawą tej znanej przyczyny.

## BRANCH/HEAD

- Branch: `fix/v16.3.25.5.75-jazn-studio-pamieci-master73-convergence-next-step`.
- HEAD kodu i zakończonych kontroli bezpośrednio przed commitem tego raportu: `f27cc2cc3a22c6e362fd3318332a6a137c57b0e4`.
- Zdalny branch przed końcowym pushem: `46ad2c05bff9b86e110124637e7b5331909a69ad`.
- Git status przed zapisem tego raportu: czysty. Jedyną nową zmianą przy tworzeniu raportu jest ten plik; końcowe metadane mają być generowane, nie edytowane ręcznie.
- Commit zawierający ten raport oraz ewentualny kolejny commit kanonicznych metadanych są końcowym checkpointem. Jego SHA należy odczytać z git rev-parse HEAD i potwierdzić przez git ls-remote origin dla wskazanego brancha; finalny SHA nie może być wpisany do pliku wewnątrz tego samego commita bez zmiany jego tożsamości. Potwierdzone SHA i czystość po pushu zostaną podane w odpowiedzi oraz lokalnej notatce RESUME_STATE.md.
