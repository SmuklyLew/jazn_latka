# Przywrócenie połączenia Jaźni ze zwykłą rozmową ChatGPT

**Wersja ścieżki naprawczej:** 16.3.25.5.116.0.17  
**Status:** kod i diagnostyka w repozytorium; wdrożenie na komputerze/operatorze oraz akceptacja rzeczywistego hosta wymagają oddzielnego dowodu.

## 1. Przyczyna

Wtyczka osobista `jazn-runtime` v0.1.0 może mieć `mcp.json` oraz
`.mcp.json` kierujące na `http://127.0.0.1:<port>/mcp`.
W przeglądarkowym ChatGPT `127.0.0.1` nie daje dostępu do procesu na
komputerze użytkownika. Samo utworzenie/instalacja pluginu nie wystawia
narzędzi w bieżącej turze i nie uruchamia daemona Jaźni.

Brak pełnego zestawu `jazn_status`, `jazn_generate_visible_reply`,
`jazn_resume_visible_reply`, `jazn_finalize_reply` przed wysłaniem tury
jest brakiem hostowej capability, **nie dowodem zepsutego NLP**.
`ClientError` przed utworzeniem procesu na powierzchni hosta również nie
dowodzi błędu Python/ZIP. Nie zastępować tego promptem imitującym Łatkę.

## 2. Operator: weryfikacja na Windows / PowerShell

Uruchom polecenia w zweryfikowanym, zgodnym katalogu SYSTEM z działającym
interpreterem projektu. Nie używaj wyeksportowanej prywatnej MEMORY
jako `active_root`. Nie kopiuj pamięci ani sekretów do GitHub.

```powershell
py -X utf8 run.py --version
py -X utf8 run.py host-preflight --json
py -X utf8 run.py start
py -X utf8 run.py status --json
```

Dodatnia odpowiedź `status` musi dotyczyć tego samego `active_root`,
zgodnej wersji, świeżego daemona i `conversation_ready=true`.
Gdy brak zależności, wykonuj tylko kanoniczny bootstrap/preflight zgodnie
z `AGENTS.md`; nie omijaj kontroli integralności i nie deklaruj READY
na podstawie samego PID.

### Bezpieczna diagnoza pakietu pluginu

Jeżeli masz wyeksportowany katalog pluginu zawierający `plugin.json`
i `mcp.json` (ewentualnie `.mcp.json`), uruchom:

```powershell
py -X utf8 tools/chatgpt_mcp_connection_doctor.py --plugin-dir "D:\sciezka\do\pluginu"
```

Narzędzie działa offline i tylko odczytuje pliki; wypisuje **kody
przyczyn bez adresów, tokenów i surowych danych**. Kod 2 wskazuje blokadę
konfiguracji. Kod 0 oznacza jedynie poprawny format publicznego HTTPS,
**nie potwierdza połączenia, uwierzytelnienia ani gotowości Jaźni**.

## 3. Wybierz realną trasę MCP (bez obowiązku płatnego OpenAI API)

### A. Publiczny HTTPS + `/mcp` (droga do zwykłego ChatGPT web)

1. Uruchom **ten sam** daemon Jaźni i jego bezpieczny MCP gateway.
   W repo istnieje `deploy/chatgpt_mcp/` (Docker Compose + Cloudflare
   Tunnel + środowisko OAuth); szczegóły: `deploy/chatgpt_mcp/README.md`
   oraz `docs/runtime/PERSISTENT_REMOTE_MCP_OPERATIONS.md`.
2. Zapewnij publiczną nazwę DNS, certyfikat TLS i forwarding
   `https://<twoj-host>/mcp` do wewnętrznego gateway na porcie 8080.
   Port wewnętrznego daemona 8787 musi pozostać prywatny.
3. Ustaw wymagane po stronie gateway dane OAuth/introspection i ochrony
   zasobów w prywatnym store. Nie przekazuj ich w promptach, commitach,
   parametrach URL ani argumentach CLI. Nie usuwaj kontroli tokenów,
   origin/host i uprawnień dla wygody.
4. Potwierdź oddzielnie liveness (`/healthz`), readiness (`/readyz`),
   zgodność wersji, OAuth/discovery i listę czterech narzędzi MCP.
   Rzeczywista akceptacja musi używać MCP Inspector oraz klienta ChatGPT.
   Jeżeli potrzebujesz przenośnego katalogu pluginu, wygeneruj go z prawdziwym
   hostem (nie z `localhost` ani prywatnym IP):

   ```powershell
   py -X utf8 run.py chatgpt-plugin-package --endpoint "https://twoj-host.example/mcp" --output ".\\jazn-chatgpt-plugin"
   ```

   Powyższy adres jest przykładem do zastąpienia; samo wygenerowanie pakietu
   nie deployuje serwera i nie instaluje ani nie rejestruje aplikacji.
