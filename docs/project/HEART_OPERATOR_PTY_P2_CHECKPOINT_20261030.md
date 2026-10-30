# Wbudowana sesja PTY (etap P2 — częściowy)

Na Windows opcjonalny, już istniejący w repozytorium kontrakt `winpty.PtyProcess.spawn`; na Linux standardowe `pty.openpty`. Start wyłącznie na przycisk operatora. Sesja to odrębna powłoka systemowa, nie Jaźń, nie daemon, nie XAMPP. Brak biblioteki opcjonalnej blokuje tę funkcję bez instalowania pakietów.

QPlainTextEdit przekazuje klawisze wejściowe i pobiera wyjście w ograniczonych paczkach z kolejki wątku. **Nie ma pełnej emulacji VT/ANSI**, testów pełnoekranowych ani fizycznych testów ConPTY; pełny odbiór P2 = NOT_RUN. Dla bezpieczeństwa nie ma dowolnego stringa uruchomieniowego ani przejmowania obcego PID. Zamykanie sesji dotyczy tylko powłoki należącej do JSS, nie runtimu Jaźni.

Źródła: https://docs.python.org/3/library/pty.html oraz https://github.com/andfoy/pywinpty .

Poprawka .34: rzeczywiste rozmiary POSIX PTY są ustawiane przed uruchomieniem powłoki; operator może zmieniać rozmiar aktywnej sesji (Python `termios.tcsetwinsize` / opcjonalny `pywinpty.setwinsize`). Po zamknięciu możliwa jest nowa, osobna sesja na kliknięcie. Regresje obejmują odmowę zmiany rozmiaru nieaktywnej sesji, granice oraz geometrię POSIX. Nadal: niepełny VT/ANSI, manualne Windows ConPTY i fizyczne DPI NOT_RUN.

TPA .35: karta „Odbiory lokalne” wymienia pozostałe próby Windows/Linux PTY/ConPTY. Brak automatycznego PASS bez wyników na rzeczywistych maszynach.
