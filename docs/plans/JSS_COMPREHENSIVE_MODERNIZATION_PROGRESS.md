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

### E1 — kompletna odmowa preflight (.63)

Pełna lokalna suite .62 na 3002abdb: **3631 PASS, 2 FAIL, 31 SKIPPED,
7 ostrzeżeń**, 795.14 s; `full-system-jss-async-tpa.*`, rejestr
`registered-async-tpa-run/`. Porażki: starszy test widoku lokalnego odbioru i
znane lokalne ramkowanie HTTP MCP. Linux verify: **3643 PASS, 1 FAIL,
19 SKIPPED**, 153.80 s; jedyna porażka to ten sam test widoku. Log
`ci-async-verify-linux.txt`. Macierz JSS Windows/Linux ma identyczny objaw.

Test oczekiwał w QTest.qWait, zatrzymując GIL. Oddanie GIL przy zachowanych
100 iteracjach po 10 ms ujawniło dodatkowo zbędne pośrednie zapisy odmowy.
Przy nieudanym preflight żaden scenariusz nie może wystartować: kolejka zapisuje
teraz początkowy manifest/snapshot i jeden kompletny końcowy raport wszystkich
BLOCKED (lub CANCELLED przy anulowaniu). Zaliczonego preflight i bariery RUNNING
przed procesem nie zmieniono. Nowy test wymaga dokładnie dwóch trwałych zapisów,
braku startu procesu i wszystkich BLOCKED/full_gate NOT_RUN na dysku.

Oryginały obu rozszerzonych testów zachowano w tests/archive z blob SHA.
Asercje poprzedniego testu i liczba/czas jego oczekiwań pozostały takie same.
Celowana regresja poprawki: **26 PASS**, `async-refusal-targeted.*`.
Typy całego JSS i dwóch testów: **0 errors/warnings**, `async-refusal-types.txt`.
Szersza rejestrowana regresja: **69 PASS**, `async-refusal-precommit.*`,
`registered-refusal-targeted/run-0e9faf958f3f4b9da655b9233c066a1d/`.
Wymagane są jeszcze metadane, pełna suite i exact-head CI .63.
Historycznych porażek .62 nie zmieniać na PASS. E0/E1 IN_PROGRESS; E2–E8 NOT_RUN.

### E1 — pierwsza trwała rewizja odmowy i publikacja GUI po zapisie (.64)

Użytkownik autoryzował wykorzystanie pozostałych 30% okna po wcześniejszym STOP;
ta zgoda zastępuje próg 65/70% wyłącznie dla tej kontynuacji. Przy wznowieniu
oficjalny odczyt wynosił 71% / 5 h, 11% tygodnia. Nie uruchomiono resetów,
kredytów ani dodatkowych modeli. Ostatni kontrolny odczyt podczas patcha: 75%.
Checkout/origin/PR przed edycją: 450273b7, czyste drzewo, master 784f3aac bez zmian.

Kontrolowany test na niezmiennym runnerze .63 z commita 450273b7 odtworzył błąd:
zatrzymany końcowy zapis pozostawia GUI już BLOCKED, mimo braku zatwierdzenia
końcowej rewizji. Wynik **1 FAIL**, `invalid-refusal-baseline.*`, zachowany.
To potwierdza przedwczesną publikację stanu; większa szybkość testu nie jest
wystarczającą poprawką tej niespójności.

W .64 pusta, względna lub nieistniejąca ścieżka Pythona jest odrzucana przez
walidację argumentu przed uruchomieniem procesu. Kopia kompletnego raportu odmowy
jest zapisywana w pierwszym kanonicznym snapshotcie, po niezmiennym manifeście.
GUI zachowuje QUEUED do potwierdzenia trwałości; dopiero wtedy przyjmuje BLOCKED,
środowisko i czas zakończenia. probe_executed=false i puste imports jawnie
odróżniają odmowę od rzeczywistej kontroli importów. Normalny preflight,
fsync/snapshot, bariera RUNNING i kanoniczny właściciel pozostają zachowane.

