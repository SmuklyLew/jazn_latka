# Odbiór lokalny w Studio Jaźni (.84)

## Cel i granice

Zakładka **Odbiór lokalny** służy do jawnego zbierania wyników testów,
których GitHub Actions i zdalny host nie mogą wykonać na komputerze operatora.
Nie uruchamia poleceń automatycznie, nie zgłasza gotowości modelu i nie
zastępuje sprawdzania lineage, process identity ani finalization.

- Repozytorium wersjonuje katalog bazowych testów w
  \`tools/jazn_run_studio/local_acceptance.py\`.
- Wyniki, notatki, lokalne dowody i własne przypadki operatora są przechowywane
  poza SYSTEM w \`operator_file("jazn_studio_manual_acceptance", root,
  "manual_results.json")\`. Domyślnie jest to
  \`~/.jazn/tools/jazn_studio_manual_acceptance/manual_results.json\`.
- Dane nie trafiają do GitHub, MEMORY ani do markerów runtime. Nie wklejaj
  sekretów, tokenów ani całych prywatnych logów. Pole „dowód” powinno
  zawierać jedynie identyfikator lub lokalną ścieżkę.
- Własny przypadek można dopisać w UI bez zmiany repozytorium.
- Po wykonaniu: wybierz wynik PASS / FAIL / BLOKADA, zanotuj fakty i dodaj
  odniesienie do dowodu. Tylko PASS z niepustą notatką i dowodem można
  przenieść do archiwum. Archiwizacja jest append-only, bez usuwania historii.
- Nowe wydanie ma nowy scope \`PACKAGE_VERSION_FULL\`. Dawny PASS nie zostanie
  odziedziczony jako nowy PASS, a historia z wcześniejszej wersji pozostaje.
- CAS/digest i atomowy zapis zapobiegają cichej utracie danych w przypadku
  zmian pliku w innym procesie. Backup powstaje przed aktualizacją.
- Obecne pole PASS jest deklaracją operatora. Automatyczna weryfikacja
  powiązania z dowodem (SHA pliku, signature) jest osobnym zadaniem.

## Wymagane testy tej iteracji

\`gui-daemon\`, \`ollama-two-turns\`, \`chat-reconnect\`, \`chat-resume\`,
\`daemon-restart\`, \`smoke-isolation\`, \`config-persistence\`,
\`studios-parity\`, \`offline-exe\` i \`ui-accessibility\`.

Dodatkowo każde z 12 studiów otrzymuje własną pozycję w kolejce `studio-*`,
z własnym stanem i historią. Jedna ogólna pozycja `studios-parity` nie
zastępuje 12 dowodów szczegółowych.

Tylko ich rzeczywisty odbiór na systemie operatora może zamknąć ręczną bramkę.
Po zakończeniu i archiwizacji można dopisać kolejne testy w następnym wydaniu,
bez nadpisywania historii.

Dokumentacja źródłowa:
- https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QTableWidget.html
- https://docs.python.org/3/library/os.html#os.replace
- https://docs.python.org/3/library/json.html
