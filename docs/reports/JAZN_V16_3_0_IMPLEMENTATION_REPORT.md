# Jaźń — raport implementacji bieżącego wydania: pełna konwergencja rozmowy i pamięci

## Status dokumentu

Ten raport rozdziela trzy klasy stwierdzeń:

- **zweryfikowane** — istnieje bieżący wynik narzędzia albo bezpośredni dowód w drzewie roboczym;
- **oczekujące na zamknięcie** — implementacja jest obecna, ale pełna bramka wydaniowa nie została jeszcze wykonana lub odnotowana;
- **nie testowano** — w tej turze nie wykonano testu wymagającego prywatnych danych, aktywnego modelu albo zewnętrznego środowiska.

Dokument nie jest dowodem aktywnego runtime i nie zastępuje markerów, żywego PID, endpointu, heartbeat ani poprawnej tury one-shot. Stan końcowego PR i GitHub Actions należy uzupełnić po ich rzeczywistym wykonaniu.

## Punkt startowy i cel wydania

| Pole | Wartość | Status |
| --- | --- | --- |
| Repozytorium | `SmuklyLew/jazn_latka` | zweryfikowane |
| Bazowy `origin/master` | `cc1cb1575ea02a6f6cd4ee0d79bae9a83f785a88` | zweryfikowane |
| Branch roboczy | bieżący branch zadania | zweryfikowane przez Git; jego nazwa nie jest duplikowana jako aktywny literał wersji |
| Wersja dystrybucji i pakietu | wartość kanoniczna | zweryfikowane w `latka_jazn/version.py` |
| Nazwa wydania | wartość kanoniczna | zweryfikowane w `latka_jazn/version.py` |
| Docelowy branch PR | `master` | oczekujące na zamknięcie |
| Merge do `master` | zabroniony bez osobnej zgody operatora | nie wykonano |

Prace rozpoczęto ze świeżego `origin/master`, a nie ze stagingowego brancha v16.2.5. Przed zmianami utworzono lokalny, timestampowany ref bezpieczeństwa wskazujący dokładny punkt startowy.

## Diagnoza zastanego stanu

### Nieukończony transport v16.2.5

Na bazowym `master` znajdował się jednorazowy transport `.github/.v1625-upload/payload.*` wraz z workflow, ale nie odpowiadający mu spójny kod produkcyjny. Zrekonstruowany strumień payloadu miał 64 899 bajtów i nie zgadzał się z deklarowanym SHA-256. Audyt wykrył dwa uszkodzenia transportowe w `payload.04`. Po ich jednoznacznej korekcie odtworzony patch miał 64 881 bajtów i SHA-256:

`f878eabe44b08915cb1f6b388dc2f5d9cab2437a935e141ed7acd74dfdd9d1ad`

`git apply --check` dla naprawionego patcha przeszedł. Patch nie został jednak zastosowany mechanicznie: jego 63 hunki w 22 plikach porównano z bieżącym kodem, a nadal potrzebną semantykę zintegrowano ręcznie z nowszym `master`.

### Niespójności architektoniczne

Audyt kodu potwierdził następujące klasy problemów:

- rozproszone i częściowo sprzeczne rozpoznawanie intencji pamięciowych;
- traktowanie roku lub miesiąca jako tokenu FTS zamiast zakresu czasu;
- możliwość przejścia rzeczywistego recall przez zwykły handler dialogowy;
- utratę source-backed kontekstu pamięci przy regeneracji kandydata i drugiej fazie finalizacji hosta;
- brak trwałej, integralnościowej kotwicy przywołanego wspomnienia dla follow-upów, korekt i powrotu do tematu;
- zbyt liberalne fallbacki identyfikatorów pamięci i akceptacji kandydatów;
- niewystarczające rozdzielenie odkrycia źródła pamięci od zaufania uprawniającego do recall;
- pozostałości stagingowe, self-removing workflow i `sitecustomize.py`, które nie były właściwą funkcjonalnością runtime;
- lokalne problemy narrowingu typów w ścieżce recovery/autoload.

Szczegółowa klasyfikacja branchy, commitów i hunków znajduje się w osobnym raporcie konwergencji branchy.

## Zaimplementowane zmiany

### 1. Kanoniczny kontrakt intencji pamięciowych