Nowe kontrakty zatrzymują końcowy zapis i sprawdzają brak przedwczesnego wyniku,
anulowanie, błąd dysku, brak uruchomionego dziecka oraz zgodność każdej publikacji
BLOCKED z odczytem dysku. Oryginał rozszerzonego testu z .63 zachowany bajt w bajt
w tests/archive z blob SHA. Istniejący test odbioru Windows pozostaje bez zmian,
włącznie ze 100 oczekiwaniami po 10 ms i odczytem BLOCKED z dysku.

Pierwsza regresja: **30 PASS**, `invalid-refusal-first.*`; typy całego JSS i
dwóch testów: **0 errors/warnings**, `invalid-refusal-types.txt`; Node24:
**23 workflow PASS**, `invalid-refusal-node24.txt`. Szersza rejestrowana regresja:
**73 PASS**, `invalid-refusal-precommit.*`, `registered-invalid-precommit/`.
Metadane, pełna suite i exact-head CI wymagają końcowych dowodów. Brak zamknięcia P0:
indeks historii, pozostali wykonawcy/CI, ręczne obserwacje i lokalny MCP pozostają
otwarte; E0/E1 IN_PROGRESS, E2–E8 NOT_RUN, RELEASE_NOT_ACCEPTED.

### E1 — koszt zimnej identyfikacji Windows (.65)

Po potwierdzeniu nowego przydziału (1% / 5 h, 0% tygodnia) obowiązuje ponownie
STOP65%, bez wyjątku z poprzedniego okna. Potwierdzono czyste lokalne/origin/PR
27dd38c3, Draft PR450 i niezmienny master784f3aac. Poprzednia pełna suite .64
jest zakończona: **3637 PASS, 1 FAIL, 31 SKIPPED, 7 ostrzeżeń**,737.62s;
`full-system-jss-invalid-refusal.*`. Nie uruchamiać jej ponownie. CI .64:
75 SUCCESS /2 FAILURE /3 SKIPPED. Błędy Windows3.14 i health<5s pozostają historyczne.

Rzeczywisty profil pierwszego zapisu w nowym natywnym procesie wskazał 4 zapytania
WMI przez platform.system/platform:151.9ms, wobec35ms wszystkich54fsync.
Raport `initial-refusal-profile-baseline.json`. Windows snapshot używa teraz
sys.getwindowsversion().platform_version i jawnej identyfikacji Python/bitowości
procesu zapisującego. Dane wybranego interpretera pozostają oddzielne. Brak
rozgrzewania, cache poprzedniego wyniku, redukcji dowodów lub fsync. Pozostałe OS
zachowują dotychczasowy format identyfikacji; starsze snapshoty nadal czytelne.

Nowe testy przed poprawką **2 FAIL** (`cold-platform-before.*`); po poprawce
archiwum i niezmieniony odbiór Windows: **36 PASS,1 SKIPPED** (`cold-platform-after.*`).
Typy **0 errors/warnings**, Node24 **23 workflow PASS**. Nowy zimny profil:
worker281.2ms, całość295.5ms wobec407.0ms; nadal54fsync, zeroWMI.
`initial-refusal-profile-native.json`. Potwierdzenie hosted Windows3.14, pełna
walidacja i P0 nadal wymagane; E0/E1 IN_PROGRESS, E2–E8 NOT_RUN.

### P0 — zachowanie decyzji no-probe przy tworzeniu adaptera (.66)

Nowe kontrakty przed poprawką: **3 FAIL,1 PASS**, `route-no-probe-before.*`.
build_speech_adapter_for_turn i build_model_guided_speech_status przekazywały
rozpoznaną konfigurację do fabryki, która ponownie wybierała trasę i wykonywała
probe mimo probe_local=False. Fabryka ma teraz zgodny domyślny resolve_route=True,
a oba miejsca konstrukcji już rozpoznanej trasy używają resolve_route=False.
Domyślna publiczna fabryka nadal rozpoznaje trasę; jawny probe warstwy mowy
wykonywany jest dokładnie raz. Brak globalnych flag omijających testy lub zmian SLA.

Regresja routingu, orkiestracji, adapterów i wersji: **76 PASS**,
`route-resolution-regression.*`; typy **0 errors/warnings**. Niezmieniony test
zdrowia <5s przeszedł; całe wywołanie testowe trwało lokalnie0.87s. Pierwszy
zakres atomowości i nowych kontraktów: **18 PASS**, `route-no-probe-after.*`.
Hosted PowerShell i pełna walidacja końcowego SHA pozostają do potwierdzenia.

