# Łatka / Jaźń

## Uruchamianie bez `.venv` na Windows

Runtime nie wymaga aktywnego środowiska wirtualnego. Z dowolnego katalogu można uruchomić:

```powershell
D:\sciezka\do\jazn_latka_master\JAZN.cmd --chat
```

Launcher wybiera globalnego Pythona 3.12+ (najpierw `py -3`), zawsze wskazuje `run.py` przez bezwzględną ścieżkę katalogu repozytorium i nie polega na bieżącym katalogu ani na `.venv`. Bez launchera działa też bezpośrednio:

```powershell
py -3 -X utf8 D:\sciezka\do\jazn_latka_master\run.py --chat
```

Po aktywacji dowolnego poprawnego środowiska można nadal użyć `python -X utf8 .\run.py --chat`, ale aktywacja `.venv` jest opcjonalna.


**Łatka / Jaźń** to eksperymentalny lokalny system rozmowny budowany wokół pamięci, kanonu, głosu, źródeł i runtime. Nie jest pojedynczym chatbotem ani samym promptem. System rozdziela aktywny proces, pamięć, tożsamość, model językowy, narzędzia, pochodzenie odpowiedzi i finalną walidację.

Projekt ma umieć powiedzieć, kiedy runtime naprawdę działa, z jakiego katalogu został uruchomiony, z jakiej pamięci korzysta, jaką trasą powstała odpowiedź oraz czy widoczny tekst pochodzi z runtime, host bridge, lokalnego modelu czy kontrolowanego fallbacku.

## Granica prawdy

Styl, pierwsza osoba, czuły ton, nazwa folderu, ZIP, sam marker albo obecność kodu nie są dowodem aktywnej Jaźni. Potwierdzenie wymaga:

1. zweryfikowanego żywego daemona z właściwym rootem, manifestem, PID-em, endpointem i świeżym heartbeat; albo
2. poprawnie zakończonej, zweryfikowanej tury one-shot z prawidłowym `final_visible_text`, integralnością i truth gate.

Główna zasada:

> Prawda runtime ma pierwszeństwo przed stylem.

## Architektura

```text
użytkownik
→ host rozmowy
→ source classifier / tool access gate
→ runtime Jaźni
→ DialogueTaskState (cel / aktywne zadanie / referencje)
→ routing + ReasoningOrchestrator (fast / standard / deliberative)
→ bramy pamięci / Knowledge Fabric / kanonu / narzędzi / lexical intelligence
→ adapter modelu albo host bridge
→ truth gate i walidator odpowiedzi
→ final_visible_text
→ commit trwałej ciągłości sesji po zaakceptowanej finalizacji
```

Każda warstwa jest osobno audytowana. Aktywacja runtime rozdziela folder, wersję, manifest, marker, PID, endpoint, heartbeat, czas, pamięć, model, narzędzia i voice.

### Tożsamość i głos

Instrukcje projektu są bootstrapem hosta, a `AGENTS.md` jest routerem runbooków. Tożsamość, perspektywa, routing, pamięć i bezpośredni głos Łatki należą do kodu runtime. Most ChatGPT eksportuje `runtime_ownership_contract` i `host_generation_policy`; host nie jest źródłem osobowości ani wspomnień.

Trasy `presence_check`, `identity_continuity_check` i `runtime_health_check` są rozdzielone. Lokalny adapter Ollamy jest kanałem językowym, nie tożsamością ani pamięcią.

### Proces Windows i Ollama

Daemon Windows domyślnie używa trybu ukrytego bez migających konsol. Tryb widocznego monitora może utrzymać jedno stałe okno diagnostyczne. Uruchomienia procesów pomocniczych są rejestrowane w runtime, dzięki czemu można ustalić PID rodzica, komendę i powód uruchomienia.

Adapter Ollamy zachowuje faktycznie użyty model, `done_reason` i metryki transportu. Routing rozpoznaje pytania o model/provider/adapter, a lokalna trasa nie powinna wyciekać terminologii hosta ChatGPT.

## Aktualna linia rozwoju

