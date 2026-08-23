# Jaźń v16.0.6 — Runtime Turn Liveness CI Hardening

## Zakres

Ta poprawka usuwa z aktywnej dokumentacji literal historycznej wersji, który sam był wykrywany przez audyty current-line po v16.0.5.

## Zmiana

Raport v16.0.5 odwołuje się teraz do stałej `LEGACY_MEMORY_SOURCE_VERSION` zamiast powtarzać historyczny numer pakietu. Nie rozszerza to allowlisty i nie osłabia audytu; aktywne drzewo nadal musi być wolne od niezatwierdzonych starych referencji.

## Wersja

Kanoniczna wersja: `16.0.6-runtime-turn-liveness-ci-hardening`.
