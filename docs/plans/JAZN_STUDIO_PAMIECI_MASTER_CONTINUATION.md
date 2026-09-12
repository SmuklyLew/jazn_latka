# Jaźń Studio Pamięci — kontynuacja po przeniesieniu na aktualny master

## Stan brancha

Branch kontynuacyjny: `fix/jazn-studio-pameci`.

Punkt bazowy: `master` @ `5842b4b24d2b073293865a6ec99a76e6be9c0fcb`.

Aktualizacja zachowuje współczesną linię systemu i podnosi wersję do:

`16.3.25.5.71-jazn-studio-pamieci-master-convergence`

Nie jest to merge starego brancha `codex/jazn-studio-pamieci`. Funkcjonalne zmiany Studia zostały przeniesione na świeży master, aby nie cofać nowszego host lifecycle, finalization, Test Studio ani pozostałych zmian systemu.

## Przeniesiony kod funkcjonalny

Na aktualny master przeniesiono:

- `docs/tools/JAZN_STUDIO_PAMIECI.md`;
- `tools/jazn_memory_studio.py`;
- `latka_jazn/tools/memory_rebuild_app/memory_studio.py`;
- `latka_jazn/tools/memory_rebuild_app/studio_audit.py`;
- `latka_jazn/tools/memory_rebuild_app/studio_links.py`;
- `latka_jazn/tools/memory_rebuild_app/studio_repair.py`;
- integrację `memory-studio` w `entrypoint.py`;
- rozszerzoną obsługę źródeł w `adapters/music_analysis.py`;
- poprawkę zachowania kolejności source inventory w `run_manifest.py`;
- korelację pól ASCII `tresc` oraz byte-level `source_sha256` / `source_size_bytes` z ostatniej poprawki starego brancha.

`ProtocolEngine` i `UnifiedMemoryDatabase`, na których opiera się Studio, mają na aktualnym master te same blob SHA co na bazie implementacji Studia, więc nie zastępowano ich starszymi kopiami.

## Celowo nieprzeniesione elementy starego brancha

Nie przenoszono:

- starego `latka_jazn/version.py` z v16.3.25.5.67;
- starych `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json`;
- zmian aktywnego testu v16.3.25.5.66, który w aktualnym master nie jest już aktywnym plikiem;
- commitów `chore(release)` starego brancha.

Metadane integralności/provenance mają być generowane wyłącznie kanonicznym workflow repozytorium.

## Testy Studia do ponownego włączenia na aktualnej polityce testów

Stary branch zawiera trzy istotne aktywne pliki testowe:

- `tests/test_jazn_memory_studio.py`;
- `tests/test_memory_manifest_inventory_order.py` — używać wersji z jawnymi argumentami `RunManifest.begin(...)`, bez `**identity`;
- `tests/test_memory_studio_correlation_fields.py`.

Nie zostały skopiowane bezpośrednio, ponieważ aktualny master wymaga, aby każda aktywna definicja testowa była obecna w `tools/jazn_tests_studio/test_contracts.json`. Przy wznowieniu pracy należy dodać te testy na nowym branchu, uruchomić aktualny migrator/katalogowanie Jaźń - Studio Testów i dopiero wtedy zatwierdzić zmianę testową. Nie przywracać historycznego aktywnego testu v66.

## Stan prywatnej przebudowy do wznowienia

Zgodnie z zapisanym stanem operatora:

- `private-acceptance-02` Test00 jest PASS i nie należy go powtarzać;
- Test01 został przerwany podczas budowy i jego częściowa baza/WAL/SHM nie jest gotową bazą;
- przed wznowieniem Test01 trzeba sprawdzić zachowanie istniejącego celu/stagingu w `_build_fresh_database`, a przerwany staging jawnie zarchiwizować lub przenieść po weryfikacji ścieżki;
- zachować ten sam run ID i artefakty poprawnego Test00;
- Test02, Test03, rzeczywisty Test04 i Final nie zostały jeszcze wykonane;
- benchmark Test04 wymaga przygotowania znaczących, source-grounded przypadków recall;
- package-smoke oraz końcowy protocol/CI trzeba wykonać ponownie po integracji testów.

Nie commitować prywatnych eksportów, baz SQLite/WAL/SHM, konfiguracji operatora ani wyników zawierających prywatną pamięć.

## Kolejność wznowienia Codexa

1. Przełączyć się na `fix/jazn-studio-pameci` i potwierdzić aktualny HEAD oraz czyste drzewo.
2. Wczytać `AGENTS.md` i `AGENTS.codex.md`.
3. Dodać trzy testy Studia z powyższej listy i zsynchronizować aktualny katalog Test Studio zgodnie z `tests/TESTING_POLICY.md`.
4. Uruchomić testy ukierunkowane oraz Pyright; nie deklarować wcześniejszych wyników ze starego brancha jako wyników nowej bazy.
5. Uruchomić pełny wymagany zestaw testów/compileall/audyty zgodnie z aktualnym master.
6. Sprawdzić przerwany staging Test01 i wznowić `private-acceptance-02` bez powtarzania Test00.
7. Kontynuować Test02 → Test03 → przygotowany realny Test04 → Final.
8. Dokończyć package-smoke i wymagane CI.
9. Nie scalać do `master` bez osobnej autoryzacji użytkownika.

## Granica deklaracji

Ten branch jest bazą kontynuacyjną po konwergencji ze współczesnym master. Samo przeniesienie kodu nie jest jeszcze deklaracją pełnego release candidate ani ukończenia prywatnej rekonstrukcji pamięci.
