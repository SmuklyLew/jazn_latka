# Jaźń — konfiguracja wersjonowana

Ten katalog zawiera publiczne schematy, szablony i wartości domyślne.

- defaults/ — deklaracje ustawień domyślnych
- schemas/ — schematy walidacji
- templates/ — szablony pierwszej instalacji
- dependencies/ — katalog źródeł zależności
- installation/ — kontrakty instalatora

Prywatne dane należą do .settings_local/.

UWAGA: same szablony nie zmieniają zachowania runtime.
Dopiero zweryfikowany resolver i instalator mogą je stosować.