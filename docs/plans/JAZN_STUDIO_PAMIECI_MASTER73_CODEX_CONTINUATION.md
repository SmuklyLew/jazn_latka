# Jaźń Studio Pamięci — master73 convergence / Codex continuation

## Status dokumentu

Ten plik jest checkpointem kontynuacyjnym dla brancha:

`fix/v16.3.25.5.75-jazn-studio-pamieci-master73-convergence`

Punkt bazowy został przypięty do aktualnego `master`:

`5c4db661268f4361f6792ac57e9c1884a126c08c`

Bazowa wersja runtime:

`16.3.25.5.73-secure-mcp-tunnel-runtime-bridge-convergence`

Źródłowy checkpoint Studia:

`fix/jazn-studio-pameci` @ `24a373a845fa983ad1149db1f9e76ecd76a989e7`

Merge-base obu linii:

`5842b4b24d2b073293865a6ec99a76e6be9c0fcb`

Nowa linia konwergencji:

`16.3.25.5.75-jazn-studio-pamieci-master73-convergence`

To nadal nie jest release candidate. Prywatny Test03 wykrył rzeczywisty problem
niedeterministyczności importu. Nie osłabiać Test03 i nie zmieniać zamrożonego
benchmarku w celu uzyskania PASS.

## Audyt 50 commitów master względem 9 commitów Studia

Od wspólnego merge-base `5842b4b2` do `master` znajduje się 50 commitów. Od
tego samego merge-base do checkpointu Studia znajduje się 9 commitów. Audyt
ścieżek wykazał tylko cztery bezpośrednio wspólne powierzchnie zmian:

1. `latka_jazn/version.py`;
2. `tools/jazn_tests_studio/test_contracts.json`;
3. `PACKAGE_INTEGRITY_MANIFEST.json`;
4. `SOURCE_PROVENANCE.json`.

Nie stwierdzono bezpośredniego przecięcia 50 commitów master z funkcjonalnymi
modułami Studia (`memory_studio.py`, `studio_audit.py`, `studio_links.py`,
`studio_repair.py`, źródłowym rozszerzeniem `music_analysis.py`, integracją
`entrypoint.py`, poprawką `run_manifest.py` ani testami Studia).

### Rozstrzygnięcie czterech wspólnych powierzchni

- `latka_jazn/version.py`: zachować cały współczesny kontrakt wersjonowania z
  `.73`, zmienić wyłącznie bieżącą tożsamość wydania na `.75`; nie przywracać
  starszego pliku `.71/.74` jako całości.
- `tools/jazn_tests_studio/test_contracts.json`: nie kopiować katalogu z `.74`.
  Zachować katalog z aktualnego master i pozwolić kanonicznemu
  `stable-test-contracts.yml` uruchomić `sync_contract_catalog.py --write` po
  dodaniu testów Studia.
- `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json`: nie edytować
  ręcznie i nie kopiować z diverged brancha. Kanoniczny `release-hardening`
  ma wygenerować je z końcowego drzewa.

W praktyce konflikt `dirty` PR #267 wynika z rozjechanej historii i powierzchni
release-governance, a nie z równoległej edycji głównych modułów Studia przez
Secure MCP / ChatGPT execution-route / Pack Generator.

## 50 commitów master po merge-base — zweryfikowana lista

Kolejność od najnowszego do najstarszego:

