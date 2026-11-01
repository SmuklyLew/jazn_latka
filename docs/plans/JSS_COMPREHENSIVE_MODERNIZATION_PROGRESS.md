# JSS — kompleksowa modernizacja: plan i trwały stan

Specyfikacja użytkownika: „JAŹŃ JSS — kompleksowa modernizacja systemu i środowiska operatorskiego.md”, 2026-11-01, sekcje I–XVII (odczytane w całości).

## Stan bazowy i budżet

- Repozytorium: `SmuklyLew/jazn_latka`; checkout: `D:/.AI/jazn_latka_master`.
- Lokalny i zdalny `master`: `784f3aac8a56288cdb2e3af22e5bd1560228cd59`; drzewo przed pracą czyste.
- Wersja bazowa: `16.3.25.5.116.0.34.94.6.55`.
- Gałąź: `upgrade/jss-comprehensive-modernization`, utworzona z tej bazy.
- Oficjalny `get_usage_limits`: początkowo 2% / 5 h i 65% / tydzień; kolejny odczyt 9% / 5 h i 67% / tydzień.
- Reset 5 h: 2026-11-01 10:41:38 Europe/Warsaw; tygodnia: 2026-11-04 08:02:53 Europe/Warsaw.
- Użytkownik doprecyzował w tej sesji: progi 60/65/70% dotyczą **wyłącznie okna 5 h**. Tydzień monitorować osobno. Żadnych resetów, kredytów ani płatnych modeli.
- Prywatne/ignorowane `.settings_local`, runtime, eksporty, cache i środowiska zastane: zachowane, bez czyszczenia i bez dodawania do Git.
- GitHub connector zwrócił niedostępność narzędzia; aktualny zdalny SHA potwierdzony przez `git ls-remote`.

## Etapy i zależności

Każdy warunek poniżej wymaga dowodów na właściwym SHA. Testy celowane nie zamykają etapu. Nie przechodzić do kolejnego etapu bez wymaganej bramki poprzednika.

| Etap | Implementacja / pliki do sprawdzenia | Walidacja i warunek ukończenia | Stan |
|---|---|---|---|
| E0 | AGENTS.md, AGENTS.codex.md, ARCHITECTURE.md; istniejące katalogi Test Studio i 22 TPA; importy, entrypointy, workflow, migracje Studiów | Zapisany baseline, pełny aktywny katalog i macierz wykonawców; diagnoza luk bez duplikacji logiki | IN_PROGRESS |
| E1 (po E0) | `tpa_reports.py`, `tpa_catalog.py`, `tpa_engine.py`, `test_catalog_view.py`; trwały manifest, osobne wyniki TXT/JSON, integralność, czytnik historii | NOT_RUN widoczne; crash/recovery, read-only external history, redakcja, korupcja, SHA drift; Windows i Linux; P0 PASS | IN_PROGRESS |
| E2 (po E1) | `terminal_session.py`, `terminal_view.py`, `pty_controlling_child.py`, `operator_workspace.py`; profile, sesje i sprawdzony renderer VT | Każda dostępna powłoka, Unicode, stdin, interaktywny Python, Ctrl+C, exit/reopen, resize, ANSI/alternate buffer, kilka kart, własność i cleanup; osobne dowody P0.1 | NOT_RUN |
| E3 (po E2) | `release_metadata_sync`, generator manifestu/provenance, `.github/workflows/release-hardening.yml`; reprodukcja błędu z bazowego SHA | Zamrożone source SHA, canonical write, commit, final SHA check, idempotencja, brak pętli commitów; exact-head CI PASS | NOT_RUN |
| E4 (po E3) | `tpa_live.py`, `tpa_paths.py`, `chat.py`, `validation_worker.py`; kanoniczny runtime w oddzielnym stagingu | Windows: root/version/PID/instance/heartbeat, rzeczywisty model, dwie zaakceptowane tury, reconnect, ten sam request resume, finalizacja i własny cleanup; żadnego zastępowania live przez unit | NOT_RUN |
| E5 (po E4) | `STUDIO_MIGRATION.md`, `view_studios.py`, konfiguracja, MEMORY, rebuild, testy, generator, dependencies, Python, start, version; usługi istniejących właścicieli | Inwentaryzacja każdej funkcji, błędy/anulowanie/recovery, porównanie stary/nowy; 12 oddzielnych bramek; zachować legacy do parzystości | NOT_RUN |
| E6 (po E5) | `chat.py`, `chat_protocol.py`, `view_chat.py`, `view_events.py`; stan wielu sesji i trwały request_id | Izolacja wiadomości, restart GUI bez replay, tab switch, resume, ACK/display_exact, canonical history/export; jeden właściciel MEMORY i finalizacji | NOT_RUN |
| E7 (po E6) | shell, layout, theme, visual_system, operator_workspace i visual_ci; centralne karty/split, panele i fokus | 860×580, 1240×840, 1920×1080; DPI 100/150/200%; motywy, monitory, accessibility, rzeczywiste screenshoty i osobny manual acceptance | NOT_RUN |
| E8 (po E7) | Pełne SYSTEM/JSS/TPA, wszystkie wymagane workflow, pakiet EXE/offline, dokumentacja i instrukcje agentów | Pełna macierz Windows/Linux i live/operator, komplet dowodów, metadane deterministyczne na finalnym SHA; RELEASE_ACCEPTED tylko bez brakujących bramek | NOT_RUN |

