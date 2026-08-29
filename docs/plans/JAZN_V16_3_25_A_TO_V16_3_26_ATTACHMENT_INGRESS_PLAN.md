# Jaźń v16.3.25.A.01+ -> v16.3.26 — host attachment & multimodal ingress

## Status

Ten dokument definiuje planistyczny train prac pomiędzy aktualnym release `16.3.25-memory-rebuild-source-union-hardening` a kolejnym systemowym release `16.3.26-host-attachment-multimodal-ingress-hardening`.

`16.3.25.A.xx` **nie jest kanoniczną wersją runtime**. Oznaczenia A.xx służą jako checkpointy/etapy implementacyjne jednego niezmargowanego release trainu. `latka_jazn/version.py` pozostaje jedynym źródłem wersji systemowej; finalny release tej pracy ma numer `16.3.26`.

## Fundament historyczny v16.0.0

Release v16.0.0 ustanowił jeden host-level `workspace_runtime` i jeden kanoniczny `JAZN_ACTIVE_RUNTIME.json`. Ten invariant pozostaje obowiązkowy:

- kod może istnieć w wielu wersjonowanych `active_root`;
- mutable host/process state nie należy do wersjonowanego kodu;
- nowy ingress załączników nie może przywrócić `<active_root>/workspace_runtime` jako równoległego źródła prawdy;
- transient materialization/staging, jeżeli jest potrzebny, ma używać kanonicznego host-level workspace;
- `workspace_runtime` nie trafia do paczki systemowej ani memory.

Szczegóły: `docs/runtime/SINGLE_CANONICAL_RUNTIME_WORKSPACE.md`.

## Problem

Bieżący host/runtime contract jest przede wszystkim tekstowy. Obecny `MessageEnvelope` wymaga niepustego `body`, co nie reprezentuje naturalnie tury zawierającej sam załącznik. Zaobserwowany przypadek hostowy pokazuje, że attachment-only może zostać sprowadzony do pustej wiadomości tekstowej zamiast wejść do kanonicznego routingu.

Docelowo Jaźń ma odbierać co najmniej:

- text-only;
- attachment-only;
- text + attachment;
- text + wiele attachments;
- pliki tekstowe/kod (`txt`, `md`, `json`, `jsonl`, `py` i pokrewne dozwolone typy);
- dokumenty, w tym PDF, w granicach dostępnych parserów;
- obrazy (`png`, `jpg`, `jpeg`, `webp`) dla ścieżki multimodalnej.

## Invariants

1. Dokładna treść tekstowa użytkownika nie jest streszczana przed runtime.
2. Załącznik ma jawny kontrakt i provenance; nie jest zamieniany na opis wygenerowany przez host bez oznaczenia źródła.
3. Attachment-only jest legalną turą i nie wymaga sztucznego placeholdera w `body`.
4. Odebranie pliku nie jest równoznaczne z trwałym zapisem do pamięci.
5. Promocja treści/faktów z pliku do L2/L3 przechodzi istniejące memory/truth/provenance/promotion gates.
6. Mutable staging używa host-level `workspace_runtime`, zgodnie z invariantem v16.0.0.
7. Ścieżki, nazwy plików i MIME są danymi nieufnymi; wymagają normalizacji i policy gate.
8. Nie wolno ufać rozszerzeniu pliku zamiast rzeczywistego typu/kontraktu.
9. Staging/cache jest bounded oraz możliwy do usunięcia bez utraty trwałej pamięci.
10. Dla obrazu model text-only nie może udawać capability vision.
11. Brak wspieranej ścieżki vision oznacza fail-closed albo jawne użycie dostępnego multimodalnego host/backendu.
12. Każdy attachment ma stabilny identyfikator oraz SHA-256 lub równoważny content identity tam, gdzie host udostępnia bajty/materializację.
13. Prywatne pliki użytkownika nie trafiają do repo, CI ani sanitizowanych raportów.

## Docelowy kontrakt wejścia

Nazwa klasy nie jest przesądzona. Preferowany kierunek to rozszerzenie kontraktu **wejścia tury**, zamiast wtłaczania załączników do envelope finalnej wypowiedzi Łatki.

Przykład semantyczny:

```text
TurnInputEnvelope
├── text: str | null
└── attachments[]
    ├── attachment_id
    ├── filename
    ├── media_kind
    ├── mime_type
    ├── byte_size
    ├── source
    ├── content_ref / materialized_path / bytes_ref
    ├── sha256
    ├── verified
    └── provenance
```

