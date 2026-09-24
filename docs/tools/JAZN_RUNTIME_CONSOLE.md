# Jaźń Runtime Console — JavaScript jako warstwa operatorska

## Cel

`Runtime Console` jest lokalnym, tylko-do-odczytu interfejsem WWW do obserwacji
działającego systemu Jaźni. Wprowadza JavaScript tam, gdzie przeglądarka jest
lepszym narzędziem niż terminal lub Tk: reaktywne renderowanie, aktualizacje
bez przeładowania strony i bezpieczną wizualizację bounded JSON.

JavaScript **nie** jest drugim runtime Jaźni. Python nadal jest właścicielem:

- `run.py -> main.py` i control plane;
- daemon lifecycle;
- pamięci i SQLite;
- routingu, cognition i identity lineage;
- turn settlement i finalizacji widocznej odpowiedzi.

Przeglądarka nie może przez Runtime Console uruchamiać tur, zmieniać pamięci,
startować/zatrzymywać daemona ani finalizować odpowiedzi.

## Uruchomienie

```powershell
py -X utf8 run.py runtime-console
```

Domyślny adres:

```text
http://127.0.0.1:8765/
```

Opcjonalne jawne otwarcie domyślnej przeglądarki:

```powershell
py -X utf8 run.py runtime-console --open-browser
```

Konsola może wiązać się wyłącznie z `127.0.0.1` albo `localhost`.
Nie jest publicznym serwerem HTTP ani zamiennikiem MCP ingress.

## Kontrakt HTTP

- `GET /` — statyczny interfejs;
- `GET /api/v1/live` — tani snapshot daemon/liveness;
- `GET /api/v1/overview` — bounded status runtime/pamięć/NLP/rest/visible-turn;
- `GET /api/v1/events` — jednostronny SSE z live snapshotami;
- `GET /healthz` — health samej powierzchni konsoli;
- metody mutujące zwracają `405 runtime_console_read_only`.

Frontend nie dostaje surowego statusu. Python tworzy jawny projection allowlist,
dzięki czemu ścieżki prywatne, tokeny i nieznane pola nie są automatycznie
przenoszone do DOM.

## Dlaczego SSE zamiast WebSocket

Console potrzebuje przepływu **runtime -> przeglądarka**. `EventSource` jest
standardowym API dla Server-Sent Events i utrzymuje jednokierunkowe połączenie
HTTP. Dzięki temu v83 nie tworzy dwukierunkowego kanału sterującego ani nowego
protokołu mutacji. Po krótkim oknie streamu klient automatycznie zestawia
połączenie ponownie.

Otwarcie transportu SSE nie jest utożsamiane z `active_trusted`. Kolor i stan
runtime wynikają z danych runtime, nie z samego istnienia połączenia HTTP.

## Bezpieczeństwo

Powierzchnia jest defense-in-depth:

- tylko loopback;
- walidacja `Host` i `Origin`;
- brak CORS;
- brak POST/PUT/PATCH/DELETE;
- `Cache-Control: no-store`;
- `Content-Security-Policy` bez inline JS i bez zewnętrznych originów;
- `frame-ancestors 'none'` / `X-Frame-Options: DENY`;
- `X-Content-Type-Options: nosniff`;
- brak `innerHTML` w kodzie UI — dane trafiają do `textContent`.

Pythonowy `http.server` jest używany wyłącznie jako lokalna powierzchnia
operatorska. Dokumentacja Pythona nie rekomenduje go jako serwera
produkcyjnego, dlatego publiczny/network ingress pozostaje w istniejących
warstwach MCP/gateway.

## Node.js i testy

Runtime Console nie wymaga Node do działania w przeglądarce. Node.js 24 LTS
pozostaje opcjonalną capability developerską i CI:

```text
npm ci --prefix tools/javascript --ignore-scripts --no-audit --no-fund
npm run --prefix tools/javascript check
npm run --prefix tools/javascript probe
npm run --prefix tools/javascript test
```

`node:test` testuje czyste funkcje modelu UI niezależnie od Pythona. Pythonowe
testy kontraktowe sprawdzają loopback, projection, security headers, brak
mutacji i packaging zasobów.

## Źródła projektowe

- Node.js releases / LTS: https://nodejs.org/en/about/previous-releases
- Node.js test runner: https://nodejs.org/api/test.html
- MDN EventSource: https://developer.mozilla.org/en-US/docs/Web/API/EventSource
- MDN Fetch API: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API
- MDN Content-Security-Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy
- OWASP CSP Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html
- OWASP HTTP Headers Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- Python `http.server`: https://docs.python.org/3/library/http.server.html

## Dalsze rozszerzenia

Po ustabilizowaniu kontraktu v83 można dołożyć bez zmiany granicy authority:

1. wizualizację publicznego/audytowego Cognitive State Graph;
2. klienta Test Studio nad wspólnym Python domain core;
3. Memory Studio web UI po konwergencji osobnego PR pamięci;
4. niezależny klient testowy MCP/Tasks napisany w Node;
5. rozszerzenie VS Code korzystające z tych samych read-only kontraktów.

Żaden z tych klientów nie powinien bezpośrednio otwierać SQLite ani stawać się
właścicielem lifecycle, pamięci lub turn finalization.