## Ustalenia E0

- JSS ma już jeden modularny proces Qt (`view_*.py`), wspólny Controller, panel operatorski i walidowany layout. Nie wprowadzać drugiego control plane.
- `tpa_catalog.execution_map()` ma 22 scenariusze z 12 bramkami Studiów, przypisanymi regresjami oraz odrębnym pełnym odbiorem.
- `tpa_reports.RunStore` ma redakcję, atomowe compatibility reports, niezmienne rewizje, recovery i jawny eksport. Rozszerzać istniejącą logikę zamiast zastępować ją konkurencyjnym magazynem.
- Obecny `test_catalog_view.py` jest tylko czytnikiem oczekiwań; nie ma jeszcze pełnej historii wymaganej przez P0.
- Resolver lokalny obecnie autoryzuje `.settings_local/operator` (i wąski acceptance/operator), a nie dowolne `.settings_local/jazn_studio`. Preferowane miejsce specyfikacji trzeba pogodzić z tym kontraktem; nie dodawać szerokiego wyjątku bezpieczeństwa.
- Nie potwierdzono jeszcze pełnej parzystości, interaktywnej emulacji VT, finalnego release-hardening ani live acceptance. Obecność modułów nie jest dowodem tych bramek.

## Raporty i testy

Lokalne dowody tej sesji: `D:/.AI/codex_tasks/jss-modernization-20261101/evidence/`.
Pełne SYSTEM/JSS/CI/TPA/live i finalny release gate: **NOT_RUN** do czasu zapisania rzeczywistych wyników.

## Najbliższy krok

Kontynuować według najnowszego checkpointu poniżej i pliku `D:/.AI/codex_tasks/jss-modernization-20261101/CONTINUE_HERE.md`. Nie powtarzać zakończonej implementacji fundamentu. Nie rozpoczynać E2 przed P0 PASS.

## Checkpoint implementacji E0/E1 — 2026-11-01

Wdrożono fundament, nie zamknięto P0. RunStore ma niezmienny manifest i jawny zewnętrzny katalog dowodów. Nowy `test_evidence_archive.py` tworzy osobne TXT/JSON wszystkich wymaganych pozycji, kompletne snapshoty, SHA-256 i bezpieczny import/eksport ZIP. Odmawia zmiany manifestu i przeniesienia wykonanego wyniku na inne źródło. `test_history_view.py` daje asynchroniczny odczyt/import/eksport, filtry, porównanie przebiegów, ostatni sukces/porażkę i podgląd TXT/JSON/JUnit/logów. `test_evidence_plugin.py` jest adapterem istniejącego pytest: rejestruje zebrane parametryzacje, niezebrane aktywne definicje, 22 TPA i bramki terminali/GUI/platform/release. Setup/call/teardown mają niezmienne potwierdzenia. Błąd teardown lub kolekcji nie staje się PASS.

