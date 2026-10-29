# TPA — wykonanie i granice dowodów (.94.6.15)

TPA uruchamia podtesty w wybranym zewnętrznym Pythonie, poza wątkiem GUI.
Wybierz **Sprawdź gotowość**, zaznacz wiersze i **Uruchom zaznaczone** albo
**Uruchom dostępne automatyczne**. Druga akcja sprawdza cały katalog; brak
zależności blokuje tylko odpowiednie pozycje. Każdy przebieg ma nowy identyfikator.
**Zatrzymaj** anuluje własne wykonanie; **Ponów nieudane / blokady** tworzy nowy
przebieg. Nie ma instalacji pakietów w tle. Studio Zależności otwiera kanoniczny
workflow wymagający podglądu i potwierdzenia instalacji do testowego środowiska.

Tabela pokazuje wynik wykonania, przyczynę i tryb. Szczegóły zawierają kryteria,
polecenie, czas i kod wyjścia. **Pokaż log** wybiera plik wskazanego scenariusza
z wybranego przebiegu. **Otwórz raport** pokazuje czytelny tekst i dane techniczne.
**Eksportuj raport ZIP** tworzy nowy plik z JSON, tekstem, JUnit, logami i jawnie
dołączonymi dowodami tego przebiegu. Nie przeszukuje runtime ani MEMORY.
Uszkodzona historia i błąd zapisu/eksportu są widoczne. Historia wcześniejszej
wersji pozostaje historyczna. Po utracie procesu niedokończone pozycje mają
INTERRUPTED; nie stają się PASS.

## Dwa różne zakresy

`status` opisuje wykonany zakres. `full_gate` opisuje pełny odbiór. Zaliczone
testy jednostkowe nie potwierdzają modelu, EXE offline ani migracji studiów.
JUnit z pominięciami daje SKIPPED, nawet przy kodzie procesu 0. Brak poprawnego
JUnit nie daje PASS. NOT_RUN, QUEUED, RUNNING, PASS, FAIL, SKIPPED, BLOCKED,
CANCELLED, TIMEOUT i INTERRUPTED pozostają oddzielne.

Poniższa mapa jest zaimplementowana w `tpa_catalog.execution_map()` i dołączana
do każdego raportu. Wszystkie wymienione pliki testowe są literalną listą
zatwierdzonych wykonawców; nie są poleceniami odczytanymi z raportu.

| Scenariusz | Wykonany automatyczny zakres / plik `tests/test_…py` | Pełny odbiór i wymagane dowody |
| --- | --- | --- |
| gui-daemon | jazn_run_studio_daemon_routing | Przycisk odbioru izolowanego: kanoniczny start/status, root, wersja, proces, endpoint, heartbeat, conversation_ready; weryfikowany stop |
| ollama-two-turns | jazn_run_studio_chat_contract | Odbiór izolowany: dwie rzeczywiste tury z lokalną Ollamą, losowy kod, jedna sesja, odrębne identyfikatory, display/ACK |
| chat-reconnect | jazn_run_studio_reconnect_acceptance_qt | Odbiór izolowany: rozłączenie własnego transportu i druga tura po ponownym połączeniu, ciągłość kodu i sesji |
| chat-resume | jazn_run_studio_delivery_ack | Odbiór izolowany: przerwanie transportu po send, resume tego samego request_id, brak replay i jedno zaakceptowane zakończenie |
| daemon-restart | heart_system_public_restart | Odbiór izolowany: publiczny restart własnej instancji, nowe instance_id, zachowana sesja i odtworzenie kodu |
| smoke-isolation | package_smoke_workspace_isolation | Syntetyczne sentinele/markery i porównanie przed/po; bez dostępu do operacyjnych markerów |
| config-persistence | jazn_system_root_config | Izolowane Studio Konfiguracji: zapis/reload/previous-profile, priorytety i konflikt CAS; raport obserwacji |
| studios-parity | jazn_run_studio_12_manual_studio_gates | 12 odrębnych odbiorów tej samej wersji i SHA oraz macierz STUDIO_MIGRATION; katalog nie jest migracją |
| offline-exe | jazn_run_studio_bundle_integrity | Prowadzona procedura Windows VM offline; wydany onedir, SHA/BUILD_INFO/manifest, logi i raport człowieka. Brak EXE/VM = NOT_RUN/BLOCKED |
| ui-accessibility | jazn_run_studio_workbench_qt | Izolowane widoczne Studio: klawiatura, 860×580, motywy i DPI; raport ze skalą i identyfikacją zrzutów |
| studio-system | jazn_operator_studio | Izolowane Studio → Developer; porównanie aktualizacji/audytów/ustawień i odmów |
| studio-start | jazn_start_studio_dashboard | Izolowane Studio → Usługi i procesy; katalog, własność, gotowość i logi |
| studio-configuration | jazn_run_studio_configuration_native_qt | Izolowane Studio → Konfiguracja Qt; mapa, preview/save/restore, błędy i ochrona szkicu |
| studio-memory | memory_studio_step_workflows | Izolowane Studio → Dowody MEMORY; syntetyczny projekt, źródła, role, kandydaci, afekt, protokół |
| studio-memory-rebuild | memory_rebuild_p0_studio | Izolowane Studio → Memory Rebuild; plan/walidacja/rebuild/eksport i anulowanie na własnym projekcie |
| studio-test-studio | tests_studio_run_history_p1 | Izolowane Studio → Katalog testów; recenzje, selekcja, wykonanie/anulowanie i historia |
| studio-generator | jazn_pack_generator_studio_portability | Izolowane Studio → Generator paczek; inputs/ → outputs/, plan/pack/verify/split/join i błąd części |
| studio-dependencies | dependency_studio_repeated_profiles | Izolowane Studio → Studio Zależności; inspect/verify lock/wheelhouse, potwierdzona instalacja do własnego venv |
| studio-python-runtime | jazn_run_studio_integrations | Izolowane Studio → Python Runtime; detect-host, inwentarz i błąd interpretera/pakietu |
| studio-version-rebuild | jazn_run_studio_version_native_qt | Izolowane Studio → Wersje Qt; AST, preview/backup/diff/sync/rollback w porównaniu z pierwotnym narzędziem |
| studio-chat-import | memory_studio_step_workflows | Izolowane Studio → Memory; syntetyczne źródło, plan/import/verify, tożsamość, kolejka i wyszukiwanie |
| studio-memory-restore | memory_restore_tool | Izolowane Studio → Memory; własny baseline/scan/plan/backup/restore/compare z potwierdzeniem |