Dodano `latka_jazn/core/memory_intent_contract.py` jako wspólne źródło semantyki dla klasyfikacji, gate, planowania wyszukiwania i NLG. Kontrakt:

- rozróżnia pytanie o zdolność pamiętania od prośby o rzeczywistą treść pamięci;
- rozpoznaje recall, zapis, zapominanie, negację, kontrast, follow-up referencyjny i korektę;
- obsługuje polską fleksję oraz parafrazy, a nie wyłącznie exact-match;
- wyznacza zakresy roku, poprzedniego roku, miesiąca i zakresu miesięcy w strefie `Europe/Warsaw`;
- pozwala odziedziczyć poprzedni zakres czasu wyłącznie w kontrolowanym follow-upie.

Classifier, `memory_use_gate`, planner oraz ścieżki NLG korzystają z tego kontraktu. Pytania typu „czy potrafisz pamiętać” nie uruchamiają retrieval, a negacja nie jest interpretowana jako recall. Kontrast typu „nie wspominaj 2025, tylko przypomnij 2024” wybiera żądany zakres 2024.

### 2. Temporal recall od tekstu do warstwy living/unified memory

`MemorySearchPlanner` przenosi teraz temporal scope jako dane strukturalne, usuwa wyrażenie czasowe z zapytania leksykalnego i umożliwia plan temporal-only. Dzięki temu `2025` nie musi występować literalnie w treści dokumentu FTS.

`ConversationArchiveStore.search` przyjmuje zwalidowany, półotwarty zakres UTC i:

- odrzuca niepoprawny typ, precyzję, wartości niefinitywne oraz odwrócone granice;
- obsługuje pusty query tekstowy, gdy istnieje prawidłowy temporal scope;
- filtruje zarówno ścieżkę FTS, jak i temporal-only;
- normalizuje liczbowe i tekstowe znaczniki czasu;
- stosuje ograniczone bucket sampling oraz równomierny wybór, zamiast zwracać wyłącznie pierwszy przypadkowy rekord;
- ujawnia strategię próbkowania i liczbę kandydatów bez wycieku prywatnej treści.

Zakres temporalny jest przekazywany również przez living/unified memory gateway. Nieobsługujące go stare backendy nie mogą po cichu udawać poprawnego temporal recall; rezultat ma jawny stan degradacji/fail-closed.

### 3. Dedykowany `MemoryExperienceRecallHandler`

Rzeczywisty recall został wyłączony z `OrdinaryDialogueHandler` i skierowany do osobnego handlera. Handler generuje odpowiedź tylko z zamrożonego `memory_recall_payload`, zachowuje identyfikatory i provenance, usuwa duplikaty oraz odrzuca:

- pusty lub pozbawiony źródła payload;
- echo bieżącej wiadomości użytkownika;
- elementy odrzucone, quarantined, superseded albo oznaczone jako niewiarygodne;
- źródła o brakującej lub zbyt niskiej pewności tożsamości.

Brak wiarygodnych wyników prowadzi do kontrolowanej odpowiedzi bez roszczenia pamięciowego, a nie do wygenerowania fikcyjnego wspomnienia.

### 4. Ciągłość kontekstu i trwała kotwica wspomnienia

`DialogueTaskState` przechowuje ograniczoną, integralnościową kotwicę zadania pamięciowego: pierwotne query i jego SHA-256, temporal scope, source/item IDs oraz skróty excerptów. Stan odróżnia historyczne źródło od korekt użytkownika.

Korekta jest zapisywana jako osobna `user_asserted_overlay`; nie przepisuje po cichu historycznego źródła. Integralność kotwicy jest ponownie sprawdzana po deserializacji, a niezgodność hash powoduje stan invalid/fail-closed. Bounded state wspiera follow-upy („co wtedy czułaś?”), zmianę tematu, powrót do wcześniejszego wspomnienia oraz odtworzenie po restarcie bez zamiany bieżącej wypowiedzi w historyczną pamięć.

Ten mechanizm został włączony w checkpoint i odtworzenie konwersacji. Izolowany zestaw restart continuity potwierdził 19/19 przypadków: wieloturowy recall z syntetycznego archiwum, korektę, zmianę tematu, zapis checkpointu, ponowne utworzenie store, weryfikację wake-bindingu, powrót do wspomnienia oraz odzyskanie oczekujących zadań po restarcie daemona/workera.

### 5. Source-backed context przez syntezę, regenerację i wybór kandydata

