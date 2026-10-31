# Audyt techniczny Jaźni — plan modernizacji całego systemu

Zakres: kanoniczny main.py, lokalny Runtime, JSS na Windows i Unix, MCP/ChatGPT, Ollama, LLM/NLP, MEMORY, testy i wydania.

## 1. Punkt wyjścia: co rzeczywiście mamy

Zweryfikowałem aktualny stan repozytorium [SmuklyLew/jazn_latka](https://github.com/SmuklyLew/jazn_latka).
**Gałąź:** `master` — zweryfikowana.

**Wydanie:** `16.3.25.5.116.0.34.94.6.53`

**SHA:** `5158116e1c7f8e0c2799549f4155a8d068cbbaca`

**4344** — wpisy w drzewie Git, w tym archiwa, dokumentacja i testy.
**5/5** — wcześniej zaliczone testy Live TPA.

PR #445 został scalony. Końcowy commit synchronizował metadane wydania 31 października 2026 r.

Repozytorium ma już rozbudowane, odrębne moduły Runtime, adapterów modeli, NLP, pamięci, MCP, narzędzi operatorskich i testów. Nie proponuję wyrzucania istniejącej Jaźni ani pisania wszystkiego od zera. W pierwszej kolejności trzeba ustabilizować kontrakty pomiędzy tymi modułami i sprawdzić, które z nich faktycznie realizują swoje deklarowane funkcje.

Istotne jest także rozróżnienie trzech poziomów jakości:
- Poprawność kodu: Python działa, testy przechodzą, dane są zapisywane prawidłowo.
- Poprawność systemu konwersacyjnego: model otrzymuje odpowiedni kontekst, narzędzia są wykonywane bezpiecznie, sesja i pamięć zachowują ciągłość.
- Jakość inteligencji i odpowiedzi: model rozumie polecenia, prowadzi naturalny dialog, nie zmyśla wspomnień i potrafi wiarygodnie wykorzystać dostępne informacje.
Ostatniego poziomu nie gwarantuje samo zwiększenie liczby modułów, testów pytest ani kolejna wersja numeracyjna Jaźni. Potrzebne są rzeczywiste oceny zachowania modelu na reprezentatywnych rozmowach. To podejście jest zgodne z praktykami ewaluacji systemów LLM.
[Źródło: OpenAI — Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)


## 2. Najważniejsze ustalenia audytu


### 2.1. Wykryłem dwa nieudane workflow GitHub Actions

Na ostatniej dużej aktualizacji kodu (bbc86940a4db, merge PR #445) wyniki CI nie były całkowicie zielone.
| Workflow | Wynik |
| --- | --- |
| Pyright — aktywne drzewo | PASS |
| MCP 2026-07-28 conformance | PASS |
| Stable test contracts | PASS |
| Package distribution cleanroom | PASS |
| Memory-cloud optional capability | PASS |
| Persistent runtime E2E | FAIL |
| Release hardening | FAIL |

To nie dowodzi automatycznie awarii wydania .53: późniejsze commity synchronizowały katalog testów i metadane release, a końcowy SHA ma znacznik [skip ci]. Oznacza jednak, że nie mamy jeszcze dowodu całkowicie zielonego CI na finalnym stanie master.

Pierwszym obowiązkowym zadaniem powinno być ustalenie przyczyn tych dwóch niepowodzeń i wykonanie pełnej walidacji bieżącego drzewa.

### 2.2. main.py i Runtime mają już dobrą podstawę, ale istotną złożoność

Odczytane pliki:
- run.py — cienki punkt wejścia (37 linii).
- main.py — około 2656 linii.
- latka_jazn/cli.py — około 1187 linii.
- latka_jazn/core/runtime_daemon.py — około 5379 linii.
To nie oznacza, że są niepoprawne. Jednak tak duże moduły zwiększają ryzyko regresji, szczególnie tam, gdzie spotykają się lifecycle, transport, sesja, zapis i finalizacja.

Zalecenie: zachować run.py → main.py jako oficjalną ścieżkę wejścia, ale stopniowo przenieść odpowiedzialności wykonawcze do mniejszych, testowalnych komponentów. Nie zmieniać publicznych komend CLI ani istniejących kontraktów sesji w jednej dużej przebudowie.

### 2.3. System LLM istnieje — problemem jest jakość i mierzalność, nie sam brak modelu

Odczytałem adapter Ollamy, fabrykę adapterów, resolver tras językowych, kompilator kontekstu oraz klasyfikator intencji.

Jaźń posiada już:
- wybór backendu (ChatGPT, Ollama, OpenAI-compatible, inne jawne adaptery);
- wywołanie modelu Ollama przez /api/chat;
- przekazywanie kontekstu rozmowy i pamięci;
- polityki ograniczające niepotwierdzone twierdzenia;
- kontrolę języka odpowiedzi i ponowną próbę przy nieprawidłowej odpowiedzi.
Znalazłem jednak konkretne ograniczenie: lokalny adapter Ollamy wywołuje model z "stream": false, a samodzielnie dodaje do żądania jedynie poprzednią wypowiedź użytkownika i odpowiedź asystenta, poza kontekstem skompilowanym w wiadomości systemowej.

To może wystarczyć w prostych scenariuszach, ale nie jest jeszcze pełną, elastyczną obsługą wieloturowego dialogu, strumieniowania, korzystania z narzędzi i różnych rozmiarów okna kontekstu.

Oficjalna dokumentacja Ollamy opisuje strumieniowanie wiadomości i tool_calls, których obsługa wymaga prawidłowego gromadzenia częściowych wyników. [Źródło: Ollama — Streaming](https://docs.ollama.com/capabilities/streaming)


Nie proponuję natychmiastowego włączenia wszystkiego naraz — najpierw trzeba zbudować porównywalne testy jakości i wydajności.

### 2.4. Ustaliłem dokładną przyczynę awarii Persistent Runtime E2E

Przejrzałem logi obu nieudanych zadań — Windows i Ubuntu.
Persistent Runtime E2E — 1 failed, 95 passed na obu systemach

Niepowodzenie: test_deployment_contract_tracks_runtime_and_real_mcp_wire_names
| Element | Wersja |
| --- | --- |
| PACKAGE_VERSION_FULL | .94.6.53-tpa-startup-diagnostics-jss-status |
| deploy/chatgpt_mcp/deployment.contract.json | .94.6.52-pypdf-6214-operator-contract-convergence |


To potwierdzony błąd spójności wersji deploymentu, nie wykazana awaria komunikacji MCP na Windows i Ubuntu.

Zweryfikowałem, że plik deployment.contract.json nadal ma starą wersję również w końcowym master. Dlatego ten test wymaga naprawy, a nie jedynie ponownego uruchomienia.
[Nieudany workflow Persistent Runtime E2E](https://github.com/SmuklyLew/jazn_latka/actions/runs/41247520878)

Drugi workflow — release-hardening — wykrył niesynchronizowane metadane podczas wykonywania. Późniejszy automatyczny commit 5158116e uzupełnił SOURCE_PROVENANCE.json i PACKAGE_INTEGRITY_MANIFEST.json. To usuwa widoczny dryf metadanych na poziomie Git, ale wymaga ponownego potwierdzenia testów na końcowym stanie wydania.
[Workflow Release Hardening](https://github.com/SmuklyLew/jazn_latka/actions/runs/41247520830)


### 2.5. Nie należy mylić niegotowej MEMORY z uszkodzeniem SQLite

Kod latka_jazn/db/runtime_sqlite.py zawiera już zabezpieczenie dotyczące błędu WAL-reset: dla niepoprawionych wersji SQLite wybiera tryb DELETE, a dla wersji z poprawką dopuszcza WAL.

To istotne, ponieważ SQLite oficjalnie dokumentuje wyścig WAL-reset i wersje zawierające poprawkę. [Źródło: SQLite — WAL](https://sqlite.org/wal.html)


Dlatego wal_reset_mitigation_required: true nie musi oznaczać, że mechanizm zabezpieczający nie działa. Trzeba zbadać także wal_reset_mitigation_active i rzeczywiście wybrany journal_mode.

Osobnym problemem pozostaje pełna autobiograficzna ciągłość Jaźni: wyszukiwanie pamięci, normalizacja, pochodzenie danych, prawidłowe odtwarzanie i wiarygodność wspomnień.

## 3. Docelowa architektura Jaźni

Proponuję zachować istniejący kanon projektu: Jaźń jest trwałym systemem, a LLM jest wymiennym silnikiem językowym.

To rozróżnienie jest fundamentalne. Model może interpretować wypowiedzi, formułować odpowiedzi, wybierać narzędzia i korzystać z kontekstu. Natomiast Runtime musi odpowiadać za tożsamość sesji, uprawnienia, pamięć, trwałość, kontrolę wykonania i prawdziwość deklarowanego stanu.
Interfejsy użytkownika

Terminal / main.py • JSS Qt • ChatGPT MCP • przyszłe aplikacje


Kanoniczny Runtime — jeden właściciel tury

Session • Turn • Policy • Tool execution • Persistence • Finalization


Kontekst i pamięć

Historia • Retrieval • Provenance • MEMORY gates


Model językowy

Ollama • Host ChatGPT • inne autoryzowane backendy


Walidacja i zatwierdzenie odpowiedzi

Źródła • Granice prawdy • Commit • ACK • Wynik widoczny


Taką architekturę wspiera już dokument projektu [CONVERSATION_RUNTIME_RESEARCH_BASE.md](https://github.com/SmuklyLew/jazn_latka/blob/master/docs/plans/CONVERSATION_RUNTIME_RESEARCH_BASE.md). Zalecam jego aktualizację i wykorzystanie jako kanonicznej podstawy dalszej przebudowy, zamiast tworzenia kolejnego niezależnego routera.

## 4. Szczegółowy plan aktualizacji P0–P5

Poniższe priorytety dotyczą nowego cyklu rozwoju, a nie istniejących oznaczeń P0–P5 wewnątrz TPA.


### P0 — spójność wydania, Runtime i diagnostyki


Najwyższy priorytet. Naprawy oparte na problemach rzeczywiście zaobserwowanych podczas tej rozmowy.


| Obszar / pliki | Wymagana zmiana |
| --- | --- |
| deploy/chatgpt_mcp/deployment.contract.json | Usunąć potwierdzoną niezgodność wersji .52 z .53. Zapewnić automatyczne wykrywanie dryfu przy każdym wydaniu. |
| tools/jazn_run_studio/probes.py | Rozdzielić /healthz i /readyz. Zastosować mierzalny budżet czasowy zamiast sztywnej 3-sekundowej sondy. |
| service_status_dialog.py | Zielony status tylko na podstawie kompletnych, świeżych dowodów; poprawne rozróżnianie timeoutu, braku gotowości i nieaktywnej usługi. |
| _active_extraction_cache_impl.py | Zbadać kolizje przy wspólnym .tmp, uprawnienia Windows, blokady plików i obsługę nieudanego os.replace. |
| runtime_supervisor.py i JSS | Oddzielić inactive, not_configured, stale i failed. Historycznie martwy supervisor nie może być przedstawiany jako bieżąca awaria Runtime. |
| Ustawienia Pythona | Zapisywać i jawnie pokazywać interpreter GUI, TPA, Runtime, MCP oraz modelu. Wykrywać konflikt JAZN_ROOT z worktree. |
| Ostrzeżenia Python | Usunąć nieprawidłowe sekwencje \m w dwóch skryptach SQLite i objąć je kontrolą ostrzeżeń. |

**Kryterium zakończenia P0:** pełne CI Windows/Ubuntu bez niepowodzeń; spójna wersja w deployment contract i metadanych; sonda MCP rozpoznaje poprawnie wyniki 200, 503 i timeout; testy Windows potwierdzają, że nieudany zapis markera nie uszkadza aktywnego stanu.

Ostatni pomiar /readyz wynosił 3,037 s przy limicie JSS 3 s. Zwiększenie limitu np. do 8 s będzie doraźną poprawą, ale w ramach P0 trzeba również profilować, dlaczego operacja statusu trwa kilka sekund.


### P1 — przebudowa i utwardzenie centralnego Runtime


Cel: czytelne moduły, jeden właściciel tury, niezawodne wznowienie i restart.


Zakres zmian:
- Zachować publiczne run.py, main.py i zgodność istniejących komend.
- Wyodrębnić z dużych modułów warstwy: Ingress, TurnCoordinator, SessionRepository, ModelExecution, ToolExecution, Finalization, Recovery.
- Wprowadzić jawny stan przejść dla każdej tury: RECEIVED → ADMITTED → RUNNING → RESULT_READY → FINALIZING → ACCEPTED, z osobnymi stanami błędów, anulowania i odzyskiwania.
- Zachować idempotencję request_id i pełne pochodzenie session_id, turn_id, trace_id.
- Rozdzielić własność procesu od jego dostępności i gotowości. Zapewnić stabilne ponowne połączenie klientów.
- Rejestrować opóźnienia poszczególnych etapów i przyczyny zatrzymań, bez ujawniania prywatnych treści.
Przy ekstrakcji modułów koniecznie zastosować characterization tests: ta sama wiadomość, stan i kontrakt muszą dawać identyczne obserwowalne zachowanie przed i po refaktoryzacji. Nie należy zmieniać routingu, NLP i formatu pamięci jednocześnie.

**Kryterium zakończenia P1:** wszystkie istniejące testy kontraktowe przechodzą; awaria procesu przed i po zapisie wyniku nie tworzy drugiej zaakceptowanej odpowiedzi; brak podwójnego wykonania skutków ubocznych; poprawne wznowienie po restarcie na Windows i Linux.


### P2 — profesjonalizacja LLM, NLP i jakości rozmowy


To najważniejszy etap dla odczuwalnej jakości konwersacji, ale należy go budować na stabilnym P1.


### 4.2.1. Warstwa modelu

W local_llm_adapter.py, fabryce adapterów i resolverze tras proponuję następujące usprawnienia:
| Zmiana | Cel |
| --- | --- |
| Wspólny kontrakt ModelCapabilities | Jawne wsparcie dla streaming, tool calling, JSON Schema, długości kontekstu, multimodalności i anulowania. |
| Pełna sekwencja wiadomości | Kontrolowane dołączanie wieloturowej historii zamiast polegania tylko na ostatniej parze i skompilowanej wiadomości systemowej. |
| Precyzyjny token budget | Liczenie kosztu kontekstu odpowiednie do modelu; heurystyka znaków/4 jako wyłącznie przybliżenie. |
| Streaming z finalnym zatwierdzeniem | Płynne wyświetlanie kandydatów bez przedwczesnego uznania częściowej odpowiedzi za zaakceptowaną. |
| Tool calling | Typowane wywołania, autoryzacja, limity kroków, kontrola argumentów i jawne wyniki. |
| Structured outputs | Walidacja odpowiedzi JSON/schema, osobno od tekstu konwersacyjnego. |
| Model routing i fallback | Jawna informacja o rzeczywistym providerze; żadna odpowiedź szablonowa nie może udawać wyniku modelu. |
| Telemetria modelu | Czas pierwszego tokenu, tokens/s, rozmiar promptu, retry, błędy, wybrany model i powód fallbacku. |

Wsparcie dla narzędzi i strumieniowania powinno wykorzystywać rzeczywisty kontrakt dostawcy, a nie lokalne imitacje odpowiedzi. [Źródło: Ollama — Tool calling](https://docs.ollama.com/capabilities/tool-calling)


### 4.2.2. NLP

dialogue_intent_classifier.py ma około 1190 linii i zawiera rozbudowane reguły leksykalne oraz priorytety intencji. Nie należy z góry uznawać ich wszystkich za błędne, ale potrzeba wyraźnie wyznaczyć im rolę.

Proponuję trzywarstwowe rozpoznawanie:

## 1. Reguły deterministyczne: komendy operacyjne, krytyczne ograniczenia bezpieczeństwa, jawne rozkazy, status Runtime.


## 2. Klasyfikacja semantyczna: wieloznaczne intencje, kontekst, odniesienia do wcześniejszych wypowiedzi, prośby mieszane.


## 3. Model językowy: rozumienie złożonej wypowiedzi, planowanie odpowiedzi i formułowanie naturalnego tekstu.

Reguła oparta na słowie „pamiętasz” nie powinna automatycznie rozstrzygać wszystkich znaczeń wypowiedzi. System powinien uwzględniać to, o czyjej pamięci jest mowa, w jakim kontekście i co zostało już powiedziane.

### 4.2.3. Rzeczywiste ewaluacje jakości Jaźni

Zaprojektowałbym osobny, bezpłatny i lokalny zestaw oceny — np. JAZN_CONVERSATION_EVALS — z własnymi danymi testowymi, ręcznie ustalonymi oczekiwaniami i opcjonalnym modelem oceniającym.

Proponowany początkowy zbiór: 300–500 przypadków, a nie udawany wynik aktualnego systemu.
**Proponowany rozkład 400 przypadków ewaluacyjnych** (plan, nie wyniki pomiarów):

| Kategoria | Liczba przypadków |
| --- | ---: |
| Dialog wieloturowy | 100 |
| Pamięć i źródła | 90 |
| Intencje/NLP | 70 |
| Narzędzia | 60 |
| Bezpieczeństwo | 50 |
| Błędy i recovery | 30 |

Dla każdego przypadku należy zapisać oczekiwane zachowanie, niedopuszczalne działania, wymagane źródła i warunki zaliczenia. Oceniać osobno skuteczność rozwiązania zadania, poprawność faktów, spójność sesji, naturalność polszczyzny, wierność pamięci i zgodność z polityką narzędzi.

Wyniki należy porównywać pomiędzy wersjami Jaźni, modelami Ollama oraz różnymi konfiguracjami kontekstu. Własny lokalny runner jest ważny również dlatego, że wcześniejsza usługa OpenAI Evals jest wygaszana; dokumentacja OpenAI zaleca budowanie ewaluacji z reprezentatywnych zestawów danych oraz ręczną kalibrację ocen. [Źródło: OpenAI — Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)


**Kryterium zakończenia P2:** zbudowany baseline jakości, mierzalna poprawa względem niego, brak regresji bezpieczeństwa i spójności, poprawne działanie minimum dwóch pełnych wieloturowych sesji na rzeczywistym modelu oraz kontrolowane porównanie kilku konfiguracji lokalnych.

Nie proponuję trenowania modelu od zera jako pierwszego kroku. To osobny, kosztowny proces. Najpierw warto poprawić sposób korzystania z istniejących modeli, a dopiero na podstawie ewaluacji rozważyć fine-tuning lub inne techniki adaptacji.


### P3 — MEMORY, recall, continuity i odporność danych


Cel: rzeczywista trwałość i odtwarzalność pamięci bez fałszywych twierdzeń autobiograficznych.


Rozdzieliłbym pięć niezależnych zdolności pamięci:
| Zdolność | Warunek zaliczenia |
| --- | --- |
| Zapis | Zdarzenie zapisane trwale, raz, z poprawną tożsamością i pochodzeniem |
| Wyszukiwanie | Znalezione rekordy odpowiadają rzeczywistemu zapytaniu |
| Pamięć autobiograficzna | Źródła rzeczywiście pochodzą ze zweryfikowanej MEMORY |
| Ciągłość sesji | Historia i stan zachowują spójność po reconnect/restart |
| Odbudowa | Migracja zachowuje dane, lineage i umożliwia zweryfikowany rollback |

Kluczowe zadania to kontrola memory_root, indeksów, normalizacji, zapisu transakcyjnego, deduplikacji, trwałych identyfikatorów, przywracania i progów recall. Każda odpowiedź opierająca się na wspomnieniu powinna mieć identyfikator źródła i informację o pewności — model nie powinien tworzyć wspomnienia tylko dlatego, że pasuje narracyjnie.

Dla SQLite nie należy automatycznie usuwać WAL ani wyłączać mechanizmów już wdrożonych w runtime_sqlite.py. Trzeba testować rzeczywiste transakcje, checkpointy, długie odczyty, sytuacje współbieżne i zgodność wersji SQLite. Dokumentacja SQLite wskazuje, że długie transakcje odczytu mogą blokować postęp checkpointu. [Źródło: SQLite — WAL](https://sqlite.org/wal.html)


**Kryterium zakończenia P3:** przywracanie kompletnego zestawu syntetycznej pamięci, brak utraty zatwierdzonych wpisów po kontrolowanej awarii, brak duplikatów po resume i osobno potwierdzona jakość recall. Prywatną MEMORY należy dołączać dopiero w autoryzowanym oknie serwisowym.


### P4 — JSS Windows, Unix, PTY i odbiory TPA


Cel: pełna aplikacja operatorska, nie tylko graficzny launcher komend.


Tutaj mamy jeszcze sporo rzeczywistej pracy.

Odczytałem [macierz migracji Studiów](https://github.com/SmuklyLew/jazn_latka/blob/master/tools/jazn_run_studio/STUDIO_MIGRATION.md). Dokument wyraźnie stwierdza, że żadne z 12 Studiów nie osiągnęło jeszcze pełnej natywnej zgodności funkcjonalnej Qt.

To ważniejsze niż wygląd samego JSS.

Zadania P4:
- Dokończyć natywne workflow Qt, zachowując wszystkie funkcje istniejących aplikacji, w tym preview, CAS, anulowanie, walidację, przywracanie i bezpieczne operacje na plikach.
- Wydzielić wspólne usługi biznesowe, z których korzystają CLI i GUI. Bez duplikowania logiki w widgetach.
- Udoskonalić panel usług, dodając odrębne stany i czas ostatniej weryfikacji, identyfikator instancji, PID, port, gotowość i czytelną diagnostykę.
- Dokończyć prawdziwe Windows ConPTY i Linux PTY: wejście, resize, Ctrl+C, EOF, zamykanie własnej sesji, obsługę ANSI/VT oraz bezpieczne sprzątanie.
- Zweryfikować Windows DPI 100/150/200%, nawigację klawiaturą, kontrast, dialogi i małe rozdzielczości.
- Sprawdzić pakiet EXE offline w czystym środowisku Windows oraz właściwe testy na Unix.
Obecny terminal ma już częściową obsługę PTY i ConPTY, ale dokumentacja projektu przyznaje, że pełna emulacja VT/ANSI i fizyczne testy nadal są nieukończone.

Długotrwałe operacje muszą odbywać się poza głównym wątkiem Qt. Oficjalna dokumentacja Qt zaleca worker objects i sygnały do przekazywania wyników, co odpowiada potrzebie zachowania responsywności JSS. [Źródło: Qt for Python — QThread](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html)


**Kryterium zakończenia P4:** rzeczywiste operacje wszystkich 12 Studiów działają w Qt albo są jawnie oznaczone BLOCKED; brak utraty możliwości legacy; pełny zestaw TPA ma oddzielne, zaakceptowane dowody na właściwym SHA; GUI nie zawiesza się podczas długich testów i diagnostyki.


### P5 — trwałe MCP, ChatGPT, bezpieczeństwo i produkcyjne wydania


Cel: niezawodne połączenie ChatGPT z istniejącą Jaźnią, bez uzależniania jej działania od jednej rozmowy lub executora.


W tym obszarze warto wykorzystać to, co już udało nam się potwierdzić:
- Lokalny Runtime Jaźni osiąga active_trusted i conversation_ready.
- MCP zwróciło tools/list z kompletem czterech narzędzi.
- /healthz i /readyz odpowiadały HTTP 200.
- Połączenie z obecną rozmową ChatGPT nadal nie zostało zweryfikowane.
Specyfikacja MCP 2026-07-28 jest bezstanowa na poziomie transportu, ale nie zabrania trwałej sesji aplikacji. Jaźń powinna utrzymywać session_id we własnym Runtime, a nie opierać jego ciągłość na ukrytym stanie połączenia HTTP. [Źródło: MCP — wydanie 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)


Plan P5 powinien obejmować weryfikację gotowości hosta, prawidłowego HTTPS/OAuth, kompletności uprawnień narzędzi i faktycznej finalizacji tury przez ChatGPT. tools/list i HTTP 200 są warunkami koniecznymi, ale nie wystarczającymi.

**Kryterium zakończenia P5:** rzeczywiste wywołanie jazn_status z ChatGPT, następnie dwie zaakceptowane tury, reconnect i wznowienie tego samego requestu bez duplikacji — z pełnym dowodem lineage i bez ujawnienia prywatnej MEMORY.

## 5. Kolejność realizacji — bez jednego ogromnego PR

Najbezpieczniej rozwijać projekt przez małe, logicznie niezależne PR-y, od najbliższych przyczyn błędów do złożonych zmian architektonicznych.
**Proponowana kolejność**

Każdy etap wymaga osobnego gate

#### 1. PR A — Release i JSS MCP


   Niezgodność deployment.contract.json, health/readiness, timeouty, wskaźniki, testy CI i kanoniczna synchronizacja metadanych.
#### 2. PR B — Runtime, markery i supervisor


   Bezpieczne zapisy, obsługa Windows WinError 5, diagnostyka lifecycle, ownership i testy crash/recovery.
#### 3. PR C — LLM evaluation baseline


   Zbiór testów dialogu, pipeline raportowania, porównanie konfiguracji i podstawowe metryki jakości.
#### 4. PR D — Refaktoryzacja orkiestracji


   Stopniowy podział dużych modułów bez zmian publicznych kontraktów.
#### 5. PR E — LLM/NLP i kontekst


   Dopiero po baseline: historia, token budgeting, tool calling, streaming i poprawa klasyfikacji.
#### 6. PR F — MEMORY


   Proweniencja, transactional persistence, recall, continuity oraz kontrolowana odbudowa.
#### 7. PR G — pełne JSS i TPA


   Migracja Studiów, PTY/ConPTY, GUI/DPI, EXE offline i fizyczne odbiory.
#### 8. PR H — ChatGPT/MCP production acceptance


   Bezpieczny transport, autoryzacja i prawdziwa finalizacja widocznych tur.

Część prac nad JSS i przygotowaniem ewaluacji może odbywać się równolegle, ale nie powinny jednocześnie modyfikować tego samego kontraktu Runtime.

## 6. Wymagania obowiązujące każdy PR

Przy pracy nad Jaźnią stosowałbym wspólny, rygorystyczny standard ukończenia:
| Bramka | Wymóg |
| --- | --- |
| Źródło | Osobny branch ze zweryfikowanego master |
| Odczyt repo | Najpierw wyszukiwanie plików, symboli i zależności; pełny odczyt tylko wybranych plików |
| Testy | Unit, contract, integration, fault injection i odpowiednie E2E |
| Typowanie | Pyright bez nowych błędów |
| Windows i Unix | Rzeczywiste przebiegi właściwych matryc CI |
| Runtime | Brak naruszenia aktywnego daemona i obcych procesów |
| MEMORY | Żadnych operacji na prywatnych bazach bez osobnej zgody |
| Release | Kanoniczny generator metadanych; żadnej ręcznej edycji hashy |
| PR | Wszystkie wymagane kontrole na aktualnym SHA |
| Odbiór | PASS regresji nie zastępuje PASS Live ani pełnego odbioru operatora |
| Merge | Wyłącznie po przeglądzie i Twojej zgodzie |

Ważne też, aby nie dopasowywać asercji testów do błędnego działania kodu. Jeśli test ujawni problem kontraktu, trzeba najpierw sprawdzić źródło prawdy i dopiero potem poprawić implementację lub formalnie zaktualizować wymaganie.

## 7. Jak sprawdzimy, że Jaźń rzeczywiście stała się lepsza?

Nie wystarczy raport „5000 passed”. Proponuję dwa niezależne zestawy kryteriów.

A. Systemowe: trwałość sesji, brak podwójnych zapisów, poprawna finalizacja, czas startu i odpowiedzi, brak zawieszeń, gotowość usług, zgodność wersji oraz poprawny powrót po awariach.

B. Konwersacyjne: spójność kontekstu, trafność odpowiedzi, jakość języka polskiego, sensowne użycie pamięci, rozpoznawanie intencji, zdolność do poprawiania własnych błędów, unikanie niepotwierdzonych wspomnień i naturalność dialogu.

Z punktu widzenia projektu Jaźni szczególnie ważne będą testy obejmujące takie sytuacje jak:
- Przywitanie, następnie pytanie „Co pamiętasz?”, a później odwołanie do wcześniejszej wypowiedzi.
- Rozmowa po reconnect i restarcie, gdy model otrzymuje zachowany kontekst.
- Pytanie o zdarzenie, którego nie ma w MEMORY — prawidłowe przyznanie braku danych.
- Pytanie techniczne, które wymaga użycia narzędzia zamiast wygenerowania domysłu.
- Zmiana tematu, ironia, korekta użytkownika, niepełne zdanie i niejednoznaczna intencja.
- Ten sam test uruchomiony z różnymi modelami, aby oddzielić jakość modelu od jakości orkiestracji.
Warto również stosować próby adversarialne i oceny ludzkie, ponieważ jakości naturalnego języka nie da się wiarygodnie określić samymi asercjami jednostkowymi. [Źródło: OpenAI — Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)


## 8. Jak powinno wyglądać nowe wydanie?

Docelowo każde wydanie Jaźni powinno zawierać maszynowo weryfikowalny raport z czterema odrębnymi kategoriami.
**Przykładowy kontrakt raportu wydania**

| SYSTEM | Integralność, provenance, version, CI, cleanroom |
| RUNTIME | Start, status, heartbeat, recovery, sesja, finalizacja |
| AI QUALITY | Baseline LLM, eval score, regresje językowe, memory grounding |
| OPERATOR | JSS, TPA, Windows/Unix, GUI, EXE, potwierdzone odbiory |

Każda kategoria ma własne PASS / FAIL / BLOCKED / NOT_RUN i identyfikator źródła. Żadna nie jest automatycznie zaliczana sukcesem innej kategorii.


## 9. Dokumentacja, którą wykorzystałem

Poza źródłami kodu Jaźni, kluczowe źródła zewnętrzne to:

- [Model Context Protocol — specyfikacja 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) — transport, narzędzia, stateless requests, Tasks i bezpieczeństwo.
- [Ollama — streaming](https://docs.ollama.com/capabilities/streaming) — poprawne odbieranie odpowiedzi i obsługa częściowych wyników.
- [OpenAI — Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices) — zestawy testowe, metryki jakości, regresje i oceny ludzkie.
- [SQLite — Write-Ahead Logging](https://sqlite.org/wal.html) — trwałość transakcji, współbieżność, checkpointy i WAL-reset.
- [Qt for Python — QThread](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html) — praca w tle, komunikacja wątków i responsywność GUI.


## 10. Końcowa rekomendacja

Zacząłbym od PR A, czyli naprawy spójności wydania i diagnostyki MCP w JSS. Mamy tam konkretne błędy, ich reprodukcję, wyniki HTTP i potwierdzone niepowodzenie CI.

Następnie PR B zabezpieczyłby Runtime, a równolegle przygotowałbym PR C — zestaw ewaluacji LLM. To pozwoli później poprawiać naturalność i inteligencję Jaźni na podstawie wyników, a nie wrażeń.

Cały projekt powinien zmierzać do sytuacji, w której:
- Jaźń potrafi prowadzić spójną rozmowę z lokalnym LLM i korzystać ze zweryfikowanej pamięci.
- JSS jest pełnoprawnym, wiarygodnym narzędziem zarządzania tą samą instancją.
- Terminal, GUI i ChatGPT korzystają z jednego kanonicznego Runtime.
- System nie udaje, że pamięta, działa lub komunikuje się z modelem, gdy nie ma na to dowodów.
- Każda aktualizacja jest mierzalnie bezpieczniejsza, stabilniejsza albo lepsza jakościowo.
Status audytu: zakończony na poziomie przeglądu architektury, wybranych pełnych plików źródłowych, historii tej rozmowy oraz rzeczywistych logów GitHub Actions. Nie jest to jeszcze pełny audyt każdej funkcji spośród tysięcy plików repozytorium ani uruchomienie całego zestawu testów. Nie modyfikowałem kodu, nie tworzyłem nowego PR i nie ingerowałem w aktywne procesy ani MEMORY.