Każdy wiersz ma własną checklistę, kryteria i ograniczenia. **Otwórz izolowane
Studio** przygotowuje świeży, zweryfikowany staging, osobny profil i port,
MEMORY off, pliki `inputs/source.txt`, `inputs/invalid.json`, pusty `outputs/`
i `PROCEDURA.txt`. Otwiera rzeczywisty interfejs na odpowiedniej stronie.
Utworzenie projektu/bazy odbywa się przez publiczne narzędzia w tym obszarze.
Samo otwarcie/zamknięcie okna nigdy nie zalicza pełnego scenariusza.

Odbiór rozmowy wymaga istniejącego modelu na lokalnej Ollamie. TPA nie uruchamia
ani nie pobiera usługi/modelu automatycznie. Klient używa wyłącznie kanonicznych
Controller/ChatClient i ich walidatora finalizacji. Przed ACK tekst trafia do
widoku TPA; tekst zmieniony redakcją nie otrzymuje ACK `display_exact` oryginału.
Sprzątanie wymaga zgodnej tożsamości własnego stagingu. W razie niepewności
raport ma BLOCKED i zachowuje dowód właściciela zamiast zatrzymywać obcy PID.

Pełna parzystość Qt nie jest zakończona. Brak natywnego przepływu importu,
restore lub innej funkcji należy zapisać jako brak; klasyczne okno nie zastępuje
natywnego odbioru. PASS człowieka wymaga checklisty, obserwacji i dowodu z tego
przebiegu; dla studiów także wykonania w izolowanym Studio, dla EXE/DPI osobnego
raportu człowieka. Wszystkie obserwacje są zachowywane oddzielnie.

## Powtarzalne dowody GUI

`python -X utf8 -m tools.jazn_run_studio.tpa_smoke --output NOWY_KATALOG_POZA_SYSTEM`
otwiera rzeczywiste okno Windows, wykonuje cały katalog, zapisuje PNG,
`smoke.json`, przykładowy JSON oraz ZIP. Wariant `--live --case CASE --model MODEL`
sprawdza rzeczywisty odbiór. Offscreen wymaga jawnego
`--expected-platform offscreen` i jest osobnym dowodem. `QT_SCALE_FACTOR=1.5`
pozwala powtórzyć natywny rendering Qt przy skali 150%; nie zastępuje oceny
człowieka ani zmiany DPI monitora. `smoke.json` podaje rzeczywistą platformę,
DPR, rozmiar minimalnego okna, liczbę zdarzeń timera i wyniki. Sam kod wyjścia
helpera oznacza wykonanie smoke, nie pełne zaliczenie katalogu.