`tpa_view.py` ma teraz rozwijane klawiaturą zaawansowane filtry: kolejka mieści się w oknie 860×580, wyszukiwarka pozostaje widoczna. Podniesiono wersję SYSTEM i zgodne pola startup/deployment, katalog testów generuje kanoniczny synchronizator. Manifest/provenance generować z zatwierdzonego źródła. Workflow JSS zawiera nowe testy i JUnit upload na każdym wyniku; przypięty upstream action.yml potwierdza node24. Audyt 23 workflow: PASS.

Wyniki kolejnych przebiegów (nie sumować powtórzeń), raporty TXT/JUnit w `evidence/` katalogu zadania:

| Przebieg | Wynik | Pliki |
|---|---|---|
| Baseline TPA | 22 PASS | `baseline-tpa.*` |
| Pierwszy patch danych | 39 PASS, 1 SKIPPED (symlink capability) | `e1-data-first.*` |
| Dane + Qt | 43 PASS, 1 SKIPPED | `e1-data-qt.*` |
| Import ZIP + historia + istniejący katalog Qt | 30 PASS, 1 SKIPPED | `e1-import-qt.*` |
| Szersza TPA w ograniczonym procesie | 184 PASS, 9 FAIL, 2 SKIPPED | `e1-regression.*` |
| Ponowienie Git/junction na właściwym wykonawcy | 50 PASS, 1 FAIL (kompaktowy układ) | `e1-failures-native.*` |
| Stary katalog z master w procesie testowym (nie pełny baseline master) | 1 FAIL (ten sam układ) | `baseline-compact.*` |
| Poprawa układu bez zmiany istniejącej asercji | 4 PASS | `compact-fixed.*` |
| Adapter na rzeczywistym syntetycznym projekcie, przed dodatkowym testem częściowej kolekcji | 2 PASS | `e1-plugin-fixed.*` |
| Typy zmienionych modułów i nowych testów | PASS, 0 errors/warnings | `e1-types-checkpoint.txt` |
| Pierwsza pełna próba SYSTEM/JSS | 9 ERROR kolekcji, 2 SKIPPED, wykonanie przerwane | `full-system-jss.*` |

Pierwsza pełna próba wyłączyła autoload pluginów bez jawnego AnyIO; brakowało też httpx. To nie jest PASS suite. Manifest 3772 pozycji i dowody zachowano w `registered-full-run/run-171d559cf40f4fb3bbd0588ea205f66e/`. Oddzielne `venv/` zadania czyta zależności poprzedniego testowego venv i bazowego Pythona, ale instaluje nowe pakiety tylko u siebie. `httpx` zainstalowano w tym środowisku; raport z hashami: `evidence/httpx-install.json`. Ponowienie pełnej suite wymaga jawnego `-p anyio.pytest_plugin`.

Ostatni odczyt przy tym checkpoincie: 42% wykorzystania 5 h (58% pozostało, 23 punkty do STOP), tydzień 72%. Odświeżyć przed kolejnymi kosztownymi krokami.

Pozostałe E1: pełna walidacja Windows/Linux i wymaganych CI na końcowym SHA, indeks/paginacja pełnej historii, odtwarzanie częściowych potwierdzeń do GUI oraz pomiar/przeniesienie synchronicznego zapisu TPA poza GUI. Release/live/operator pozostają RELEASE_NOT_ACCEPTED. E2–E8 nie rozpoczęte.

### Dalszy mały patch fundamentu

Źródło pierwszego checkpointu: `07076e880529d13ddcf3fa901da663f06f6a407d`; jego metadane: `b6449cad9a53011be91f3cd123abd5893de2f57b`. Ostatnia szersza regresja rozpoczęta przed naprawą kompaktowego układu zakończyła się 201 PASS, 2 SKIPPED i 1 FAIL tego układu (`e1-final-regression.*`). Nie jest to PASS całej regresji.

Podgląd wykazał dodatkowo nadmierną szerokość historii z długimi identyfikatorami. Następny patch ogranicza wymagania szerokości pól, skraca podpisy przycisków z pełnymi etykietami accessibility, wymusza PlainText dla danych importowanych i ogranicza łączny rozmiar odczytanej historii. Niezmienione wymaganie 860×580 oraz nowy test historii przechodzą: 5 PASS (`history-responsive-fixed.*`). Typy: 0 errors/warnings. Wersja pochodzi dynamicznie z `latka_jazn/version.py`; oba kontrakty i katalog są synchronizowane razem.

