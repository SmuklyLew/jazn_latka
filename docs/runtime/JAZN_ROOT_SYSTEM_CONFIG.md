# Kanoniczna konfiguracja Jaźni w ROOT (v16.3.25.5.116.0.34.78)

Plik operatora: $ROOT/jazn_system_config.json (Windows: ROOT\jazn_system_config.json).
Jest ignorowany przez Git i wyłączony z manifestu SYSTEM; nie commitować prywatnych plików.
Przykład lokalny (dostosuj wartości i ścieżki do instalacji):

{"schema_version":"jazn_system_config/v1","values":{"JAZN_MEMORY_MODE":"off"},"studio":{"model":"gemma3:latest","daemon_url":"http://127.0.0.1:8878"}}

Priorytet: CLI > jawnie ustawione ENV > ROOT > wartości fabryczne.
Klucze na białej liście; sekrety i tokeny w osobnym magazynie.
Studio Starter zapisuje model, interpreter i endpoint do ROOT przy ręcznym Zapisz i zastosuj.
Preferencje wyglądu nadal pozostają w workspace. ROOT przeżywa jego zmianę.
Studio Konfiguracji udostępnia jawną migrację z operator.json do ROOT bez zmiany daemona.
Wykryty konflikt odrzuca migrację. Źródłowy profil pozostaje nienaruszony.
Zapis ROOT tworzy lokalny jazn_system_config.previous.json przy aktualizacji i sprawdza SHA.
Plik jest czytany przy starcie nowego procesu. Nie edytuje działającego daemona.
package-smoke ma oddzielny tymczasowy workspace dla procesów i podprocesów.
Nie uruchamiać testowego package-smoke w aktywnym workspace starszych wydań.

Źródła: https://docs.python.org/3/library/subprocess.html
https://git-scm.com/docs/gitignore
https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
