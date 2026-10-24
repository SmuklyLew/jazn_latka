# Studio Jaźni — wspólna powłoka Qt / Workbench (.85)

Inspiracja operatorska: ciemna, subtelnie purpurowa ergonomia z układem
podobnym do edytorów kodu, bez kopiowania VS Code i **bez tła z logo**.

Implementacja: `tools/jazn_run_studio/workbench_theme.py` definiuje
wielokrotnego użytku, lokalny dla okna motyw Qt; nie wymusza zmian wyglądu
innych narzędzi w procesie. `window.py` korzysta z jednej powłoki:
- lewa nawigacja do istniejących stron i nowego „Odbioru lokalnego”;
- nagłówek z bieżącą stroną i stanem „niezweryfikowanym”, bez wnioskowania
  o gotowości usługi z PID lub procesu;
- resizowalna główna powierzchnia i dolny panel per-operacja z zakładkami
  `Zdarzenia`, `Błędy`, logami uruchomień, diagnozą i czatem;
- `Ctrl+B` przełącza boczny pasek, `Ctrl+J` dolny panel; panel
  zachowuje istniejący kontrakt niewznawiania po ręcznym ukryciu;
- `system` light/dark, `light`, `dark`, `purple`, `custom`;
  własny kolor tylko po zatwierdzeniu w Studio.

To jest wspólny fundament natywnych **nowych** Studiów. Osobne stare okna
Tk/Qt nie są automatycznie migrowane ani uznawane za zaliczone w tym etapie.
Weryfikacja: testy składni, pyright, testy GUI na Windows/Ubuntu,
rzeczywisty odbiór operatora w Studio (nie zastępuje go `--gui-smoke`).

Oficjalne dokumenty:
- https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSplitter.html
- https://doc.qt.io/qtforpython-6/PySide6/QtGui/QStyleHints.html
- https://code.visualstudio.com/docs/editing/getting-started/userinterface
