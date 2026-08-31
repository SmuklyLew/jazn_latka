# Jaźń Pack Generator v8.7 — Studio i przenośny ZIP

## Cel

Wersja v8.7 utrzymuje dotychczasowy kontrakt generatora i dodaje jawny profil
interoperacyjności dla paczek przeznaczonych do Windows 11 File Explorer,
7-Zip, WinZip i WinRAR. `memory_rebuild` nie jest modyfikowany.

## Standard przenośny

Najbardziej interoperacyjny wariant to:

- kontener `zip`,
- kompresja `ZIP_DEFLATED` (lub STORE dla poziomu 0 tam, gdzie stosowane),
- woluminy `independent`, czyli każdy wynik jest kompletnym ZIP-em,
- nazwy wpisów bez kolizji Windows, urządzeń `CON/PRN/AUX/NUL/COM*/LPT*`,
  końcowych kropek/spacji, znaków zabronionych i casefold collisions,
- CRC + SHA-256 + sidecar kontraktu Jaźni.

`binary` (`.zip.001/.002/...`) pozostaje poprawnym transportem Jaźni i może być
konieczny dla bardzo dużej pamięci, ale nie jest bezpośrednim ZIP-em dla
Explorer/WinZip. Najpierw trzeba go połączyć do pełnego `.zip` (np. przez
wygenerowany `join.ps1`). Raport zgodności v8.7 rozróżnia te dwa przypadki.

## Studio

`python tools/jazn_pack_generator.py studio` uruchamia GUI `tkinter/ttk` z
zakładkami PAKOWANIE, WERYFIKACJA i USTAWIENIA. Na Windows Studio może być
uruchamiane automatycznie przy starcie bez argumentów; można to wyłączyć w
ustawieniach Studio lub zmienną `JAZN_PACK_GENERATOR_NO_STUDIO=1`.

Studio domyślnie włącza Portable ZIP. Tryby 7z, AES ZIP i binary pozostają
jawnie dostępne jako tryby specjalistyczne.

## Nazwa paczki

Przy uruchomieniu generator rozpoznaje nazwy, które sam wcześniej wygenerował
w postaci `jazn_latka_v<wersja>-<release>`, i odświeża je na podstawie
`latka_jazn/version.py`. Własna nazwa użytkownika pozostaje bez zmian.
Zmiana katalogu źródłowego w Studio również odświeża nazwę kanoniczną.