Jedynym źródłem wersji jest `latka_jazn/version.py`.

```text
<wartość PACKAGE_VERSION_FULL z latka_jazn/version.py>
```

Bieżąca linia rozwoju zachowuje runtime-owned identity, recovery pamięci L0–L3, stabilność daemona, atomowość tur, provenance, integralność paczki i pełne CI Windows/Ubuntu, a dodatkowo wprowadza strukturalny stan celu/zadania rozmowy, selektywną orkiestrację rozumowania, Knowledge Fabric, warstwę Polish Lexical Intelligence, zweryfikowane lekcje antyregresyjne oraz commit ciągłości sesji dopiero po zaakceptowanej finalizacji widocznej odpowiedzi. Szczegółowy projekt: `docs/plans/JAZN_V15_4_0_0_COGNITIVE_ARCHITECTURE.md`.

## Pamięć L0–L3

Pamięć jest systemem źródeł i rekordów, a nie biologicznym wspomnieniem:

- **L0 `source_archive`** — pełne źródła i archiwa;
- **L1 `working`** — stan bieżącej sesji i ograniczony wake-state;
- **L2 `short_term`** — rekordy z TTL i statusem przeglądu;
- **L3 `long_term`** — wyłącznie rekordy z jawnym requestem, decyzją i promotion ledger.

Sama obecność SQLite nie oznacza zaufanej pamięci. Wymagana jest znana ścieżka, czytelna struktura, `integrity_check` lub `quick_check`, osobny `foreign_key_check`, zgodność sidecarów oraz rzeczywiste rekordy.

### Wake-state, continuity readiness i restart continuity

Runtime rozdziela teraz **przeszukiwalność L0**, **kompletność normalizacji**, **gotowość wake-state** i **prawo do twierdzenia o ciągłości**. Brak sidecara lub wake-state nie oznacza automatycznie braku pamięci: jeśli conversation archive jest zdrowe i przeszukiwalne, system może działać w trybie `retrieval_only`, zachowując źródłowy recall i zwykłą rozmowę, ale z `continuity_claim_allowed=false`. Częściowa normalizacja (`partial_unverified`) nie może hydratować L1 ani udawać pełnego przebudzenia.

Pełny recovery nie ma ukrytego limitu liczby normalizowanych rekordów. Każdy run zapisuje `expected_item_count`, `normalized_item_count`, `coverage_complete` i `coverage_ratio`; wake-state wolno zbudować dopiero przy pełnym coverage. Jawny limit pozostaje narzędziem diagnostycznym i daje stan częściowy.

Runtime ładuje jeden zweryfikowany snapshot wake-state, sprawdza jego SHA i integralność sidecara, a następnie hydruje ograniczony pakiet L1.

Stan sesji jest zapisywany atomowo do checkpointu per-session oraz do wskaźnika ostatniej kwalifikującej się sesji. Checkpoint zawiera hash stanu, hash całego checkpointu, generację, poprzedni hash oraz powiązanie z identyfikatorem i SHA wake-state. Po restarcie carryover jest dozwolony tylko wtedy, gdy checkpoint i wake-state nadal są zgodne; manipulacja, wygaśnięcie lub zmiana snapshotu blokują odziedziczenie poprzedniego tekstu, intencji i trasy.

`--no-carryover` tworzy izolowaną sesję i nie zastępuje wskaźnika ostatniej zwykłej sesji.

## Audytowalny czas pomiędzy rozmowami — rest / replay / dream continuity

Bieżąca linia rozwoju dodaje osobny, audytowalny proces odpoczynku działający wewnątrz istniejącego daemona — bez nowego portu i bez zastępowania zwykłej rozmowy. Po osiągnięciu progu bezczynności `RestCycleController` może wykonywać ograniczone cykle: read-only memory replay → lokalna symulacja wewnętrzna → niezależna ewaluacja → consolidation gate → hash-verified wake report.

