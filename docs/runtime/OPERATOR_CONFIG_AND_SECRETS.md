# Minimalna konfiguracja operatora i oddzielne sekrety Jaźni

`main.py` jest jedynym centralnym control plane. `run.py` tylko przekazuje do niego oryginalne argumenty. Przy każdym uruchomieniu `main.py`, przed importem i bootstrapem runtime (poza dependency-free `--version`), wczytywane są:

1. `config/jazn.toml` — **publiczne, wersjonowane minimum**: routing auto, pamięć optional, weryfikowalna autobiografia, lokalny endpoint Ollama, zakaz płatnej trasy bez jawnego opt-in.
2. `config/jazn.secrets.env` — **opcjonalne, lokalne sekrety**. Plik i jego zawartość nie należą do release / Git / SYSTEM ZIP. Repozytorium zawiera tylko `config/jazn.secrets.env.example`.

Nie trzeba deklarować wszystkich domyślnych flag: pozostałe wartości pozostają zdefiniowane w `JaznConfig` i modułach właścicielskich. `JAZN_ROOT` pozostaje opcjonalną informacją dla Studio/launchera, nie jest wpisany na sztywno w konfiguracji release. `JAZN_OLLAMA_MODEL` pozostaje opcjonalny (auto discovery).

Priorytet źródeł: **jawny ENV procesu (np. Studio konfiguracji / PowerShell) > lokalny plik sekretów > publiczny TOML > domyślne wartości kodu**. Sekrety i publiczne ustawienia mają odrębne, rozłączne dozwolone nazwy. Nie są wykonywane żadne wyrażenia shell, interpolacje, skrypty ani komendy. Błędy schematu, nieznane publiczne klucze, niepoprawny plik sekretów i niebezpieczny symlink są odrzucane przed modyfikacją ENV. Na POSIX plik sekretów musi mieć uprawnienia `0600` (`chmod 600 config/jazn.secrets.env`). Na Windows użyj restrykcyjnego ACL konta operatora.

## Instalacja

```powershell
Copy-Item config/jazn.secrets.env.example config/jazn.secrets.env
# Otwórz lokalnie w edytorze; usuń komentarz tylko przy faktycznie wykorzystywanym sekrecie.
python -X utf8 run.py status --json
python -X utf8 run.py chat-ollama
```

Zapis `KEY=wartość` jest dosłowny (bez cudzysłowów, ekspansji `$`, `#` ani `%`, bez wieloliniowych wartości). **Nie zapisuj tutaj tokenów, których nie używasz**. Nie wysyłaj zawartości tego pliku do GitHub, czatu, raportów ani logów. Sam `.gitignore` nie usuwa sekretów, które wcześniej trafiły do historii Git — konieczne jest unieważnienie i rotacja po ujawnieniu. Sprawdź `git check-ignore -v config/jazn.secrets.env` i `git ls-files config/jazn.secrets.env`; oczekiwany wynik drugiej komendy jest pusty.

`JAZN_ALLOW_PAID_OPENAI=0` pozostaje domyślną blokadą. OPENAI_API_KEY nie jest potrzebny do Ollamy ani do hostowego mostka ChatGPT. Włączenie trasy płatnej wymaga osobnej świadomej konfiguracji oraz odpowiedniego klucza.

`JAZN_MEMORY_MODE=optional` nie blokuje core runtime przy braku prywatnej bazy. `JAZN_MEMORY_READINESS_POLICY=native_unified_required` zaostrza wyłącznie dowód autobiograficznego recall. Nie tworzy ani nie migruje pamięci. Stan `memory` i OAuth MCP sprawdzaj osobno.

Po zmianie TOML lub lokalnych sekretów uruchom **nowy** proces Jaźni; już działający daemon nie otrzyma ustawień automatycznie. Nie przeprowadzaj restartu podczas aktywnej tury bez bezpiecznej procedury lifecycle.
