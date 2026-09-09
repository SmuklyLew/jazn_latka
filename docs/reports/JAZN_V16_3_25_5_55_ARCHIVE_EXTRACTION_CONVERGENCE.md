# Jaźń v16.3.25.5.55 — archive extraction convergence

## Cel

Ta aktualizacja zamyka klasę problemów, w której poprawne archiwum albo poprawny zestaw części był obecny na hoście, ale fizyczne nazwy plików po materializacji transportowej różniły się od nazw zapisanych w manifeście (np. `payload.zip(1).001` zamiast `payload.zip.001`). Celem jest rozdzielenie integralności **logicznej paczki** od nazwy **fizycznego artefaktu transportowego**, bez obniżania fail-closed bezpieczeństwa.

Granica platformy pozostaje jawna: jeżeli host nie potrafi utworzyć żadnego lokalnego procesu, kod archiwów nie może fizycznie wykonać ekstrakcji. Gdy istnieje działający executor i dane są dostępne, warstwa archiwów ma sama rozpoznać poprawną drogę i nie traktować rename'u transportowego jako uszkodzenia paczki.

## Główna przyczyna

Manifest `jazn_package_set/v2` przechowuje kanoniczne `outputs[].filename`, rozmiary i SHA-256. Host ChatGPT może jednak zmaterializować ponownie przesłany plik z sufiksem kopii, np.:

- `archive.zip.001` -> `archive.zip(1).001`,
- `archive.zip.package.json` -> `archive.zip.package(1).json`.

Poprzednia ścieżka `ArchiveExtractionService` budowała fizyczny path bezpośrednio jako `parent / outputs[].filename`. W rezultacie kompletna, poprawna kryptograficznie paczka mogła zostać sklasyfikowana jako brakująca wyłącznie dlatego, że warstwa transportu zmieniła nazwę pliku.

## Zmiany

### 1. Transport-renamed package outputs

`latka_jazn/archive/transport_convergence.py`, dołączony przez `hardened_service.py`, rozdziela teraz nazwę logiczną od materializowanej ścieżki bez przepisywania stabilnego bazowego `archive/service.py`:

1. dokładna nazwa z manifestu ma pierwszeństwo;
2. jeżeli jej nie ma, kandydaci są ograniczeni limitem i filtrowani przez znormalizowany hint nazwy transportowej;
3. rozmiar musi być identyczny z manifestem;
4. SHA-256 musi być identyczny z manifestem;
5. jeden fizyczny plik nie może zostać użyty dla dwóch logicznych outputów;
6. dwa poprawne kryptograficznie aliasy są błędem `package_output_transport_alias_ambiguous`, a nie losowym wyborem;
7. `package_set_sha256` nadal jest liczony z **kanonicznych nazw z manifestu**, a nie z nazw transportowych.

Jeżeli dokładny logiczny plik istnieje, ale ma zły hash, resolver nie omija go przez znalezienie poprawnego aliasu. Taki przypadek pozostaje błędem integralności.

### 2. Discovery przemianowanego sidecara

Sidecar może być rozpoznany przez wspierany schema contract nawet wtedy, gdy host zmienił jego nazwę. Dla wejścia będącego częścią split setu discovery:

- preferuje exact/canonical sidecar,
- następnie dopasowanie znormalizowanej nazwy `(N)`,
- ostatecznie może powiązać sidecar z konkretną częścią wyłącznie przez zgodny rozmiar i SHA-256 zapisany w `outputs[]`.

Ambiguitet zawsze kończy się fail-closed.

### 3. Stabilna tożsamość pliku

Hashowanie outputów i join części porównują tożsamość pliku przed otwarciem, na otwartym descriptorze i po odczycie (`device`, `inode`, `size`, `mtime_ns`). Zmiana lub podmiana pliku w trakcie odczytu jest klasyfikowana jako `package_input_not_ready`.

Join nie ufa samemu wcześniejszemu hash checkowi: każda część jest ponownie kontrolowana na otwartym descriptorze podczas faktycznego składania archiwum.

### 4. RAR w kanonicznym ArchiveExtractionService

RAR3/RAR5 jest teraz rozpoznawany po sygnaturze i routowany przez jeden kanoniczny serwis ekstrakcji. `rar_backend.py` wykonuje:

- walidację wpisów przed ekstrakcją,
- odrzucenie symlinków i special files,
- normalizację i containment target path,
- strumieniowe kopiowanie członków do prywatnego stagingu,
- limity per-member i total podczas zapisu,
- kontrolę rzeczywistej liczby zapisanych bajtów,
- atomowe zatwierdzenie destination.

`rarfile` pozostaje read-only; tworzenie RAR nie jest deklarowane jako capability runtime.

### 5. Minimalne bezpieczne wersje backendów

Aktualizacja nie akceptuje samego faktu importowalności biblioteki:

- `py7zr >= 1.1.3` — wersja 1.1.3 naprawia path traversal, O(n²) DoS i decompression bomb oraz dodaje `max_extract_size`;
- `rarfile >= 4.5` — linia 4.3–4.5 zawiera kolejne security hardening, a 4.5 naprawia m.in. nadmierne komentarze i NUL w nazwach.