Przed implementacją należy sprawdzić odpowiedzialności istniejących:

- `latka_jazn/core/message_envelope.py`;
- cognitive/turn envelopes;
- `latka_jazn/core/chat_command_contract.py`;
- ChatGPT adapter/host bridge;
- MCP tools;
- model context compiler;
- model route/capability resolver;
- Ollama adapter;
- memory use/promotion gates.

Nie tworzyć drugiego równoległego systemu envelope, jeśli obecny turn contract można bezpiecznie rozszerzyć.

## Train 16.3.25.A.01+

| Checkpoint | Zakres | Warunek zamknięcia |
|---|---|---|
| `16.3.25.A.01` | audyt host->runtime + reprodukcja attachment-only + projekt kontraktu | znana root cause i wskazany kanoniczny ingress |
| `16.3.25.A.02` | text-only / attachment-only / text+attachments / multi-attachment | wszystkie typy tury reprezentowalne bez placeholdera |
| `16.3.25.A.03` | secure bounded staging w host-level `workspace_runtime` | brak per-release mutable root, path traversal fail-closed |
| `16.3.25.A.04` | text/document extraction + MIME policy + provenance | ekstrakcja ma jawne source/provenance |
| `16.3.25.A.05` | image ingress + capability negotiation | obraz nie trafia do modelu bez jawnego vision capability |
| `16.3.25.A.06` | Ollama multimodal integration | supported vision path działa; text-only fail-closed |
| `16.3.25.A.07` | runtime/model-context/MCP/ChatGPT integration | jeden kanoniczny routing end-to-end |
| `16.3.25.A.08` | memory boundary | zero automatycznej promocji pliku/faktów do L3 |
| `16.3.25.A.09` | regression/security/E2E closure | wymagane testy i manual live acceptance udokumentowane |
| `16.3.25.A.10+` | defect loop P0/P1 przed release closure | każdy finding ma root cause i regresję |

## Finalny release v16.3.26

**Proponowany release name:** `host-attachment-multimodal-ingress-hardening`

Release może zostać zamknięty dopiero, gdy:

- attachment-only przechodzi kanoniczną ścieżkę host->runtime;
- text+attachments i multi-attachment mają zachowany ordering/identity/provenance;
- pliki tekstowe/dokumenty są obsługiwane przez jawne parser/policy gates;
- obrazy są kierowane wyłącznie do backendu z potwierdzonym capability vision;
- unsupported typ/capability kończy się jawnie i fail-closed;
- staging respektuje single canonical runtime workspace v16.0.0;
- załącznik nie staje się automatycznie pamięcią;
- sanitizowane logi/telemetria nie zawierają prywatnej treści plików;
- testy kontraktowe i E2E są powtarzalne;
- aktualny `master` pozostaje bazą PR, a partial A.xx nie są mergowane jako osobne release'y.

## Branch strategy

Jeden branch release train utworzony ze świeżego HEAD `master`, np.:

```text
upgrade/v16.3.26-host-attachment-multimodal-ingress-hardening
```

Checkpointy `A.xx` mogą być commitami/tagami planistycznymi na tym branchu. Nie wykonuje się częściowych merge'y A.xx do `master`.

Po zamknięciu A-series finalny branch zawiera systemowy bump do `16.3.26`, raport techniczny oraz PR do `master`.

## Research registry

Przy implementacji używać aktualnych źródeł pierwotnych/oficjalnych:

- OpenAI / ChatGPT file & image inputs oraz host capabilities;
- OpenAI Responses/API input-file/input-image contracts, jeżeli warstwa API jest używana;
- Ollama vision/multimodal capabilities i format `images`;
- Python `pathlib`, tempfile, MIME/content-type oraz bezpieczna materializacja;
- istniejące repo contracts i testy jako źródło prawdy o bieżącej architekturze.

Wynik wyszukiwarki lub przykład blogowy nie zastępuje dokumentacji oficjalnej.

## Granica testów

Ten dokument jest aktualizacją planistyczną i sam nie uruchamia testów. Implementacja v16.3.26 ma wrócić do normalnego protokołu repo: reprodukcja -> regression test -> fix -> focused suite -> full deterministic suite -> Windows/Ubuntu/live acceptance tam, gdzie realna platforma jest wymagana.