### E1 — trwałość ręcznych obserwacji i załączników (.67)

Oba zapisy działają teraz na kopii raportu. Artefakt jest tworzony bez
nadpisywania, flush/fsync poprzedza commit RunStore, a raport wywołującego jest
aktualizowany dopiero po jego sukcesie. Błąd zapisu artefaktu lub raportu pozostawia
poprzedni stan w pamięci i na dysku; nie usuwa osieroconych własnych dowodów.
Wymagania PASS, aktualność źródła, redakcja i odrębna bramka operatora pozostają.

Nowe testy przed poprawką: **6 FAIL**, JUnit `manual-commit-before.xml`; pierwsza
próba miała dodatkowo błąd cleanup systemowego TEMP. Kolejne przebiegi używają
wyłącznie TEMP zadania, a wstrzyknięty błąd fsync jest cofany przed raportowaniem
przez pytest, aby nie obejmował adaptera dowodów. Nie zmieniono asercji.
Nowe kontrakty z aktywnym rejestrem: **6 PASS**, `manual-commit-after.*` i
`registered-manual-commit/`. To syntetyczne dane testowe, bez odbioru człowieka.
Szersza regresja ujawniła zachowywaną referencję do wiersza: **52 PASS,1 FAIL**,
`manual-commit-regression.*`. Przyjęcie kopii aktualizuje teraz istniejące wiersze
i listy wyników po zatwierdzeniu, bez unieważniania referencji. Niezmieniony stary
test i nowe kontrole tożsamości przechodzą: **53 PASS**, `manual-commit-compatible.*`;
typy **0 errors/warnings**. Nie zmieniano istniejących testów.
Przeniesienie ręcznych operacji GUI poza główny wątek i pełne P0 pozostają otwarte.
# .68 — evidence phase identity, 2026-11-02

The pinned .67 full run terminated with pytest exit3 / INTERNALERROR after
1817 PASS and16 SKIPPED. The Windows metadata regression deliberately forbids
platform inventory, exposing a phase-hook call that rebuilt the frozen
definition solely to compute its identifier. Hosted JSS matrices failed at
the same adapter call; their old acceptance step was not reached.

Phase hooks now compute only the canonical stable nodeid hash and look up the
existing result row. Manifest construction still captures the environment
before execution. No assertions, tests or timing limits were weakened.
Registered platform/phase/plugin regression:6PASS,63.75s; targeted Pyright
0errors/0warnings. Evidence phase-identity.{txt,xml}, phase-identity-types.txt
and registered-phase-identity/ under the external task directory. Full .67
report remains evidence/full-system-jss-renewed-foundation.{txt,xml}; it is an
incomplete failed validation, never a complete PASS. E0/E1 still IN_PROGRESS.

# .69 — storage-level history pages, 2026-11-02

RunStore and verified snapshots now expose bounded read-only pages, continuation
cursors, explicit errors and inventory counts. The 100-run/64MiB limits apply
per page, with no lost record at byte boundaries. Keyset discovery uses a bounded
heap; inventory changes invalidate continuation explicitly. Legacy compatible
reports remain reachable through RunStore; missing snapshot seals are reported
as errors rather than silently omitted. Existing per-document/run integrity
limits remain intact. Both history views provide older/newer navigation and
read pages off the Qt thread. Previous PASS/FAIL labels explicitly describe
the loaded page; this does not claim a global outcome index.

Registered store/Qt/workspace validation:35PASS,1SKIPPED (OS symlink capability),
101.46s; history-store-final.{txt,xml}, registered-history-store/. Actual fixtures
cover104 persisted runs, >64MiB of verified text evidence, stable forward/back
navigation, errors and background thread use. Initial combined check57PASS,
1FAIL,2SKIPPED exposed new counter minimum-width overflow; fixed layout, then
unchanged Qt/workspace checks20PASS. Pyright0errors/0warnings, Node24 auditPASS.

