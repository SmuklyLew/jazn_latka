# Jaźń Pack Generator 10.1.86.0.112 — byte-exact staging and EOL fail-closed

Generator zachowuje rolę czystego archiwizera SYSTEM / MEMORY / SYSTEM+MEMORY.
Nie buduje wheelhouse, dependency bundle ani Python runtime.

## Kontrakt integralności

1. SYSTEM wymaga obecnego `.gitattributes`.
2. Przed utworzeniem ZIP wszystkie pliki są kopiowane do tymczasowego canonical
   release staging bez transformacji treści.
3. Kopia stagingowa musi mieć identyczny SHA-256 jak odczytane bajty źródła.
4. Dla plików SYSTEM generator odczytuje obowiązującą politykę `text`/`eol` z
   `.gitattributes`. Drift LF/CRLF jest błędem fail-closed przed utworzeniem paczki.
5. Manifest `jazn_pack_generator_package/v2` zapisuje SHA-256 każdego pliku.
6. Po utworzeniu ZIP każdy wpis jest ponownie hashowany z archiwum i musi być
   identyczny z SHA-256 stagingu.
7. `verify` wykorzystuje sidecar `.package.json`, jeśli jest dostępny, i wykonuje
   kontrolę per-member SHA-256; starszy manifest bez hashy pozostaje możliwy do
   sprawdzenia wyłącznie na poziomie ZIP/CRC.

## Polityka EOL

Repozytorium używa LF jako domyślnego EOL dla automatycznie rozpoznanych plików
tekstowych. Skrypty Windows (`.ps1`, `.psm1`, `.psd1`, `.bat`, `.cmd`) mają
jawny CRLF. Historyczne `.archives/**` zachowują dokładne bajty i nie podlegają
normalizacji tekstowej.

Generator nie „naprawia” EOL po cichu i nie liczy hashy po normalizacji. Jeżeli
working tree nie spełnia polityki, pakowanie SYSTEM jest blokowane z komunikatem
`EOL drift`. Dzięki temu SHA-256 oznacza rzeczywistą integralność bajtową.