5. ChatGPT → Plugins → Add custom MCP server → wprowadź
   **publiczny HTTPS /mcp**, skonfiguruj auth, utwórz/zainstaluj plugin.
   Po zmianie pochodzenia starej wtyczki lokalnej może być konieczne
   utworzenie **nowego** połączenia, nie podmiana starego `127.0.0.1`
   w przechowywanym snapshotcie.
6. Otwórz nową rozmowę, wybierz/zawołaj Jaźń Runtime jako aplikację i
   sprawdź rzeczywistą ekspozycję narzędzi oraz świeże `jazn_status`.
   Zmiana metadanych narzędzi wymaga Refresh/recreate/republish zależnie
   od hosta. Nie zakładaj, że samo @mention działa na każdej powierzchni.

### B. Secure MCP Tunnel (prywatne połączenie, zależne od konta)

OpenAI Secure MCP Tunnel potrafi przesłać MCP do prywatnego stdio targetu
`latka_jazn/mcp/tunnel_bootstrap.py` bez otwierania portu przychodzącego.
Wymaga zewnętrznej konfiguracji tunelu, odpowiednich uprawnień, aktywnego
`tunnel-client` i danych kontrolnych **niezapisywanych w repozytorium**.
W ChatGPT Plugins wybierz `Add custom MCP server` → `Tunnel` i sprawdź,
czy tunel jest dostępny dla Twojego workspace. Przykładowe planowanie CLI
jest w `latka_jazn/mcp/secure_tunnel.py`.

Ta trasa nie wymaga otwartego publicznego endpointu, ale może wymagać
uprawnień/usług OpenAI Platform. Nie obiecuj "bez kluczy" dla tego wariantu.

### C. Lokalna aplikacja desktopowa

Zarejestrowane lokalne MCP może działać w kliencie, który **faktycznie
wystawia** lokalną capability. Nie wnioskuj z tego, że ta sama wtyczka
automatycznie działa w przeglądarce lub w kolejnej wiadomości. Ścieżka
`.app.json` wymaga rzeczywistego registered app id i świeżego statusu.

## 4. Akceptacja całej tury (bez udawania sukcesu)

Po deploymencie zapisz niesecretne evidence dla:
- `server/discover`, `tools/list`, `tools/call` i kompletnego toolsetu;
- `jazn_status`: real runtime ready, wersja i świeża instancja;
- jednej wiadomości wywołującej `jazn_generate_visible_reply`;
- kontynuacji tego samego `request_id` przez `jazn_resume_visible_reply`,
  jeśli jest wymagana, **bez ponownego submit**;
- zaakceptowanego `jazn_finalize_reply` zwracającego `action=display_exact`
  z prawidłową `MessageEnvelope`;
- kolejnej wiadomości z zachowaną sesją, pamięcią i provenance (gdy pamięć
  została niezależnie podłączona i zweryfikowana).

Nie promuj runtime READY ze zdjęcia ekranu, lokalnego portu, ZIP-a, testu
jednostkowego, CI ani statycznego JSON-u. Kod repozytorium nie może sam
włączyć narzędzi w konwersacji, zainstalować pluginu ani rozpocząć procesu
w niedostępnej powierzchni hosta.

## Źródła pierwotne