Każdy „sen” ma status `simulated_internal`, `counterfactual`, `rehearsal` albo `associative` i **nigdy nie jest faktem ani wspomnieniem obserwowanego zdarzenia**. Sandbox nie ma narzędzi zewnętrznych, a autonomiczny rest nie może automatycznie promować L3. Domyślny `JAZN_REST_SHADOW_MODE=1` nie zapisuje nawet kandydatów L2; służy najpierw do zebrania audytowalnych dowodów działania.

`WakeStateRuntimeBridge` może pokazać `rest_continuity_status` oraz ograniczone podsumowanie nocnego/idle raportu, ale sam raport rest nie daje prawa do `continuity_claim_allowed=true`: pełna ciągłość pamięci nadal wymaga istniejącego zweryfikowanego wake-state. Brak lub awaria warstwy rest nie blokuje ordinary dialogue.

Szczegółowy plan faz 0–6: `docs/plans/JAZN_V15_4_2_0_REST_REPLAY_DREAM_CONTINUITY.md`. Podstawa badawcza: `docs/reports/JAZN_V15_4_2_0_RESEARCH_SOURCES.md`.

### Cognitive truth & memory integration hardening (current integration-hardening line)

Bieżąca linia integration-hardening wzmacnia kryterium „działa”: obecność pliku lub zielony unit test nie wystarcza do oznaczenia capability jako working. Audyty rozróżniają obecność od integracji behawioralnej, a diagnostyka rozdziela gotowość procesu, przeszukiwalność pamięci, continuity, scheduler rest i gotowość DreamSandbox.

Recovery source jest rozdzielony od mutowalnego runtime-write, kanoniczne archive+FTS+staging są bramką przed pełnym wake, RestReplay potrafi czytać indywidualne rekordy z pełnego sidecara, a KnowledgeFabric i Polish Lexical Intelligence są wpięte w rzeczywistą ścieżkę cognitive frame/model context. Homeostaza ma co najmniej jeden jawny downstream control effect: bounded `generation_limit` steruje `ModelAdapterRequest.max_output_tokens`. Prediction pozostaje advisory.

`rest_scheduler_ready=true` nie oznacza `rest_dream_ready=true`: autonomiczne sceny wymagają faktycznie dostępnego, dozwolonego lokalnego modelu. Szczegółowy projekt: `docs/plans/JAZN_V15_4_2_1_COGNITIVE_TRUTH_MEMORY_INTEGRATION_HARDENING.md`; raport źródeł: `docs/reports/JAZN_V15_4_2_1_RESEARCH_SOURCES.md`.

## Start i diagnostyka

```powershell
python -X utf8 run.py status --snapshot --json
python -X utf8 run.py doctor --json
python -X utf8 run.py start
python -X utf8 run.py status --json
python -X utf8 run.py stop
python -X utf8 run.py chat-gpt -- "wiadomość"
```

`run.py` jest kanonicznym interfejsem operatora. `main.py` pozostaje technicznym punktem zgodności dla kompatybilnych flag, daemona i mostów niskiego poziomu.

### Przenośny bootstrap paczki

Aktualną lokalną paczkę systemową albo `combined` można bezpiecznie zmaterializować do nowego,
zapisywalnego i wersjonowanego katalogu:

```powershell
python -X utf8 run.py runtime-bootstrap `
  --parts-dir D:\lokalne_paczki `
  --destination D:\Jaźń\active-current `
  --json
