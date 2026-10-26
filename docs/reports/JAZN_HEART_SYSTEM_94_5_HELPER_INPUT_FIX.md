# Jaźń — Serce Systemu .94.5: walidacja wejścia operacji

2026-10-26. Częściowa poprawka na zależnym Draft PR #424, bez merge.

## Wykryty problem

`Controller.studio_helper` rezerwował operatorowi zadanie przed serializacją i limitem wejściowego JSON. Niedozwolony obiekt zgłaszał `TypeError` już po rezerwacji, pozostawiając stan `starting` bez `done`. Zbyt duże dane tworzyły zadanie bez standardowego zdarzenia terminalnego. Mogło to skutkować zablokowaniem następnej operacji.

## Poprawka i zakres

Walidacja typu, kodowanie JSON z `allow_nan=False`, UTF-8 i limit 65536 bajtów następują **przed** rezerwacją. Odrzucone dane zgłaszają `StudioError` bez wyświetlania prywatnego payloadu. Poprawny ładunek zachowuje dotychczasową ścieżkę wykonania. Dodano testy dla nieobsługiwanego typu, NaN, nadmiaru bajtów i ponownego poprawnego zlecenia.

Nie zmieniono `main.py`, parsera MCP, MEMORY ani daemona. Nadal wymagane: pełna regresja Windows, lokalne HTTP/MCP, EXE, prawdziwy ChatGPT end-to-end. Testy i kontrole trzeba zweryfikować po commicie; nie deklarować wyniku bez logu narzędzia. Manifesty release wyłącznie przez kanoniczny synchronizator.
