# Jaźń Studio Pamięci — checkpoint przerwy 2026-09-19

## STAN

PAUSED na wyraźną prośbę użytkownika. Nie rozpoczynać nowych napraw ani długich testów przed wznowieniem. To odzyskiwalny checkpoint, nie DONE ani release candidate.

Repozytorium SmuklyLew/jazn_latka; worktree `D:\.AI\jazn_branchs\jazn-studio-pamieci`. Wersja `16.3.25.5.80.2-jazn-studio-pamieci-native-conflict-identity`. Po świeżym fetch master i merge-base: `affabf5618934bd8efb39b0b1d074f7529116643`. HEAD kodu: `397fdcb14c6cb10c9e9b0785351eac84c5a765b8`; 25 ahead / 0 behind master; 1 ahead / 0 behind zdalnego brancha roboczego. Początkowy git status: tylko zmodyfikowane PACKAGE_INTEGRITY_MANIFEST.json i SOURCE_PROVENANCE.json, wygenerowane kanonicznie.

Polecenie synchronizacji już uruchomione przed przerwą zakończyło się: write 0, check 0, synchronized=true, manifest_matches=true, provenance_matches=true. Sprawdzenie procesów nie wykazało działającego lokalnego pytest ani release_metadata_sync. Nie uruchomiono nowych testów w ramach tej przerwy.

## WYKONANE

Od checkpointu `0d7440719d979f6b759a4ca6b4ee36bc9aa6db09`:

- 0d744071 zawiera właściwą implementację BatchPlan i oddzielną semantykę incremental; nie odtwarzać jej od początku. 19794d32 synchronizuje metadane .76.
- 037adcdd: konwergencja z masterem affabf56, zachowane 152 zmienione ścieżki mastera poza czterema plikami governance. Konflikty version/catalog/metadane rozstrzygnięto z zachowaniem współczesnych kontraktów. Nie scalano osobno historycznego .74.1.001. 052ad40e: kanoniczne metadane .80.
- 241eb89b: Test04 przyjmuje jawny expected branch/ref przez request, CLI i PowerShell. Brak oczekiwania blokuje wykonanie; ref musi wskazywać dokładnie HEAD; oba podane warunki muszą być spełnione. Dirty-tree preflight zachowany. 46ad2c05: metadane .80.1.
- f27cc2cc: pełny append-only snapshot 312 testów z 052ad40e, tree 95f78f9fac6cf14e2c2f805e85ce660061fd021e. Poprawia zgodność archiwum bez zmiany istniejących snapshotów lub testu governance.
- f7d9784d i 584306bb: poprzedni raport przerwy i jego metadane.
- 7fb7921c5f64ffeaa72f59c478e97dff0abc0591: publiczny syntetyczny native-conflict RED zapisany i wypchnięty przed poprawką; oba przypadki FAIL. Oczekiwania testu pozostały niezmienione.
- 95899e34: wyłącznie metadane bota, sprawdzone i włączone przez fast-forward.
- 397fdcb14c6cb10c9e9b0785351eac84c5a765b8: native conflict uuid5 wyprowadzane z SHA źródła, incoming raw tree i pełnego ConversationPlan; usunięta zależność source_member od absolutnej lokalnej ścieżki. Nowa wolna wersja .80.2 i zsynchronizowany katalog Test Studio. Raport szczegółowy: JAZN_STUDIO_PAMIECI_NATIVE_IDENTITY_CHECKPOINT.md.

Batch przygotowuje cały plan przed zapisem, używa stabilnych danych semantycznych i jawnego tie-breakera z provenance. Incremental pozostaje świadomie późniejszym importem mogącym tworzyć kolejną rewizję. Nie zmieniono walidatora Test03, porównania normal/reverse, snapshotu semantycznego, benchmarku ani automatic_l2=False / automatic_l3=False / automatic_activation=False. Nie aktywowano runtime i nie migrowano historii istniejących baz wstecz.

## TESTY

Wyniki należą do wskazanych etapów; nie są zbiorczym PASS końcowego drzewa.