Pełna ponowna suite ma ruszyć po commicie tego patcha, kanonicznej synchronizacji i kontroli rzeczywistego HEAD, w środowisku `venv/` zadania, z jawnym AnyIO i trwałym rejestrem. Stan wykonywanego checkpointu/walidacji: `D:/.AI/codex_tasks/jss-modernization-20261101/evidence/validation-state.json`. Jeżeli ma IN_PROGRESS, najpierw sprawdzić istniejący proces i raport; nie uruchamiać drugiego przebiegu. Żaden zrzut offscreen nie zalicza odbioru wizualnego realnego Windows ani P0.

### Kontynuacja po zmianie budżetu przez użytkownika

Użytkownik polecił wykorzystać dalsze 20 punktów procentowych przy 63% zużycia, pozostawiając 17% na checkpoint. Nowy próg zakończenia zwykłej implementacji to około 83% wykorzystania okna 5 h; rezerwy nie trzeba zużywać. Oficjalny odczyt przy przygotowaniu tego zapisu: 75% / 5 h i 77% / tydzień. Reset pozostaje jak wyżej. Nie uruchomiono resetu, kredytów ani dodatkowych modeli.

PR #450 jest Draft, gałąź i baza bez zmian. Poprzedni końcowy HEAD `2dc2727ecc191b214e8d3ce3755c986bc09f5a84` miał zgodne metadane (3617 plików), lecz CI ujawniło brak deklaracji pytest dla adaptera dowodów. Wersja .58 dodaje opcjonalny profil `test-evidence`, poza core/release, test rzeczywistego audytu importów oraz wygenerowany kanonicznie lock Windows/Python 3.14. Dependency Studio zweryfikowało sześć wheel i wykonało izolowaną instalację offline z pip check/import smoke/inventory. Próba cross-target bez natywnego locka została poprawnie odrzucona; pozostałych platform nie zaliczono. Workflow zbiera natywne locki i manifesty w każdej pozycji macierzy.

Poprzedni pełny przebieg przerwano po potwierdzeniu własności procesu: test koloru podmieniał klasę w starym module `window`, podczas gdy implementacja korzysta z `view_settings`. Poprawiono wyłącznie miejsce podmiany, zachowując asercje i archiwizując oryginalny test z commita 2dc. Pełny raport częściowy i receipts zachowane; status **INTERRUPTED**, nie PASS. Pierwotny skrypt narzucał globalne JAZN_MEMORY_ROOT/MODE i zakłócał syntetyczne fixture; nie należy ich ustawiać globalnie w pełnej suite. Nie zmieniano prywatnej MEMORY ani runtime w celu uzyskania zielonych testów.

Po korekcie środowiska: `resume-targeted.*` **28 PASS**; wszystkie moduły z wcześniejszych porażek: `resume-prior-failures.*` **89 PASS, 2 SKIPPED** (fixtures POSIX); typy **0 błędów i ostrzeżeń**, audyt Node24 **PASS, 23 workflow**. Wyników przebiegów nie sumować. Nowy pełny przebieg ma osobny stan `evidence/validation-resume-state.json`, raporty `full-system-jss-resume.*` i rejestr `registered-resume-run/`. E0/E1 nadal IN_PROGRESS, E2–E8 NOT_RUN; RELEASE_NOT_ACCEPTED.

### Wznowienie po odnowieniu okna 5 h

Oficjalny odczyt przed wznowieniem: 0% okna 5 h, 78% tygodnia. Zweryfikowano czyste drzewo, lokalny/zdalny/PR HEAD `50d4c33f7653b7ee324a6cc9de4895db518dc8ed`, bazę master `784f3aac8a56288cdb2e3af22e5bd1560228cd59` i otwarty Draft PR #450. Końcowe CI tego SHA: 74 SUCCESS, 3 FAILURE, 3 SKIPPED. Pełna lokalna suite: 3603 PASS, 2 FAIL, 31 SKIPPED, 7 ostrzeżeń. Linux verify: 3615 PASS, 1 FAIL, 19 SKIPPED. Historyczne wyniki nie są aktualizowane do PASS.