1. `5c4db661` — release: synchronize canonical metadata for 16.3.25.5.73-secure-mcp-tunnel-runtime-bridge-convergence
2. `6340102e` — Merge pull request #270 (PowerShell contract convergence)
3. `07712ed3` — metadata `.73`
4. `b48883fb` — fix: restore canonical thin-loader boundary phrases
5. `f6a9b6f7` — ci: validate synchronized v16.3.25.5.73 repair head
6. `3cddfdbc` — metadata `.73`
7. `d2ce12a0` — fix: classify local namespace packages in dependency audit
8. `a4ab1821` — metadata `.73`
9. `d2d57263` — test: align runtime bundle generator contract with 10.1.86.0.115
10. `6a84f3d4` — metadata `.73`
11. `d200cf09` — test: align memory transport generator contract with 10.1.86.0.115
12. `cdb2ce7b` — test: synchronize Test Studio contract catalog
13. `e3a02003` — test: align generator studio portability with 10.1.86.0.115
14. `65159458` — test: converge pack generator public API scope
15. `a6240f99` — metadata `.73`
16. `6e41534c` — test: align pack generator profiles with 10.1.86.0.115
17. `fccb49e2` — test: synchronize Test Studio contract catalog
18. `2be4f223` — test: align generator import isolation with 10.1.86.0.115
19. `761044e0` — test: converge pack generator public contract at 10.1.86.0.115
20. `1808f036` — test: align memory pack contract with generator 10.1.86.0.115
21. `2f877945` — metadata `.73`
22. `7b42ac70` — fix: restore thin ChatGPT loader contract
23. `39241ffc` — ci: validate synchronized Secure MCP release state
24. `832e4ce4` — metadata `.73`
25. `a7abba2a` — docs: record deterministic Test Studio governance sync
26. `a87f34d8` — metadata `.73`
27. `452fb54c` — test: synchronize Test Studio contract catalog
28. `5780a146` — ci: synchronize Test Studio contracts on update branches
29. `e3a98ba8` — metadata `.73`
30. `ef3e4679` — test: add deterministic Test Studio contract catalog sync
31. `cc9e7bf9` — metadata `.73`
32. `87f7e676` — docs: report Secure MCP Tunnel runtime bridge convergence
33. `a4028d0f` — docs: add Secure MCP Tunnel remote runtime runbook
34. `e9aaeacb` — metadata `.73`
35. `feaf2a63` — release: bump Jaźń to 16.3.25.5.73 Secure MCP bridge
36. `cd19a62e` — test: fix Secure MCP bootstrap argv assertion
37. `5c3d9b0c` — test: cover packaged Secure MCP tunnel target semantics
38. `06b9cc3e` — test: verify tunnel bootstrap binds only to trusted daemon
39. `5ab3789c` — test: cover Secure MCP Tunnel route truth boundaries
40. `7edfc1ed` — feat: discover Secure MCP Tunnel remote runtime route
41. `cb26111d` — feat: publish Secure MCP Tunnel package capability
42. `bcd25550` — feat: bind Secure MCP Tunnel to verified persistent runtime
43. `20c43456` — metadata `.72` convergence
44. `3ae171f3` — feat: add secure MCP tunnel transport contract
45. `cb9e9785` — metadata `.72`
46. `187ad85e` — Merge pull request #268 (ChatGPT execution route / pack bootstrap)
47. `788e55b9` — metadata `.72`
48. `fc69f5a6` — chore: preserve Pack Generator launcher file mode
49. `f46f5aed` — metadata `.72`
50. `559f2405` — fix: converge ChatGPT execution routes and pack bootstrap contract

Nie cherry-pickować tych 50 commitów: nowy branch już zaczyna się na ich końcowym
HEAD. Powyższa lista służy do audytu regresji i ustalenia właściciela konfliktów.

## 9 commitów starego brancha Studia — zweryfikowana lista

1. `11387b60` — feat(memory): rebase Jazn Memory Studio onto current master
2. `14504341` — release metadata `.70`
3. `f70be71a` — chore(release): bump Memory Studio master convergence to `.71`
4. `8047c407` — docs(memory): record master-based Studio continuation state
5. `767fc9a1` — release metadata `.71`
6. `3fbdf2d8` — test(memory): register restored Studio contracts on current master
7. `fd634de3` — release metadata for Studio test integration
8. `8c97b4ea` — fix(memory): tokenize source FTS probes without merging JSON boundaries
9. `24a373a8` — chore(release): synchronize Memory Studio FTS checkpoint metadata

Na nową linię przenosić efekt funkcjonalny, nie stare commity metadanych. Historyczne
metadane `.70/.71/.74` nie są źródłem prawdy dla drzewa opartego na `.73`.

## Stan prywatnej akceptacji odziedziczony jako dowód historyczny

- Test00: PASS na wcześniejszym kodzie;
- Test01: PASS na wcześniejszym kodzie;
- Test02: PASS na wcześniejszym kodzie;
- Test03: FAIL — normalna i odwrócona kolejność importu nie dają tego samego
  semantycznego snapshotu;
- poprawka FTS z `.74`: ukierunkowane testy przeszły, ale nie naprawia ona
  deterministyczności Test03;
- zamrożony benchmark: 13 przypadków, NIE URUCHOMIONY;
- Test04: NOT RUN;
- Final: NOT RUN.

Zachować stare raporty PASS/FAIL bez modyfikacji. Nie nadpisywać ich nowymi
wynikami i nie przenosić prywatnych artefaktów do repozytorium.

## Diagnoza Test03 — obecna przyczyna techniczna

`ProtocolEngine.run_test03()` buduje dwie świeże bazy: pierwszą z `build_paths`,
a drugą z `reversed(build_paths)`, następnie porównuje semantyczne snapshoty.
Warunek akceptacyjny `normal_reverse_semantic_reconciliation` wymaga równości.