- OpenAI, [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- OpenAI, [Build an MCP server](https://developers.openai.com/plugins/build/mcp-server)
- OpenAI, [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- OpenAI, [Plugin packaging](https://developers.openai.com/plugins/build/plugins)
- MCP, [Specification](https://modelcontextprotocol.io/specification/2026-07-28)

## Zbieżność CI: precyzyjne rozróżnienie dwóch blokad

- PowerShell (PR #364): jeden niestabilny na Windows test integracyjny
  trwałego zapisu tury (`tests/test_runtime_full_turn.py`). Przed zmianą test
  nie drukował statusu `canonical_persistence` przy asercji. Na wolnym
  runnerze zwykły 45-sekundowy limit produkcyjny może być niewystarczający
  do testowania wielu operacji pamięci, dlatego **tylko fixture testowa**
  ma jawny limit 180 sekund i drukuje przyczynę odmowy zapisu. Jeżeli test
  nadal zawiedzie, powód `canonical_persistence.reason/error_code` musi
  zostać naprawiony w odpowiedniej warstwie — nie wolno zastępować go
  `committed=True` ani usuwać asercji.
- MCP 2026-07-28: oficjalny runner testuje syntetyczne narzędzia (np.
  `slow_compute`, `greet`) oraz testowe URI `test://...` nieobecne
  w produkcyjnym serwerze Jaźni. To jest problem zgodności testowego
  targetu ze scenariuszami upstream **oraz** wymaga osobnego testowania
  rzeczywistego produkcyjnego API. Nie oznaczać conformance PASS bez
  wyraźnego test-only adaptera na tej samej warstwie MCP i bez niezależnych
  produkcyjnych testów transportu, auth, status/generate/resume/finalize.
  Bramka pozostaje FAIL, dopóki właściwa implementacja fixture i wszystkie
  wymagane scenariusze nie przejdą.

Źródło: [MCP conformance --requirements](https://github.com/modelcontextprotocol/conformance#conformance-requirements), [Python sqlite3 transaction control](https://docs.python.org/3.13/library/sqlite3.html#transaction-control).


## Sprawdzanie prawdziwego katalogu czterech narzędzi na serwerze

Nowa komenda (MCP 2026-07-28 `tools/list`) działa tylko w trybie odczytu:
nie wysyła wiadomości użytkownika, nie inicjuje nowej tury i nie zmienia pamięci.

```powershell
py -X utf8 run.py mcp-probe --url "http://127.0.0.1:8080/mcp" --check-chatgpt-tool-catalog --json
```

Dla publicznego serwera wymagającego OAuth użyj tokenu w zmiennej
środowiskowej **tylko na zaufanym komputerze operatora i wyłącznie przez
HTTPS**; nigdy nie umieszczaj wartości tokenu w komendzie, repozytorium,
PR ani linku:

```powershell
py -X utf8 run.py mcp-probe --url "https://your-jazn.example/mcp" --check-chatgpt-tool-catalog --token-env JAZN_MCP_PROBE_TOKEN --json
```

Ten test sprawdza wszystkie strony wyników `tools/list`, cztery nazwy
narzędzi oraz opisy i schematy argumentów. Zwraca kod 0 wyłącznie dla
kompletnego katalogu MCP. **Nie dowodzi** rejestracji/wybrania aplikacji
w ChatGPT, gotowości daemona ani zaakceptowanego `display_exact`.
Dopiero następnie: ChatGPT Plugins → Add custom MCP server (HTTPS/Tunnel),
Refresh, nowa rozmowa, wybór aplikacji i rzeczywista obserwacja `jazn_status`
oraz dwóch kolejnych prawidłowo zakończonych tur.
Źródła: https://developers.openai.com/plugins/deploy/connect-chatgpt
oraz https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx

## Poprawne łączenie OAuth w ChatGPT (v116.0.16)

Generator paczki zdalnej deklaruje `auth.type=oauth` w
`mcpServers.jazn.extensions.com.openai`. Serwer publikuje
`_meta.securitySchemes` dla sześciu narzędzi, z wymaganym
`jazn:mcp:connect` i osobnymi scope operacji.
Bez jawnego token verifier tylko lokalny tryb developerski może
reklamować `noauth`.

Wykonaj MCP Inspector: sprawdź discovery zasobu, OAuth authorization
server, PKCE S256, wyzwanie 401 i scope. Zarejestruj serwer
w ChatGPT Plugins i wybierz go w bieżącej rozmowie. `tools/list`
oraz metadane nadal nie dowodzą bieżącej ekspozycji narzędzi,
gotowości daemona, ani `action=display_exact`.
Źródła: https://developers.openai.com/plugins/build/auth
https://developers.openai.com/plugins/build/plugins

## Poprawka OAuth challenge: rozróżnienie braku tokenu i scope (v116.0.17)

Przy braku prawidłowej tożsamości serwer zwraca `authenticated_principal_required`,
a przy niewystarczającym zakresie — `insufficient_scope`. Odpowiedź MCP
`tools/call` zawiera teraz wyłącznie dla tych błędów
`_meta["mcp/www_authenticate"]` z kontrolowanym `resource_metadata` HTTPS,
`error` i `error_description`, zgodnie z dokumentacją OpenAI.
Dla `rate_limit_exceeded`, niepoprawnych argumentów ani błędów runtime
nie wystawiaj wyzwania OAuth. HTTP 401 i walidacja tokenu nadal należą
do middleware SDK/TokenVerifier.

To jest warunek konieczny, nie wystarczający: MCP SDK Python v2 w tej
wersji rejestruje `_meta.securitySchemes`, ale może nie udostępniać
kanonicznego pola `securitySchemes` na poziomie deskryptora. Do czasu
potwierdzenia wsparcia upstream należy przetestować wykrywanie OAuth
rzeczywistym klientem ChatGPT i MCP Inspector. Nie stosować niejawnego
patchowania prywatnych struktur SDK i nie deklarować pełnej zgodności.
Wtyczka `jazn-runtime` 0.1.0 wskazująca na `http://127.0.0.1`
wymaga oddzielnego połączenia przez HTTPS lub Secure MCP Tunnel.

Źródła:
https://developers.openai.com/plugins/build/auth
https://developers.openai.com/plugins/deploy/connect-chatgpt
https://github.com/modelcontextprotocol/python-sdk