| Kontrola | Wynik |
|---|---|
| Pierwotny syntetyczny batch RED przed 0d744071 | 2 FAIL, 1 PASS |
| Ten sam test po naprawie .76 | 3 PASS |
| Pakiet pamięci .76 / dodatkowe kontrakty batch | 48 PASS / 4 PASS |
| Pyright trzech plików silnika .76 | PASS, 0 errors, 0 warnings |
| Po konwergencji .80: pamięć, Studio, ingress, pre-response, executor | 48 PASS, 6.49 s |
| Test04 i kontrakt repozytorium .80.1 | 30 PASS, 5.99 s |
| Pełny Pyright .80.1 w pierwotnym środowisku | FAIL: 9 brakujących importów mcp-http, 1 warning |
| Pełny Pyright .80.1 w izolowanym venv z zależnościami mastera | PASS: 0 errors, 1 warning, exit 0 |
| compileall .80.1: latka_jazn/tests/tools/main.py/run.py, bez archive | PASS, exit 0 |
| Ostatni pełny aktywny pytest .80.1 | FAIL: 1761 PASS, 6 SKIPPED, 1 FAIL, 1 warning; 471.57 s |
| Niezmieniona bramka governance po f27cc2cc | 5 PASS, 0.76 s |
| Kontrole wznowienia 584306bb: governance, archiwum, Studio, Test04, batch, manifest, FTS | 41 PASS, 13.18 s |
| Nowy publiczny native-conflict RED | 2 FAIL, 1.46 s |
| Po samej stabilizacji conflict_id | 1 FAIL, 11 PASS, 4.57 s — nadal zależność od ścieżki |
| Po obu poprawkach .80.2 | 41 PASS, 13.59 s |
| Po doprecyzowaniu ON CONFLICT(conflict_id) DO NOTHING | 5 PASS, 1.74 s |
| py_compile zmienionego store, adaptera i nowego testu | PASS, exit 0 |
| Pyright tych trzech plików .80.2 | PASS, 0 errors, 0 warnings |
| Kanoniczne metadane dla 397fdcb1: write i niezależny check | PASS, exit 0 / 0 |
| Pełny pytest, pełny Pyright i compileall na .80.2 | NOT RUN — przerwa użytkownika |
| Prywatny chain nowej wersji Test00–Final | NOT RUN |

Pełny pytest nie jest obecnie uruchomiony. Jego ostatni FAIL to test_snapshot_manifest_is_byte_exact: KeyError snapshot_source w początkowym pojedynczym manifeście. Przyczynę poprawiono append-only pełnym snapshotem, a test pozostał niezmieniony. Ostrzeżenie Pyright pochodzi z mastera: chatgpt_host_pre_response_gate/_core.py:324, reportUnsupportedDunderAll. Ostrzeżenie pytest dotyczy celowego duplicate ZIP name.

CI 584306bb miało SUCCESS dla Stable test contracts, release-hardening, pyright-active-tree-audit, memory-rebuild-v24-windows, persistent-runtime-e2e, package-distribution-cleanroom, javascript-node24-contract i dependency-review. Powershell-terminal-regressions run 35449258568 ostatecznie CANCELLED. Nie oznacza to pełnego zielonego CI. CI finalnego checkpointu musi zostać sprawdzone po wznowieniu, bez przenoszenia wyników ze starego HEAD.

Logi pozostają poza Git w `D:\.AI\codex_tasks\jazn-studio-pamieci`: pytest-v80-1-full.log, pytest-v80-convergence.log, pytest-test04-ref-contract.log, pyright-v80-1-*.log, compileall-v80-1.log, pytest-resume-584306bb-targeted.log, pytest-native-conflict-{red,green,identity-green}.log, metadata-native-identity-{write,check}.json. Starsze wyniki i dalsze ścieżki: JAZN_STUDIO_PAMIECI_RESUME_CHECKPOINT.md; raport pozostaje historyczny.

## WYKRYTE PROBLEMY