Obecny `UnifiedCoreMixin.import_sources()` iteruje źródła w kolejności podanej
przez wywołującego. `UnifiedL0Store.ingest()` dla każdego `logical_key`:

1. odczytuje rekord `is_current_revision=1`;
2. przy innej treści wyłącza bieżącą rewizję;
3. nadaje `revision = current.revision + 1`;
4. wstawia właśnie importowany wariant jako nową rewizję bieżącą.

To oznacza, że numer rewizji i wybór `is_current_revision` są zależne od
kolejności importu. Odwrócenie tej samej unii źródeł może więc zmienić zarówno
historię rewizji, jak i końcowy rekord bieżący. Jest to zgodne z obserwowanym
FAIL Test03 i należy naprawić w silniku, nie w teście.

## Następny etap Codexa: naprawa deterministyczności

### Wymagania bezpieczeństwa

1. Zacząć od aktualnego HEAD tego brancha po zakończeniu botowych synców.
2. Wczytać `AGENTS.md` i `AGENTS.codex.md` w całości.
3. Potwierdzić czyste drzewo oraz bieżący `PACKAGE_VERSION_FULL`.
4. Utworzyć checkpoint commit przed zmianą semantyki importu.
5. Nie używać prywatnych danych jako test fixture. Minimalny przypadek
   regresyjny ma być syntetyczny.
6. Nie zmieniać `ProtocolEngine.validate_test03()` tak, by akceptował różne
   snapshoty. Nie usuwać porównania normal/reverse.
7. Każda systemowa poprawka po `.75` musi podnieść wersję, np. `.76`; nie
   przepisywać historii `.75`.

### Kontrakt poprawki

Oddzielić dwie semantyki:

- **batch reconstruction**: ta sama zamknięta unia źródeł ma dawać identyczny
  wynik niezależnie od kolejności argumentów;
- **explicit incremental update**: jawny późniejszy import nowego źródła może
  tworzyć następną rewizję, ale jego znaczenie nie może być przypadkowym skutkiem
  kolejności listy wejściowej podczas świeżej rekonstrukcji.

Nie wystarczy posortować ścieżek po nazwie. Ścieżka jest własnością środowiska,
nie semantyczną tożsamością źródła. Plan batch powinien używać stabilnych danych
źródłowych dostępnych po `adapter.prepare()`, co najmniej `adapter_id`,
`source_sha256`, `source_member`, a w rozstrzyganiu wariantów rekordów również
stabilnych właściwości `logical_key`, `content_sha256` i dostępnej chronologii
źródłowej. Jeżeli chronologia nie pozwala ustalić "nowszego" wariantu, wybór
musi być deterministyczny i jawnie opisany w proweniencji, a nie zależny od
kolejności pętli.

Preferowany kształt implementacji:

1. dodać prywatny etap przygotowania źródła, aby `adapter.prepare()` nie był
   wykonywany podwójnie;
2. dla `import_sources()` przygotować cały batch przed zapisem;
3. ustalić kanoniczny plan importu i/lub kanoniczny ranking wariantów;
4. zachować pojedyncze `import_source()` jako jawny incremental path;
5. dodać test z dwiema lub trzema syntetycznymi wersjami tego samego
   `logical_key`, importowanymi w co najmniej dwóch kolejnościach;
6. porównać nie tylko bieżącą treść, ale numery rewizji, occurrence links,
   `is_current_revision` i `_semantic_database_snapshot()`;
7. uruchomić istniejący test, który potwierdza, że ponowny identyczny import nie
   tworzy dodatkowej rewizji.

## Kolejność akceptacji po poprawce

Zmiana kodu deterministyczności zmienia silnik rekonstrukcji. Historyczne PASS-y
Test00-Test02 pozostają dowodem wcześniejszego checkpointu, ale nie są nowym
łańcuchem akceptacyjnym dla zmienionego `PACKAGE_VERSION`/commita. Kontrakt
`RunManifest.load_draft()` wymaga zgodności `system_version` i `base_commit`.
Dlatego po poprawce należy utworzyć nową sesję/proweniencję i wykonać minimalnie:

1. Test00 — ponownie dla niezmienionej unii źródeł, aby związać nowy run;
2. Test01 — świeża baza na poprawionym silniku;
3. Test02 — projekcje i niezmienność L0;
4. Test03 — normal/reverse; wymagany PASS bez wyjątków;
5. dopiero po PASS Test03 uruchomić zamrożony **13-case benchmark**;
6. Test04 — na dokładnie tym benchmarku, bez modyfikowania przypadków lub
   progów po zobaczeniu wyniku;
7. Final — tylko gdy cały nowy łańcuch jest PASS.