7z przekazuje `max_extract_size` zgodny z `ArchiveSecurityLimits.max_total_uncompressed_bytes` zarówno do inspekcji, jak i ekstrakcji. Bazowy `archive/service.py` pozostaje niezmieniony; aktywny publiczny `ArchiveExtractionService` składa tę funkcjonalność przez `ArchiveTransportConvergenceMixin` + `ArchiveBackendConvergenceMixin` + dotychczasowy bazowy service. Logika backendów 7z/RAR znajduje się w `latka_jazn/archive/backend_convergence.py`.

## Zachowany kontrakt bezpieczeństwa

Nadal obowiązują:

- inspect-before-extract,
- odrzucenie absolute paths i `..`,
- odrzucenie nazw niebezpiecznych dla Windows/ADS,
- odrzucenie symlinków/special files,
- casefold collision guard,
- limit liczby członków,
- limit pojedynczego pliku,
- limit sumy rozpakowanych bajtów,
- compression ratio limit,
- free-space preflight,
- staging przed commit,
- atomowe zatwierdzenie destination,
- brak utrwalania haseł.

ZIP nadal jest stdlib-first i nie potrzebuje opcjonalnego dependency. Standalone system ZIP bootstrap v54 pozostaje osobną warstwą przed dostępnością operatora `run.py`.

## Testy regresji v55

Nowy `tests/test_v16325555_archive_extraction_convergence.py` sprawdza m.in.:

- pełny roundtrip split ZIP po rename `...(1).001` + `...package(1).json`;
- direct use przemianowanego sidecara;
- fail-closed przy dwóch poprawnych aliasach;
- zakaz omijania błędnego exact outputu przez alias;
- RAR3/RAR5 aliases i signature detection;
- routing RAR przez kanoniczny backend;
- odrzucenie `py7zr 1.1.2`;
- odrzucenie `rarfile 4.2`;
- capability truth dla transport alias resolution i minimum safe backend versions;
- identity release `16.3.25.5.55-archive-extraction-convergence`.

Na lokalnym workspace zmienione moduły archiwów są bajtowo oparte o te same bloby co świeży `master` v54. Wykonane przed publikacją brancha:

- `python -m compileall -q latka_jazn tests main.py run.py CHATGPT_BOOTSTRAP.py` — PASS;
- nowy zestaw v55 — 10 passed;
- rozszerzony zestaw archive/plugin/generator/resource-limit — 36 passed;
- realny probe nazwy załącznika `jazn_latka_v15.0.3.222-RUN-HOTFIX_memory.zip(1).001` poprawnie odnalazł `...zip.package(1).json` bez joinu dużej paczki.

Dodatkowo na czystej, zweryfikowanej paczce systemowej v54 (`SHA-256 9f9c5b84e78180fa7cf951960c8d424ea96039892d5919e4d3890c3c0df02955`) nałożono wyłącznie 9 plików v55 i wykonano końcowy lokalny gate:

- `compileall` — PASS;
- `tests/test_v16325555_archive_extraction_convergence.py` — 10 passed;
- rozszerzony gate archive/capability/dependency/plugin/resource-limit — 49 passed, 2 deselected;
- pełny deterministyczny pytest został rozpoczęty, ale lokalny interpreter nie ma opcjonalnych backendów `py7zr` ani `pyzipper`, a `rarfile` ma wersję 4.2. Pierwsze failures były jednoznacznie środowiskowe (`py7zr_not_installed`, `pyzipper_not_installed`), nie błędami v55;
- Pyright nie jest zainstalowany w tym sandboxie; jego gate pozostaje obowiązkiem CI;
- `run.py --version` zwrócił `16.3.25.5.55-archive-extraction-convergence`;
- `run.py doctor --json` zwrócił `installation_ok=true`, a jednocześnie oczekiwane pre-sync mismatchy manifestu dla zmienionych/nowych plików;
- `run.py package-smoke --profile system --json` zwrócił `rc=2` wyłącznie dlatego, że baza walidacyjna nadal miała metadane v54. Zgodnie z `AGENTS.codex.md` manifestów i provenance nie edytowano ręcznie.

Pełny gate dokładnego brancha na świeżym `master` należy potwierdzić w GitHub Actions po pushu, razem z kanoniczną synchronizacją `SOURCE_PROVENANCE.json` i `PACKAGE_INTEGRITY_MANIFEST.json`.

## Źródła bezpieczeństwa

- Python `zipfile`: https://docs.python.org/3.14/library/zipfile.html
- py7zr changelog v1.1.3: https://py7zr.readthedocs.io/en/stable/Changelog.html
- rarfile history 4.3–4.5: https://rarfile.readthedocs.io/news.html

## Granica odpowiedzialności

Ta aktualizacja usuwa błędną zależność od fizycznej nazwy transportowej i zwiększa niezawodność ekstrakcji, ale nie może naprawić awarii control-plane hosta, która następuje przed utworzeniem procesu (`TransportTimeoutError`, `ClientError`, `InvalidArgumentError`). Taki błąd nadal jest `host_executor_unavailable`, a nie błędem ZIP/RAR/7z.