Wersja .59 usuwa przyczynę błędu okna stanu: `observe()` odświeża projekcję otrzymanego dowodu również przy ukrytym oknie, więc otwarcie nie pokazuje poprzedniego stanu. Żaden probe/lifecycle nie jest uruchamiany przez to odświeżenie. Oryginalny test pozostaje niezmieniony. Testy okna i kontraktów wersji: **15 PASS**, `evidence/renewed-status-fix.*`.

Izolowana diagnoza drugiej porażki potwierdziła `IncompleteRead`: klient widzi Transfer-Encoding: chunked i surowy JSON zamiast długości pierwszego fragmentu. Obserwacja własnego serwera pokazuje odpowiedź Content-Length; różnica wymaga dalszego wyjaśnienia, nie uzasadnia obchodzenia parsera ani zaliczenia testu. Helpery diagnostyczne i logi obu końców są poza repozytorium w katalogu zadania (`renewed-mcp-framing-*.txt`, `mcp-framing-*/mcp-http-process.log`). Nie użyto prywatnego runtime/MEMORY. Windows cleanroom readiness również pozostaje otwarte. E0/E1 nadal IN_PROGRESS, release NOT_ACCEPTED.

### E1 — odczyt potwierdzeń po niezamkniętym pytest (.60)

Niezależny fixture stdlib potwierdził lokalną blokadę HTTP bez Jaźni/SDK: odpowiedź Content-Length dociera jako chunked z nieopakowanym body; oba warianty opener (domyślny i proxy-disabled) kończą się IncompleteRead. `evidence/renewed-independent-loopback.json` nie jest PASS MCP; parser pozostaje fail-closed. CI poprawki .59 na SHA `1042d3a77efa785402f51de585b46fba91c95c89` miało przy ostatnim odczycie 77 SUCCESS, 2 SKIPPED, 1 IN_PROGRESS i brak porażek; odświeżyć terminalny stan przed odbiorem.

`test_evidence_receipts.py` odtwarza wyłącznie widok w pamięci, powiązany z wcześniej zweryfikowaną rewizją, źródłem i manifestem. Weryfikuje SHA, TXT/JSON, scenariusz, fazy, unikalność, kolejność i limity. PASS wymaga kompletnego setup/call/teardown; niepełna faza nie jest zaliczana ani dowodem żywego procesu. Widok Qt oznacza NIEZAMKNIĘTY i odmawia eksportu jako pełnej rewizji. Końcowy snapshot pozostaje autorytatywny. Uszkodzony ZIP kończy zadanie GUI jawnym błędem zamiast pozostawiać je zajęte.

Próba dużego historycznego przebiegu ujawniła różnicę redakcji: stary manifest miał surową nazwę parametryzacji, JSON nazwę zredagowaną, TXT ponownie surową. Naprawiono właściciela RunStore: redakcja przed zamrożeniem; TXT powstaje z tego samego zredagowanego wyniku co JSON. Nowy manifest jawnie zapisuje politykę redakcji; starszy format ma ograniczoną zgodność stabilnych reguł, bez dzisiejszych sekretów. Eksport wykrywalnie niezredagowanego manifestu jest blokowany. Nowe raporty zawierają też nazwę scenariusza, a wyszukiwanie obejmuje tę nazwę.

Dowody rozwojowe (nie sumować): `receipt-recovery-fixed.*` 43 PASS, 1 SKIPPED; `receipt-recovery-redaction.*` 66 PASS, 1 SKIPPED; `receipt-legacy-boundary.*` 26 PASS, 1 SKIPPED; `receipt-import-errors.*` 2 PASS. Końcowa regresja celowana `receipt-recovery-precommit.*`: **69 PASS, 1 SKIPPED**. Typy całego JSS i nowego testu: **0 błędów, 0 ostrzeżeń** (`receipt-recovery-final-types.txt`); Node24 **23 workflow PASS**. Wymagane pozostają pełna suite i CI zamrożonego końcowego SHA. Rzeczywisty proces fixture pytest kończy się nagle przez os._exit(7); każdy test korupcji dostaje osobną kopię jego dowodów.