Jeżeli operator świadomie zdecyduje się użyć zewnętrznych wcześniejszych
artefaktów jako danych porównawczych, traktować je wyłącznie jako baseline, nie
jako zastępstwo nowego łańcucha Test00-Test02.

## Zamrożony benchmark 13-case

Nie generować nowego benchmarku w repo na podstawie prywatnych wspomnień.
Odnaleźć istniejący prywatny plik 13-case, sprawdzić jego hash i zachować go
bez zmian. Przed Test04 zweryfikować, że zawiera wymagane kategorie kontraktu:
`direct`, `paraphrase`, `referential_followup`, `temporal`, `update`, `conflict`,
`negative`, `provenance`, `sensitive_boundary`. Brak kategorii, zmiana hasha lub
zmiana liczby 13 przypadków ma blokować Test04 do wyjaśnienia.

## Timeout policy dla kontynuacji

Nie uruchamiać nieograniczonych komend. Timeout jest wynikiem `TIMEOUT/NOT
VERIFIED`, nigdy PASS.

- testy ukierunkowane dla poprawki deterministyczności: limit ścienny 5 min;
- Test00-Test03 na prywatnym operatorze: limit nadawać osobno każdemu etapowi;
  nie owijać całego łańcucha jednym nieograniczonym procesem;
- pełny deterministyczny pytest: limit 30 min, zgodny z `release-hardening`;
- Windows targeted CI: limit 20 min, zgodny z `release-hardening`;
- dependency matrix: limit 12 min na job, zgodny z `release-hardening`;
- manifest sync: limit 15 min;
- Pyright lokalnie: użyć jawnego limitu hosta; w CI podlega limitowi joba 30 min;
- każdy package-smoke uruchamiać osobno z jawnym limitem hosta i zachować kod
  wyjścia / raport zamiast powtarzać w nieskończoność.

Po timeout nie zabijać niepowiązanych procesów globalnie; zakończyć wyłącznie
proces potomny danego kroku i zachować artefakt diagnostyczny.

## Walidacja repo po naprawie Test03

Najpierw małe bramki, dopiero potem kosztowne:

```text
python -X utf8 -m compileall -q -x 'tests[\\/]archive[\\/]' latka_jazn tests main.py run.py
python -X utf8 -m pytest -q -ra --tb=short <testy deterministyczności + testy Memory Studio>
python -X utf8 tools/jazn_tests_studio/sync_contract_catalog.py --check
pyright latka_jazn main.py run.py
python -X utf8 -m pytest -q -ra --tb=short --durations=25 -m "not live_model and not live_mcp"
python -X utf8 run.py doctor --json
python -X utf8 run.py package-smoke --content system --json
```

Dla finalnego release candidate wykonać dodatkowo wymagane przez aktualny
`AGENTS.codex.md` package-smoke/release-build. Nie deklarować tych bramek jako
PASS na podstawie wyniku z `.71/.74`.

## Git / commity

Kontynuować małymi checkpointami, przykładowo:

1. `test(memory): reproduce order-dependent L0 revisions` — RED test;
2. `fix(memory): make batch reconstruction order-independent` — implementacja;
3. `test(memory): prove normal-reverse semantic reconciliation` — GREEN/regresje;
4. `chore(release): bump deterministic Memory Studio line to .76` — wersja;
5. kanoniczny sync Test Studio / release metadata przez tooling lub workflow;
6. `docs(memory): record Test03 and 13-case acceptance evidence` — wyłącznie
   sanitizowane, nieprywatne dane.

Commit z RED testem może istnieć jako checkpoint roboczy, ale branch przeznaczony
do PR nie może kończyć się na świadomie czerwonym stanie.

Nie force-pushować. Nie scalać do `master` bez osobnej autoryzacji użytkownika.

## Definition of Done dla tej linii

Linia może być nazwana kandydatem do scalenia dopiero, gdy jednocześnie:

- Studio jest zachowane na aktualnym master bez regresji `.72/.73`;
- Test03 przechodzi na realnej unii źródeł w obu kolejnościach;
- zamrożony 13-case benchmark przechodzi bez edycji po fakcie;
- Test04 PASS;
- Final PASS;
- pełny deterministyczny pytest PASS;
- Pyright PASS;
- compileall PASS;
- `doctor --json` PASS;
- wymagane package-smoke PASS;
- Test Studio catalog jest zsynchronizowany;
- canonical release metadata jest zsynchronizowane;
- GitHub CI jest zielone;
- repo nie zawiera prywatnych eksportów, baz SQLite/WAL/SHM ani prywatnych
  raportów operatora.