An earlier large unbroken-word fixture was explicitly INTERRUPTED after exposing
existing quadratic secret-assignment redaction; process identities and diagnosis
are preserved in history-store-interrupted*. Separate bounded subprocess
regression confirms2FAIL/10PASS (redaction-scaling-before.*). This defect remains
open; the successful pagination fixture uses normal multiline text logs. No
complete P0 or release acceptance is claimed. Full final-SHA validation pending.

# .70 — bounded assignment redaction, 2026-11-02

The independently reproduced long-word defect is repaired in the canonical
Studio Redactor. Assignment keys are scanned once, then classified; secret
values retain the same masking, including nested assignments inside public
values. Existing tests remain unchanged. Before:2FAIL/10PASS (owned five-second
subprocess timeouts). After:47PASS across new scaling/compatibility cases,
existing Studio contracts, checkpoint redaction and manual evidence failures.
The original12MiB unbroken-word shape now completes in0.598s using the actual
Redactor (redaction-12mib-after.json). This is synthetic performance evidence,
not live/operator acceptance. Whole JSS/new tests Pyright0errors/0warnings.

E0/E1 remain IN_PROGRESS. CI/executor registry integration, off-GUI manual
observations, final-SHA full validation and live Windows/Linux gates remain
open. The .67 hosted health-check latency/no-write step is SUCCESS; its full
PowerShell suite was still running at last observation. Hosted JSS .67 matrix
failed at the phase identity defect, now fixed in .68; no claim that its later
Windows3.14 local acceptance step ran. Same Draft PR450, no merge.

# .71 — Windows index stability and operator label, 2026-11-02

Pinned .70 full validation TERMINAL:3675PASS,3FAIL,32SKIPPED,7warnings,
738.64s, full-system-jss-history-redaction.{txt,xml} and registered receipts.
Two new failures were the delayed NTFS directory mtime invalidating a read-only
history scan and the old operator label disappearing during asynchronous read.
The third remains the independently diagnosed MCP HTTP framing failure.

Storage pages now order and fingerprint closed report indexes instead of
directory mtimes. Missing/refused indexes remain discoverable. Cursor scope
includes the indexing policy. Existing dock label is preserved during and after
background reads; no assertion changed. New deterministic index-policy cases
3PASS; unchanged archive/receipt/unified-dock regression42PASS/1SKIPPED,
48.88s. Whole JSS/new tests Pyright0errors/0warnings. Evidence index-stability-*.
Hosted .70 JSS Linux3.12/3.13/3.14 SUCCESS; Windows matrix failed the same
cursor defect before reaching later local-acceptance assertions. Windows3.14
timing acceptance remains unconfirmed. E0/E1 IN_PROGRESS; release not accepted.

# .72 — asynchronous manual evidence, 2026-11-02

TPAPanel submits copied reports to a serial I/O lane for observation/attachment
validation, artifact fsync and RunStore persistence. GUI report rows and attached
proofs are adopted only after the durable acknowledgement, preserving held row
aliases. Controls prevent concurrent mutation; close waits for the pending
write. A failed write reports its real error and retains prior visible state.
No test or acceptance time limit changed. Synthetic tests use FAIL observations,
not fabricated human acceptance.

Controlled baseline4FAIL (held synchronous writes blocked the caller); after
10PASS including backend fault injection. Registered TPA regression56PASS,
85.09s, including unchanged local-acceptance, automated persistence and execution
contracts. Evidence manual-async-{before,after,regression}.{txt,xml},
registered-manual-async/. Whole JSS/new tests types0errors/0warnings and
Node24 auditPASS. Required complete final-SHA Windows/Linux/live matrix is open.

User explicitly authorized live acceptance in local Work under D:/.AI. Read-only
Ollama inventory confirms gemma3:latest; owned TPA panel/plan observer is prepared
under the external task directory. No model download, active MEMORY mutation or
foreign process adoption. Live has not started at this source checkpoint.
Task3 remaining executor/CI integration is not implemented. All23 workflows have
been inspected; in particular preserve the no-checkout/dependency-empty consumer
job in package-distribution-cleanroom when adding any recorder. Do not introduce
a source checkout into that cleanroom just to load a local composite action.
E0/E1 IN_PROGRESS; E2–E8NOT_RUN; RELEASE_NOT_ACCEPTED. Budget68%five-hour/11%weekly
at last official read; latest user extension is scoped to this window only.

