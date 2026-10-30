# Konsola usług Jaźni (.94.6.33)

Widok inspirowany panelem XAMPP, bez implementacji/usług XAMPP. Dotychczasowe komendy Start/Stop/Restart nadal przechodzą przez kanoniczny kontroler i ograniczenia własności procesu. Sześć wierszy usług otrzymuje stan: zielony zweryfikowana gotowość; żółty wyłącznie API Ollama; czerwony potwierdzony błąd; szary zatrzymane lub brak dowodów. PID i URL nie oznaczają gotowości. Nie uruchamia się nic przy otwieraniu tego widoku.

Odbiór operatora, rzeczywiste porty, procesy, supervisor, Cloudflare, 12 Studiów oraz full_gate TPA: NOT_RUN.

Poprawka .34: gotowość runtime wymaga jawnego `root_matches=true` i `version_matches=true`; brak dowodu nie może powodować zielonego statusu. To prezentacja, nie uruchomienie daemona.