1. Losowe uuid4 konfliktów i absolutny source_member powodowały różnice pełnego snapshotu. Obie przyczyny naprawiono; nowe testy syntetyczne są zielone, ale nie zastępują prywatnego Test03.
2. Nadal brak rewalidacji hasha źródła pomiędzy przygotowaniem BatchPlan a natywną projekcją. Nie rozpoczęto poprawki ani testu RED tej luki. Przy wznowieniu ustalić kontrakt odmowy i potwierdzić RED przed naprawą; zachować prepare-once i jednokrotne konsumowanie iteratora.
3. Do dalszego sprawdzenia: ZIP/katalog, powtórzenia źródeł, lokalizatory, duże batche i spójność natywnego zapisu przy zmianie źródła.
4. Stare bazy nie zostały przepisane; kanonizacja dawnych tożsamości źródeł wymaga osobnej świadomej analizy przy aktualizacji.
5. Pełna walidacja .80.2 i stabilne CI nie są zakończone. Nie ogłaszać DONE.

## POZOSTAŁO

- Zweryfikować świeże HEAD/master/CI po fetch; konwergencja z affabf56 jest wykonana. Nie powtarzać historycznych merge/cherry-pick ani napraw Test04/batch od początku.
- Dodać RED zmiany źródła między przygotowaniem a native projection; naprawić właściciela i uzyskać GREEN bez zmiany oczekiwań. Przed kolejną zmianą semantyki sprawdzić wolną wersję.
- Dokończyć pozostałe scenariusze batch i incremental; pełny pytest, Pyright, compileall, governance/release oraz Windows/Linux CI na końcowym drzewie.
- Test04 branch/ref jest naprawiony; prywatny etap Test04 nadal NOT RUN.
- Dopiero po stabilnych publicznych bramkach uruchomić NOWY spójny chain Test00 → Test01 → Test02 → Test03 PASS → frozen benchmark 13 → Test04 → Final. Nie używać skryptu wznowienia przypiętego do .71 ani starych PASS jako nowej akceptacji.
- Zamrożony recall-source-acceptance.json SHA256: 21753c142113c7c02600c75de0859b17d03b572656d7cd4d2bf6e76a1098fc8e. Nie zmieniać przypadków/progów. Źródła prywatne pozostają poza Git.
- Zaktualizować końcowy raport, metadane kanonicznie, commit/push i zdalne potwierdzenie. Brak prywatnej akceptacji musi zostać oznaczony precyzyjnym handoff, nie PASS.

## NASTĘPNY KROK

Dopiero po jawnej kontynuacji: przeczytać AGENTS.md, AGENTS.codex.md i ten raport; sprawdzić status/branch/HEAD/fetch/master/merge-base/ahead-behind oraz CI dla rzeczywistego HEAD. Użyć izolowanego `D:\.AI\codex_tasks\jazn-studio-pamieci\tooling\validation-v80-1\Scripts\python.exe` (także jako --pythonpath dla Pyright). Najbliższe zadanie merytoryczne: minimalny syntetyczny RED mutacji źródła pomiędzy przygotowaniem batcha a projekcją. Nie ma lokalnego procesu pytest do odzyskania.

## BRANCH/HEAD

Branch: `fix/v16.3.25.5.75-jazn-studio-pamieci-master73-convergence-next-step`.
HEAD kodu przed zapisem raportu: `397fdcb14c6cb10c9e9b0785351eac84c5a765b8`.
Master/base: `affabf5618934bd8efb39b0b1d074f7529116643`.
Status przed raportem: wyłącznie dwa wygenerowane pliki metadanych; żadnych niezacommitowanych zmian kodu.
Ten raport i metadane będą zapisane w checkpointach; końcowy SHA zostanie potwierdzony przez git ls-remote i podany w odpowiedzi oraz lokalnym RESUME_STATE.md. SHA commita zawierającego raport nie może być wpisany do jego własnej treści bez zmiany tożsamości. Po pushu wymagane puste git status; ewentualne pozostałości trzeba jawnie wymienić. Prywatne źródła, SQLite, logi i artefakty testowe nie wchodzą do commita.
