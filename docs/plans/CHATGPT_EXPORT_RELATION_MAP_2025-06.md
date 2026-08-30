# ChatGPT export — mapa relacji pięciu plików

Data analizy: 2026-08-30
Zakres: `conversations.json`, `chat.html`, `message_feedback.json`, `shared_conversations.json`, `user.json`

## Werdykt

`conversations.json` jest kanonicznym źródłem grafu rozmów. `chat.html` zawiera ten sam `jsonData` po odkodowaniu encji HTML, ale dodatkowo zawiera `assetsJson`, który mapuje wskaźniki `sediment://...` na ścieżki eksportowanych zasobów. `message_feedback.json` i `shared_conversations.json` są sidecarami relacyjnymi, a `user.json` jest metadanymi konta.

## Mapa relacji

```text
user.json
  id
   |
   +---- message_feedback[].user_id

conversations.json
  conversation_id == id              [21/21]
   |
   +---- chat.html/jsonData[].conversation_id
   |       (ten sam graf po html.unescape)
   |
   +---- message_feedback[].conversation_id
   |        |
   |        +---- message_feedback[].id
   |              == mapping[message_id].message.id
   |              (potwierdzone w tym eksporcie)
   |
   +---- shared_conversations[].conversation_id
            |
            +---- shared_conversations[].id = shared-link ID

conversations[].mapping
  3829 nodes
  3808 message nodes
  21 root nodes z message=null (dokładnie 1 na rozmowę)

chat.html
  jsonData -> duplikat semantyczny conversations.json
  assetsJson -> 2 mapowania sediment:// -> eksportowana ścieżka zasobu
```

## Wyniki ilościowe

| Obiekt | Wynik |
|---|---:|
| Rozmowy w `conversations.json` | 21 |
| Rozmowy w `chat.html/jsonData` | 21 |
| Węzły `mapping` | 3829 |
| Węzły z `message` | 3808 |
| Rooty bez `message` | 21 |
| Wiadomości `user` | 1331 |
| Wiadomości `assistant` | 1949 |
| Wiadomości `system` | 170 |
| Wiadomości `tool` | 358 |
| Feedback records | 1 |
| Shared conversation records | 1 |
| `sediment://` pointers | 2 unikalne |
| Pokrycie przez `assetsJson` | 2/2 |

## Najmocniejsze joiny

### Feedback -> konkretna wiadomość

W tym eksporcie rekord `message_feedback.json` ma `id`, który jest równocześnie kluczem w `conversations[].mapping` oraz `message.id`. Rekord dotyczy rozmowy `Łatka`; wskazany komunikat asystenta informował o przygotowaniu `info-si.txt` do pobrania. To daje join:

```text
feedback.conversation_id -> conversation.conversation_id
feedback.id              -> conversation.mapping[feedback.id].message.id
feedback.user_id         -> user.json.id
```

To jest obserwacja empiryczna dla tego eksportu; nie zakładamy bez osobnego kontraktu, że OpenAI gwarantuje ją jako publiczny, stabilny schemat na zawsze.

### Shared conversation -> rozmowa

`shared_conversations.json` wskazuje tę samą rozmowę `Łatka` przez `conversation_id`; tytuł zgadza się z rekordem rozmowy. Oficjalna dokumentacja OpenAI opisuje `shared_conversations.json` jako metadata shared links zawierającą shared-link ID, conversation ID, title i anonymity setting.

### chat.html -> conversations.json

Po wyjęciu zmiennej `jsonData` z HTML i wykonaniu `html.unescape` całe 21-elementowe drzewo jest identyczne z `conversations.json`. W związku z tym nie należy importować obu jako dwóch niezależnych źródeł rozmów. HTML pozostaje jednak wartościowy jako kontener kontrolny: osadza pełny graf, osobny resolver `assetsJson`, a jego warstwa renderująca pokazuje tylko wybraną ścieżkę od `current_node` i filtruje część typów wiadomości.

## Kontrakt importu dla Memory Rebuild v4

| Plik | Klasa źródła | Rola | Import treści jako rozmowa? |
|---|---|---|---|
| `conversations.json` | PRIMARY_CONVERSATION_SOURCE | lossless conversation graph | TAK, kanonicznie |
| `chat.html` / `jsonData` | LOSSLESS_DUPLICATE_CONTROL | pełny graf osadzony w HTML; po `html.unescape` identyczny z JSON | NIE, dedupe względem JSON |
| `chat.html` / `assetsJson` | ATTACHMENT_METADATA | resolver asset-pointerów | TAK jako metadata/provenance |
| `message_feedback.json` | FEEDBACK_METADATA | feedback do konkretnej wiadomości | NIE jako osobna wypowiedź |
| `shared_conversations.json` | SHARING_METADATA | metadane shared-linka | NIE jako treść rozmowy |
| `user.json` | ACCOUNT_METADATA | identyfikacja bundle/konta | NIE jako pamięć autobiograficzna |

## Zalecany klucz kanoniczny

- conversation key: `conversation_id`
- message key: `message.id` / klucz `mapping` (w tym eksporcie są równe dla 3808/3808 wiadomości)
- account key: `user.json.id`, tylko dla provenance/bundle linkage
- share key: `shared_conversations[].id`, niezależny od `conversation_id`
- feedback key: zachować oryginalne `id`, ale join wykonywać w parze `(conversation_id, id)`

## Granica prawdy

Ta mapa jest odtworzona z konkretnych przesłanych plików. Oficjalna dokumentacja OpenAI potwierdza ogólnie, że eksport zawiera historię czatów oraz inne dane konta, a także obecnie opisuje strukturę `shared_conversations.json`. Nie znalazłam oficjalnej publicznej specyfikacji gwarantującej pełny, stabilny schemat wszystkich pól `message_feedback.json`, `user.json` i wewnętrznego `jsonData` HTML. Dlatego ich relacje powinny być traktowane jako wersjonowany kontrakt zaobserwowanego eksportu i walidowane przy każdym imporcie.