`RuntimeResponseSynthesizer` przyjmuje `memory_context`, a obie ścieżki lokalnej regeneracji dostają ten sam zamrożony kontekst ramki tury. Presenter i builder kontraktu preferują zatwierdzony payload zamiast odbudowywania go z luźnych warstw. Identyfikatory elementów są stabilne i wyprowadzane z treści źródłowej.

Usunięto fallback, który dopisywał do kandydata wszystkie dozwolone identyfikatory pamięci bez deklaracji faktycznego użycia. Model może zadeklarować wyłącznie ograniczony podzbiór IDs obecny w zaakceptowanym kontekście. Usunięto też runtime fallback force-accept. Gdy wszystkie kandydaty naruszają granicę prawdy, selector tworzy bezpieczną odpowiedź bez roszczenia source-backed recall.

### 6. Dwufazowa finalizacja ChatGPT/MCP i provenance narzędzi

Druga faza finalizacji sprawdza rzeczywisty SHA kontekstu względem niezmiennego bindingu. Jedyna dozwolona próba naprawcza zachowuje dokładnie ten sam `host_generation_context`, jego hash, binding runtime i dane continuity. MCP przenosi ten kontekst bez rozszerzania zaufania.

Host helper przenosi ograniczone `used_memory_item_ids` oraz `external_tool_evidence`, ale nie dziedziczy automatycznie dowodów z odrzuconego kandydata. Regresja łączona potwierdza, że retry zachowuje dozwolony memory item, a jednocześnie:

- `web.run` może spełnić kontrakt wymagający zewnętrznego webu tylko przy rzeczywistym, poprawnym evidence;
- GitHub zachowuje własne provenance i sam nie spełnia wymogu `web.run`;
- końcowy rezultat zachowuje zarówno SHA kontekstu pamięci, jak i evidence narzędzia.

### 7. Zaufanie źródła, autoload i granice pamięci

Odkrycie strukturalnie poprawnego źródła zostało oddzielone od decyzji, czy źródło jest zaufane do recall. Gateway ujawnia stan i podstawę zaufania, a źródło niezweryfikowane nie zostaje wybrane jako recall-ready tylko dlatego, że istnieje w registry lub ma poprawny schemat.

Zachowano kontrakty v16.2.4: standalone `profile=memory`, bezpieczne auto-attach, walidację manifestu, bounded limits, legacy v3 repack, read-only retrieval oraz brak automatycznej promocji L2/L3. Mutable `workspace_runtime` pozostaje oddzielony od pakietu systemowego.

### 8. Recovery i typy

W `latka_jazn/bootstrap/chatgpt_recovery.py` surowe dane sidecar są najpierw zwężane do właściwego kształtu, a dopiero potem lokalnie rzutowane. Zmiana usuwa nieprawidłowe użycie optional/unknown bez globalnego wyłączania diagnostyki, szerokiego `type: ignore` ani osłabiania kontraktu runtime.

### 9. Usunięcie transportu i ustawienie wersji

Usunięto jednorazowe payloady i workflow v16.2.5, wcześniejszy bootstrap payload v15.4.3, self-removing triggery/workflow, skrypt naprawczy oraz repozytoryjny `sitecustomize.py`. Końcowy kod nie wymaga workflow, aby funkcjonalność Jaźni pojawiła się w źródłach.

Kanoniczna wersja i nazwa aktywnego kontraktu zostały ustawione wyłącznie w `latka_jazn/version.py`. Historycznych raportów i historycznych numerów wersji nie przepisywano.

## Zachowane granice prawdy

| Własność | Stan |
| --- | --- |
| Brak pamięci nie uprawnia do konfabulacji | zweryfikowane regresją handlera i kandydata |
| Bieżąca wiadomość nie staje się automatycznie wspomnieniem historycznym | zweryfikowane regresją current-turn echo |
| Korekta użytkownika nie nadpisuje historycznego źródła | zweryfikowane regresją kotwicy zadania |
| Nieudokumentowane memory item IDs nie są automatycznie przypisywane modelowi | zweryfikowane regresją generatora/evaluatora |
| GitHub nie udaje `web.run` | zweryfikowane regresją finalizacji hosta |
| Retry nie zmienia zamrożonego kontekstu pamięci | zweryfikowane regresją MCP end-to-end |
| Samo odkrycie źródła nie oznacza zaufania do recall | zweryfikowane regresją living memory source trust |
| Automatyczna promocja L2/L3 | nie została włączona ani autoryzowana |

