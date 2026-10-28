# Pierwsza instalacja Jaźni

Planowana instalacja powinna:
- wykryć zgodny interpreter Python;
- zweryfikować integralność SYSTEM;
- sprawdzić schemat konfiguracji;
- przygotować prywatny katalog .settings_local;
- nie nadpisywać istniejących ustawień;
- nie uruchamiać automatycznie daemona;
- nie dotykać produkcyjnej MEMORY;
- instalować zależności wyłącznie po autoryzacji.

Kanoniczny control plane: main.py przez run.py.