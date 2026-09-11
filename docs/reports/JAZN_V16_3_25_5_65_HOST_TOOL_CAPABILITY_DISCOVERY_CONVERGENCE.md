# Jaźń v16.3.25.5.65 — host-tool capability discovery convergence

## Cel

Ta aktualizacja usuwa architektoniczne założenie, że lista narzędzi hosta jest stałą właściwością kodu Jaźni. Dotychczas `host_tool_turn_policy.py` posiadał lokalne `KNOWN_HOST_TOOLS`, co było użytecznym bezpiecznikiem, ale nie było prawdziwym discovery hosta: proces Python nie może z samego importu, PID-u ani TTY dowiedzieć się, jakie narzędzia udostępnia aktualny host ChatGPT.

Nowy kontrakt rozdziela trzy rzeczy:

1. **trusted catalog** — wiedza Jaźni o semantyce i ryzyku znanych klas narzędzi;
2. **host manifest** — deklaracja tego, co bieżący host rzeczywiście wystawia;
3. **observed evidence** — wynik rzeczywistego, uprawnionego użycia narzędzia w bieżącej lub wcześniejszej zweryfikowanej turze.

Dopiero manifest albo evidence może być podstawą twierdzenia o dostępności. TTY, aktywny daemon, lokalny import i podobny interfejs nie są dowodem obecności narzędzia hosta.

## Źródła projektowe

Projekt został oparty na kontraktach discovery i bezpieczeństwa MCP:

- MCP `tools/list` jest jawnie operacją discovery dostępnych narzędzi, a lista może być stronicowana i zmieniać się w czasie: https://modelcontextprotocol.io/specification/2025-11-25/schema
- MCP opisuje `readOnlyHint`, `destructiveHint`, `idempotentHint` i `openWorldHint`, ale zaznacza, że annotations są tylko hintami i nie wolno opierać na niezaufanych annotations decyzji bezpieczeństwa: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- dlatego Jaźń przechowuje własny konserwatywny katalog ryzyka, a hostowe `annotations` zachowuje wyłącznie jako raportowane metadane.

Dla zasobów medialnych użyto oficjalnych kontraktów wyszukiwania/metadanych:

- YouTube Data API `search.list` zwraca zasoby `video`, `channel` i `playlist`: https://developers.google.com/youtube/v3/docs/search/list
- Spotify Web API `Search for Item` wyszukuje katalog m.in. albumów, wykonawców, playlist, utworów, audycji i odcinków: https://developer.spotify.com/documentation/web-api/reference/search

Jaźń nie wywołuje tych API bezpośrednio w tym module. Źródła służą do poprawnego modelowania semantyki lookupu. Faktyczne zewnętrzne wyszukiwanie pozostaje hostową capability, np. `web.run`.

## Implementacja

### `latka_jazn/core/host_tool_capabilities.py`

Nowy moduł udostępnia:

- wersjonowany `HostToolDescriptor` i trusted catalog;
- stany `unknown`, `advertised`, `verified`, `degraded`, `unavailable`;
- jawny manifest przez `JAZN_HOST_TOOL_CAPABILITIES_JSON` lub `JAZN_HOST_TOOL_CAPABILITIES_FILE`;
- bounded parser: limit liczby narzędzi i rozmiaru manifestu, walidacja nazw, odrzucenie symlinkowego pliku manifestu;
- `probe_plan`, który odróżnia bezpieczny read-only probe od capability, których nie wolno wywoływać tylko po to, aby sprawdzić ich istnienie;
- możliwość podniesienia `advertised -> verified` przez rzeczywiste tool evidence;
- otwarty model rozszerzeń: host może zadeklarować narzędzie nieznane bieżącej wersji Jaźni, ale takie narzędzie dostaje konserwatywną politykę i zakaz automatycznego probe.

Brak manifestu nie oznacza `unavailable`. Oznacza brak zweryfikowanej informacji o dostępności. Dla zgodności bieżącej integracji trusted catalog może nadal dostarczyć kandydatów do planowania tury, ale polityka jawnie wskazuje `capability_confirmation_required_for_tools`.

### `latka_jazn/core/host_tool_turn_policy.py`

Usunięto lokalne `KNOWN_HOST_TOOLS` jako źródło prawdy o dostępności. Policy najpierw ustala narzędzia potrzebne semantycznie przez turę, a następnie przecina je z capability snapshotem.

Jeżeli host jawnie deklaruje, że wymagane narzędzie jest niedostępne, powstaje `required_tools_unavailable`, a validator zwraca `required_host_tool_unavailable:<tool>` zamiast pozwolić na wymyślony wynik albo boczną trasę.

Wszystkie wcześniejsze invariants pozostają obowiązujące: narzędzie jest pośrednim evidence tej samej tury, runtime zachowuje authority, a widoczny tekst nadal wymaga phase-2, accepted final i `MessageEnvelope`.

### `latka_jazn/core/host_media_resources.py`

Dawna mała krotka `_MEDIA_LOOKUP_TOKENS` została zastąpiona utrzymywalnym katalogiem zasobów i słownikiem lookupu.

Rozpoznawane są m.in. YouTube/YouTube Music, Spotify, SoundCloud, Bandcamp, Apple Music/Podcasts, Deezer, TIDAL, Mixcloud, Audiomack, Last.fm, MusicBrainz, Discogs, Genius, Musixmatch, Vimeo i Dailymotion oraz szerszy słownik polskich i angielskich intencji dotyczących utworu, albumu, wykonawcy, tekstu, remixu, wersji live, playlisty i podcastu.

Detekcja nie oznacza, że system „słyszał” nagranie. Kontrakt jawnie rozdziela lookup publicznych metadanych/strony od odtwarzania audio i od dostępu do pełnego chronionego tekstu.

### `latka_jazn/core/bridge_discovery.py`

`run.py bridge-discovery` zwraca teraz `host_tool_capabilities` oraz skrócony kontrakt pod `chatgpt_bridge.host_tool_capability_discovery`. Dzięki temu po uruchomieniu Jaźni host może odczytać, co runtime wie o narzędziach, które capability są tylko advertised, które zostały verified i których nie wolno automatycznie testować.

## Polityka probe

Automatyczne sprawdzenie capability jest dozwolone tylko wtedy, gdy można wykonać bounded operację read-only bez skutku ubocznego i bez niepotrzebnego dostępu do prywatnych danych.

Przykłady:

- `web.run`: dopuszczalny bounded public read/search probe;
- `GitHub`: tylko read-only suboperation; żadnych commitów, branchy, merge, delete ani update podczas samego probe;
- `file_search`: probe odroczony do realnej potrzeby użytkownika, aby nie enumerować prywatnych plików tylko dla diagnostyki;
- `image_gen`, `automations`, `python_user_visible`: brak automatycznego probe, bo samo wywołanie tworzy artefakt, akcję lub widoczny skutek;
- narzędzie nieznane: domyślnie brak automatycznego probe i konserwatywne założenie o możliwym skutku ubocznym.

## Granica prawdy

Ten moduł nie daje procesowi Jaźni magicznej możliwości introspekcji UI ChatGPT. Host musi jawnie przekazać inventory, gdy platforma udostępnia taką możliwość, albo runtime uczy się stanu capability z rzeczywistego evidence. Jeżeli host niczego nie przekazał, stan pozostaje `host_manifest_missing` / `unknown`.

Capability snapshot nie jest także dowodem aktywnej Jaźni. Aktywny runtime i accepted visible turn nadal mają własne, niezależne bramki lineage i finalizacji.