Duży zachowany przebieg z SHA `2dc2727e` odczytano bez błędu: 4781 receipts, 3779 pozycji; historyczne 1554 PASS, 29 FAIL, 13 SKIPPED, 1 RUNNING (niepotwierdzone zakończenie), 2182 NOT_RUN. Status UNSEALED / RELEASE_NOT_ACCEPTED. Pełna weryfikacja trwała 121 s poza wątkiem GUI; to ograniczenie wydajności, nie odbiór pełnego indeksu. Raport: `evidence/receipt-recovery-real-legacy-final.json`. Nie zmieniono źródłowych raportów ani historycznego wyniku przerwanego przebiegu.

Nadal otwarte E1: kompletna integracja rejestru z wykonawcami CI, pełny indeks/paginacja i dowód responsywności zapisu TPA. E0/E1 IN_PROGRESS, E2–E8 NOT_RUN; realny model/rozmowa/finalizacja/operator acceptance NOT_RUN.

### E1 — strony scenariuszy i pierwszy indeks (.61)

Pełna rejestrowana lokalna suite .60 na SHA `9d382202180070ff10e222a157b9cdf6e76771c4` zakończyła się **3619 PASS, 1 FAIL, 31 SKIPPED, 7 ostrzeżeń** w 720.13 s. Jedyna porażka: MCP HTTP framing, odtworzony niezależnym fixture stdlib. Raporty `full-system-jss-receipts.*`, rejestr `registered-receipts-run/`. Nie oznaczać tej suite jako PASS. Ostatni odczyt CI tego SHA: 77 SUCCESS, 2 SKIPPED, 1 IN_PROGRESS; odświeżyć przed odbiorem.

Historia ma strony po 300 scenariuszy zamiast ucięcia widoku do pierwszych 300. Przyciski i licznik pozostają w dotychczasowym pasku, bez powiększenia okna 860×580. Filtry przeszukują cały przebieg i resetują stronę. Błąd importu nie odblokowuje eksportu niezamkniętego podglądu. Cztery testy Qt na 601 syntetycznych scenariuszach przeszły przed zastosowaniem zmiany; podgląd `history-pagination-candidate-860.png` sprawdzono wizualnie. To nie jest fizyczny odbiór operatora ani dowód pełnego indeksu wszystkich przebiegów.

Odtworzono też błąd pierwszego indeksu pytest: wykonawca był oznaczany dopiero po początkowym zapisie, więc duży indeks traktowano jak zwykły TPA. RunStore przyjmuje jawny rodzaj wykonania przed pierwszym manifestem/snapshotem; pytest i TPARunner przekazują go podczas create. Limity produkcyjne nie zostały zmienione. Test granicy przed poprawką: 1 FAIL, 1 PASS; po poprawce regresja indeksu, stron, historii, recovery, TPA i wersji: **53 PASS**, `history-index-pagination.*`.

Końcowe nowe kontrakty po doprecyzowaniu typu QApplication: **6 PASS** (`history-index-pagination-final.*`). Typy całego JSS i obu nowych plików: **0 błędów, 0 ostrzeżeń** (`history-index-pagination-types-fixed.txt`); Node24 **23 workflow PASS**. Pierwszy odczyt typów ujawnił brak zawężenia QCoreApplication do QApplication w nowej fixture; poprawiono rzeczywistą kontrolą typu, bez ignorowania diagnostyki. Przed zapisem tego punktu budżet: 53% / 5 h, 87% / tydzień. Nie rozpoczynać większego patcha zapisu TPA przed kolejną sesją z dostatecznym zapasem; zachować wyniki końcowego pipeline i instrukcję wznowienia.

