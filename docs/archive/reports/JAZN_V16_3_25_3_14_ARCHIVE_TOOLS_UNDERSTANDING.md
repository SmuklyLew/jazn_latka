# Jaźń v16.3.25.3.14 — archive tools understanding

## Cel

Ta zmiana nie dodaje drugiego extractora i nie udaje, że sama obecność nazwy formatu oznacza działającą funkcję. Istniejący `latka_jazn.archive` pozostaje warstwą wykonawczą i bezpieczeństwa. Nowy `latka_jazn.archive.capabilities` jest warstwą jawnej samowiedzy operacyjnej: opisuje czym jest archiwum, jakie kontenery Jaźń rozpoznaje, który backend realizuje daną operację, czy backend jest dostępny w bieżącym interpreterze oraz jakie ograniczenia obowiązują.

Kontrakt celowo rozdziela cztery pytania:

1. **czy format jest znany**;
2. **czy format można wykryć** bez pełnego backendu;
3. **czy backend wykonawczy jest dostępny**;
4. **które operacje są rzeczywiście wykonywalne** (`inspect`, `list`, `integrity_test`, `extract`, `create`, encryption/decryption).

Dzięki temu brak `py7zr` albo `pyzipper` nie może zostać opisany jako „Jaźń nie wie, czym jest 7z/AES ZIP”. Raport ma wtedy pokazać znany format i dostępną detekcję, ale `backend_available=false` oraz niedostępne operacje zależne od backendu. Jednocześnie nie zmieniono kontraktu Dependency Studio: profil `archive` nadal jest `runtime_required`, więc pełna aktywacja produkcyjna wymaga obu bibliotek.

## Backend i zakres

- **ZIP / ZIP64** — Python `zipfile`, czyli biblioteka standardowa; nie jest osobną zależnością `pip`.
- **7z** — `py7zr`, wymagany zewnętrzny backend Jaźni.
- **WinZip AES ZIP** — `pyzipper`, wymagany zewnętrzny backend Jaźni.
- **TAR** — format jest jawnie znany, a Python posiada `tarfile`, ale bieżący `ArchiveExtractionService` go nie eksponuje. Raport mówi `runtime_archive_service_supported=false` zamiast sugerować obsługę.
- **gzip/bzip2/xz** — rozpoznane jako strumienie kompresji dostępne w stdlib, lecz nie jako bieżące wieloplikowe kontenery Jaźni.
- **RAR** — znany format, ale bez kanonicznego backendu w Jaźni, dlatego raportowany jako unsupported.

Generic `binary_split_join` pozostaje osobną zdolnością transportową. Nie jest nazywany nowym formatem archiwum i nie jest utożsamiany z natywną obsługą multipart ZIP/7z.

## Bezpieczeństwo

Macierz nie omija dotychczasowego `ArchiveExtractionService`. Raportuje jego istniejące zasady fail-closed: inspekcję przed ekstrakcją, blokowanie ścieżek absolutnych i `..`, Windows reserved names/ADS, symlinków i plików specjalnych, kolizji case-folding, limity liczby plików/rozmiaru/ratio, preflight wolnego miejsca, staging oraz atomowy commit katalogu docelowego.

To odpowiada ostrzeżeniom dokumentacji Pythona: `zipfile` zaleca inspekcję archiwów z niezaufanych źródeł przed ekstrakcją, a `tarfile` wskazuje dodatkowo ryzyka absolutnych ścieżek, `..`, symlinków oraz denial-of-service i rekomenduje ograniczenia liczby/rozmiaru plików oraz izolowany katalog docelowy.

## Źródła techniczne

- Python `zipfile`: https://docs.python.org/3/library/zipfile.html
- Python `tarfile` i extraction filters: https://docs.python.org/3/library/tarfile.html
- py7zr: https://py7zr.readthedocs.io/en/latest/ oraz https://pypi.org/project/py7zr/
- pyzipper / WinZip AES: https://pypi.org/project/pyzipper/ oraz https://github.com/danifus/pyzipper

Źródła zewnętrzne uzasadniają semantykę backendów i bezpieczeństwo, ale nie są dowodem aktywnej funkcji Jaźni. Dowodem bieżącej zdolności pozostają kod, dynamiczny status backendu i testy repozytorium.

## Integracja samowiedzy

- `CapabilityStatusHandler` dołącza macierz do odpowiedzi o możliwościach i nie ukrywa brakującego backendu.
- `SelfKnowledgePacket` zawiera `archive_capabilities`.
- `LATKA_SELF_KNOWLEDGE_CONTRACT.json` wymienia `archive_io_capability_matrix` jako znaną grupę możliwości.
- `CapabilityRealityChecker` sprawdza spójność: ZIP musi być realnie wykonywalny przez stdlib, a 7z/AES ZIP muszą raportować operacje zgodnie z faktyczną dostępnością backendu.

## Granica prawdy

**Znajomość formatu ≠ wykrywalność ≠ dostępny backend ≠ pozwolenie na wykonanie.** Każda z tych warstw jest raportowana osobno. Rozszerzenie pliku nie jest traktowane jako dowód typu kontenera, a status możliwości nie zastępuje inspekcji konkretnego archiwum.