## Wyniki walidacji dostępne w chwili sporządzenia raportu

Poniższe liczby są wynikami faktycznie uruchomionych zestawów. Zestawy częściowo się nakładają, dlatego nie należy ich sumować jako liczby unikalnych testów.

| Bramka | Wynik | Status |
| --- | --- | --- |
| Baseline przed implementacją, v16.2.4 host/tool + autoload + recall timeout/archive/living | `30 passed` | zweryfikowane |
| Nowy kontrakt intencji i temporal planner | `26 passed` | zweryfikowane |
| Szerszy zestaw planner/gateway | `65 passed` | zweryfikowane |
| Temporal-only conversation archive | `3 passed` | zweryfikowane |
| Dedykowany handler recall | `6 passed`; szerszy zestaw `34 passed` | zweryfikowane |
| Fail-closed memory provenance/candidates | `4 passed`; szerszy zestaw `20 passed` | zweryfikowane |
| Recall timeout compatibility | `6 passed` | zweryfikowane |
| Host contract | `25 passed`; szerszy zestaw `21 passed`; krytyczny zestaw `5 passed`; finalny probe `1 passed` | zweryfikowane |
| Łączny targeted closure suite bieżącego wydania | `116 passed` | zweryfikowane |
| Focused packaging/autoload regressions | `84 passed, 2 skipped` | zweryfikowane; dwa testy symlink pominięte na bieżącym Windows |
| Pyright kodu produkcyjnego | `0 errors, 0 warnings` | zweryfikowane |
| Dedykowany Pyright testów/generatora | `0 errors, 0 warnings` | zweryfikowane |
| Semantic route audit | `132/132`, `ok=true` | zweryfikowane |
| Cognitive architecture audit | wszystkie wymagane kontrole `ok` | zweryfikowane |
| Końcowy pełny deterministic pytest | `973 passed, 5 skipped` | zweryfikowane; pominięcia: brak `termios`, dwa opcjonalne przypadki PyNaCl i dwa testy symlink bez uprawnienia Windows |
| Końcowy Windows regression suite | `82 passed, 2 skipped`; atomicity/timeout `41 passed` | zweryfikowane; dwa pominięcia dotyczą braku uprawnienia do symlink |
| Izolowany restart continuity | `19 passed` | zweryfikowane |
| Packaging/autoload/legacy contract suite | `67 passed` | zweryfikowane; wyłącznie syntetyczne fixture, bez prywatnej pamięci |

Read-only probe `run.py memory-plan --root . --json "powspominaj 2025 rok"` zwrócił bieżącą wersję z `latka_jazn/version.py`, pusty leksykalny focus dla temporal-only query i strukturalny zakres roku. Brak manifestu prywatnego archiwum został zgłoszony jako `archive_not_ready`; nie przedstawiono go jako udanego recall.

## Prywatny benchmark pamięci

Prywatny acceptance benchmark **nie został uruchomiony w tej turze**. W związku z tym nie ma podstaw do twierdzenia, że bieżące wydanie poprawiło rzeczywisty private recall.

Bezpieczne dane historyczne służą wyłącznie jako punkt odniesienia:

- wcześniejszy wynik v16.1.2 wynosił `6/15`;
- osobny późniejszy kandydat miał zagregowany wynik `0.533333`, ale pogorszył metrykę wrong-conversation i nie dawał podstaw do aktywacji.

Żaden z tych wyników nie jest wynikiem bieżącej implementacji. Do repozytorium nie wprowadzono prywatnych zapytań, treści, nazw źródeł, ścieżek ani baz.

## Stan obszaru chronionego w chwili sporządzenia

Bieżący status drzewa nie wykazuje zmian pod `memory/` ani `workspace_runtime/`. Raport nie zawiera SQLite, WAL/SHM, ZIP, sekretów, tokenów, prywatnych eksportów ani surowych danych benchmarku. Kontrolę powtórzono po commitach implementacji, pierwszym kanonicznym metadata sync i finalnym clean-tree package smoke.

## Końcowe bramki lokalne i zdalne

Poniższa tabela zapisuje wyłącznie wyniki rzeczywiście uzyskane. Pozycje zdalne pozostają oczekujące do czasu publikacji brancha i zakończenia GitHub Actions.