Nadal otwarte E1: pełny indeks starszych przebiegów, kompletna integracja wszystkich wykonawców/CI i asynchroniczny zapis TPA. Pomiar `tpa-write-responsiveness-baseline.json`: create 0.310 s, save 0.206–0.222 s; przerwa pętli Qt 0.310 s. Wyłącznie własne raporty w izolowanym katalogu, bez scenariuszy/usług. Większy patch opisano w `D:/.AI/codex_tasks/jss-modernization-20261101/NEXT_TPA_WRITE_STEP.md`; wymaga nowego zapasu budżetu i osobnej pełnej walidacji. E0/E1 pozostają IN_PROGRESS, E2–E8 NOT_RUN, RELEASE_NOT_ACCEPTED.

### E1 — asynchroniczny zapis automatycznej kolejki TPA (.62)

Wznowienie: rzeczywisty local/origin/PR HEAD 00bcf8b6, Draft PR #450, master
784f3aac bez zmian; czyste drzewo przed edycją. Oficjalne okno odnowione: 0% / 5 h
i 0% tygodnia przy starcie; nie uruchomiono resetu ani kredytów. Obowiązuje ponownie
operacyjny STOP 65% / 5 h. Ostatni pomiar podczas patcha: 22% / 5 h, 4% tygodnia.

RunStore.prepare/begin rozdziela budowę kontraktu i jego trwały zapis, zachowując
synchroniczne publiczne create/save. Aktywna TPARunner używa jednego szeregowego
workera, kopii raportów i kontynuacji Qt. Manifest poprzedza preflight, RUNNING
poprzedza start procesu, completed czeka na finalny snapshot i własny cleanup.
Walidacja i zapis JUnit/log/live pracują poza GUI; anulowanie, awaria dysku i
przepełnienie kolejki nie uruchamiają zależnych procesów. Błąd cleanup jest jawny.
Ręczny zapis obserwacji operatorskiej pozostaje do osobnego przeglądu.

Pierwsza regresja ujawniła głodzenie workerów przez QTest.qWait zatrzymujące GIL.
Helper istniejącego testu pompuje teraz zdarzenia i oddaje GIL przez time.sleep,
z zachowaniem timeoutu i asercji. Oryginały dwóch zmienionych testów zachowane
bajt w bajt w tests/archive z blob SHA w README. Wyniki rozwojowe zachowane,
nie są zamieniane na PASS: pierwszy 9 FAIL / 5 PASS, wariant qWait+yield 6 FAIL /
34 PASS i 1 FAIL / 4 PASS nowych barier. Poprawiony event pump: **45 PASS**.

Regresja przed commitem: **85 PASS, 1 SKIPPED**, `async-tpa-precommit.*`;
końcowe 7 kontraktów barier: **7 PASS**, `async-tpa-barriers-final.*`.
Typy całego JSS i trzech testów: **0 błędów, 0 ostrzeżeń**,
`async-tpa-types-fixed.txt`; wcześniejszy błąd typu fixture zachowany osobno.
Node24: **PASS, 23 workflow**. Workflow JSS zapisuje rejestr i przesyła go
również przy porażce kroku kontraktów; pozostałe kroki/wykonawcy nadal wymagają
kompletnej integracji.

Rzeczywisty QApplication.exec i 25 własnych zapisów: wszystkie poza wątkiem GUI,
start_selection 14.5 ms, maksymalna przerwa heartbeat **27.8 ms**, poprzednio
310 ms. Raport `tpa-write-responsiveness-async.txt`. Celowo brakujące pliki testów
dają 22 BLOCKED, nie PASS; pomiar nie zalicza runtime/modelu/fizycznego GUI.

Pełna suite .61 na HEAD 00bcf8b6: **3625 PASS, 1 FAIL, 31 SKIPPED**, 789.98 s;
FAIL MCP framing, odtworzony niezależnym stdlib. Końcowe CI .61: **77 SUCCESS,
1 FAILURE, 2 SKIPPED**; Windows health-check 6.5006942 s wobec progu <5 s.
Nie osłabiono parsera, SLA ani asercji. Te wyniki są historyczne, nie zaliczają .62.
Nowy patch wymaga przypiętego pełnego przebiegu, metadanych i exact-head CI.
E0/E1 nadal IN_PROGRESS: pozostają pełny indeks starszych przebiegów, integracja
pozostałych wykonawców/CI, ręczny zapis, Windows/Linux i niezaliczone bramki.
E2–E8 NOT_RUN; RELEASE_NOT_ACCEPTED.