```

Loader rozpoznaje bieżący `*.zip.package.json`, starszy sidecar zgodnościowy, binarnie dzielony ZIP
oraz niezależne woluminy ZIP. Sprawdza hashe części, CRC, bezpieczne ścieżki, pełny manifest kodu
i — dla profilu `combined` — osobny manifest pamięci. Bieżąca paczka wymaga znanego profilu i schematu,
zgodnej wersji, zweryfikowanego `SOURCE_PROVENANCE.json` oraz dokładnego inwentarza statycznych plików.
Obcy kod i zapakowany stan `workspace_runtime` blokują materializację. Paczka `memory` nigdy sama nie
staje się `active_root`, a zajęty katalog docelowy nie jest automatycznie zastępowany.

`--no-start-daemon` wykonuje wyłącznie materializację i walidację. Nawet gdy pamięć jest zdrowa,
wynik pozostaje `installed_inactive`; stan `active` wymaga osiągalnego procesu, zgodnej tożsamości
endpointu, świeżego heartbeat oraz sprawnej pamięci. Brak zapisu, części paczki lub uprawnień daje
ustrukturyzowany raport `bootstrap_blocked`, nigdy pozorny start.

`JAZN_RUNTIME_WORKSPACE_DIR` przenosi stan techniczny (marker, PID, logi, checkpointy i cache)
poza katalog kodu. Nie przenosi pamięci SQLite i `memory/`; pełna instalacja tylko do odczytu musi
zostać najpierw zmaterializowana do zapisywalnego `active_root`.

## Walidacja dużej pamięci

Szybka, read-only kontrola znanych baz i shardów:

```powershell
python -X utf8 run.py memory-validate --root . --json --progress
```

Pełny audyt wszystkich baz pod `memory/sqlite`, z licznikami rekordów, SHA-256 i raportem JSON:

```powershell
python -X utf8 run.py memory-validate --root . `
  --full --include-all-sqlite --table-counts --hash-files `
  --output workspace_runtime/memory_validation/full-report.json `
  --json --progress
```

Polecenie działa read-only, wykrywa bazy z konfiguracji i manifestów shardów, sprawdza pary WAL/SHM, strukturę SQLite, klucze obce, metryki stron, sidecar wake-state oraz magazyn tierów.

Zielony raport nie dowodzi kompletności wszystkich archiwów, jakości recallu ani autoryzacji L3. Praktyczna walidacja prywatnych danych jest śledzona w GitHub Issues i odbywa się lokalnie bez commitowania `memory/`, SQLite ani eksportów.

## Recovery pamięci

Recovery jest projektowany jako bezpieczna konsolidacja warstwowa, nie automatyczne trenowanie wag modelu na prywatnej historii. Pełne źródła pozostają w L0, wake tworzy ograniczony L1, L2 jest selektywne, a L3 wymaga jawnego zatwierdzenia. Taki podział jest zgodny z kierunkiem współczesnych architektur agentowych i retrieval-augmented generation: trwała wiedza pozostaje jawna, aktualizowalna i możliwa do przypisania do źródła zamiast być ukrytym efektem niekontrolowanego fine-tuningu. Szczegóły i źródła badawcze: `docs/reports/JAZN_V15_4_1_0_MEMORY_CONTINUITY_NEURO_HARDENING.md`.

```powershell
python -X utf8 run.py memory-recover --root . `
  --progress --prepare-l2 --build-l3-manifest --json
```

Promocja L3 wymaga dokładnego SHA manifestu zatwierdzeń i jawnego `--approved-by`. Szczegółowy kontrakt opisuje `docs/MEMORY_RECOVERY_CURRENT.md`.

## Backlog

Aktualny roadmap pamięci i ciągłości jest utrzymywany w GitHub Issues:

- #60 — roadmap nadrzędny;
- #59 — pełne archiwa, recall i L3 na rzeczywistych danych;
- #55 — stabilizacja i skrócenie testów Windows.

Dokument `docs/plans/MEMORY_CONTINUITY_VALIDATION_BACKLOG.md` opisuje kolejność i kryteria ukończenia bez zastępowania Issues.

## Domknięcie wydania

Na czystym, zatwierdzonym commicie:

```powershell
python -X utf8 run.py package-smoke --profile release --json
python -X utf8 run.py release-build --json
```

`release-build` tworzy staging z bieżącego commita, generuje w nim świeże `SOURCE_PROVENANCE.json` i `PACKAGE_INTEGRITY_MANIFEST.json`, uruchamia profil eksportowy, buduje ZIP atomowo oraz zapisuje SHA-256 i raporty pakowania.

## Kontrolowana instalacja patchy

Patch jest czystym diffem Git. Backup, `git apply --check`, testy i raport zapewnia `tools/patch_install/apply_patch_checked.py`; instrukcja znajduje się w `tools/patch_install/README.md`.