| Bramka końcowa | Wynik | Stan |
| --- | --- | --- |
| `git diff --check` na drzewie po implementacji i metadanych | exit `0` | zweryfikowane; końcowy guard powtarza tę kontrolę |
| Pełny `compileall` | exit `0` | zweryfikowane |
| Pełny deterministic pytest | `973 passed, 5 skipped in 101.93s` | zweryfikowane |
| Windows regression suite | `82 passed, 2 skipped in 2.85s`; atomicity/timeout `41 passed in 3.99s` | zweryfikowane |
| Izolowany runtime smoke input → finalization → checkpoint | package smoke: wszystkie 14 wymaganych kontroli zaliczone; 1 opcjonalna kontrola manifestu źródłowego niezaliczona przed metadata sync | zweryfikowane z jawnym ograniczeniem |
| Izolowany restart continuity (task/wake/temporal/source/checkpoint) | `19 passed in 3.55s` | zweryfikowane w syntetycznym, odseparowanym środowisku |
| Live local model/Ollama | probe `ok`; `gemma3:latest` zainstalowany; generacja `completed`, `generated=true`, 0 tool calls, 54 znaki | zweryfikowane dla bezpośredniego adaptera z syntetycznym kontekstem; walidator/finalizacja sprawdzone osobno |
| System-only i finalny release package smoke | przejściowy system smoke: 14 wymaganych kontroli zaliczonych; po metadata sync clean-tree profil `release`: `15/15`, `failed=0`, `optional_failed=0` | zweryfikowane |
| System + osobna pamięć i independent memory contract | w zestawie packaging/autoload `67 passed` | zweryfikowane na syntetycznych fixture |
| Legacy memory v3 repack smoke | w zestawie packaging/autoload `67 passed` | zweryfikowane: segmentacja JSONL, SQLite online backup, v3 i odtworzenie integralności |
| Kanoniczny metadata sync i kontrola idempotencji | `ok=true`; wersja i source commit zgodne; `static_file_count=822`; `mutable_runtime_file_count=0`; drugi czysty przebieg pozostawił oba SHA-256 bez zmian | zweryfikowane |
| Clean-checkout guard i finalny protected-path audit | workflow guard: `dirty_count=0`; 0 taskowych artefaktów; 0 zmian chronionych rootów lub binarnych danych; 0 staging payload/workflow | zweryfikowane |
| Ponowny fetch i closure audit świeżych branchy | fetch `2026-08-24T23:01:30.2009361Z`; `origin/master=cc1cb157…`; 0 nowych/zmienionych rzeczywistych tipów; `unreviewed=0` | zweryfikowane |
| Push brancha i PR do `master` | do uzupełnienia numerem/URL | oczekujące na zamknięcie |
| Wymagane GitHub Actions | do uzupełnienia nazwami runów i wynikami | oczekujące na zamknięcie |

## Znane ograniczenia i uczciwe wnioski

- Zmiany oraz focused regressions dowodzą spójności kontraktów, lecz bez bieżącego prywatnego benchmarku nie dowodzą poprawy recall na produkcyjnej pamięci.
- Izolowane regresje dowodzą zapisu, ponownego wczytania i ciągłości po restarcie store/daemona/workera, lecz nie są testem na prywatnym produkcyjnym runtime ani jego danych.
- Finalny clean-tree release smoke został wykonany po kanonicznym metadata sync, ale nadal używa wyłącznie syntetycznych/izolowanych danych i nie zastępuje prywatnego acceptance benchmarku.
- Lokalny model wykonał rzeczywistą generację przez bezpośredni adapter. Pole walidacji adaptera nie jest dowodem hostowej finalizacji; tę część sprawdza osobny izolowany package smoke i regresje finalizacji.
- Runtime nie został uznany za aktywny ani zdrowy wyłącznie na podstawie kodu, statusu lub obecności markera.
- PR nie może zostać scalony do `master` bez odrębnej, wyraźnej zgody operatora.

Na obecnym etapie dowiedziono integracji architektonicznej bieżącego wydania oraz zielonych lokalnych bramek statycznych, deterministycznych, restartowych, packagingowych, metadanych i modelowych wymienionych powyżej. Ostateczne stwierdzenie „release-ready” nadal wymaga publikacji PR i zielonego CI.
