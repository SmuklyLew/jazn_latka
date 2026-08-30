# Jaźń v16.3.25.A.01+ -> v16.3.26 — host attachment & multimodal ingress

## Status

**Status:** planned / next release train after Memory Rebuild v4 consolidation.  
**Current master at plan synchronization:** `420b1b6d3bd2b550fbbde1102b57ca2d3f7ba339` / `16.3.25.3-release-metadata-semantics`.  
**Immediate prerequisite:** complete and merge the active `16.3.25.4-memory-rebuild-v4-consolidation` plan, unless a later explicit engineering decision proves the two scopes can be safely reordered.  
**Final system release:** `16.3.26-host-attachment-multimodal-ingress-hardening`.

`16.3.25.A.xx` **nie jest kanoniczną wersją runtime**. Oznaczenia A.xx są checkpointami planistycznymi jednego niezmargowanego release trainu. `latka_jazn/version.py` pozostaje jedynym źródłem wersji systemowej; finalny release tej pracy ma numer `16.3.26`.

Nie wolno zużyć numeru `16.3.26` na Memory Rebuild v4. Konsolidacja Memory Rebuild ma osobny patch-release `16.3.25.4` w bieżącej roadmapie.

## Fundament historyczny v16.0.0

Release v16.0.0 ustanowił jeden host-level `workspace_runtime` i jeden kanoniczny `JAZN_ACTIVE_RUNTIME.json`:

- kod może istnieć w wielu wersjonowanych `active_root`;
- mutable host/process state nie należy do wersjonowanego kodu;
- ingress załączników nie może przywrócić `<active_root>/workspace_runtime` jako równoległego źródła prawdy;
- transient materialization/staging ma używać kanonicznego host-level workspace;
- `workspace_runtime` nie trafia do paczki systemowej ani memory.

Szczegóły: `docs/runtime/SINGLE_CANONICAL_RUNTIME_WORKSPACE.md`.

## Problem

Host/runtime contract jest przede wszystkim tekstowy. Attachment-only nie może być redukowany do pustej wiadomości tekstowej ani sztucznego placeholdera. Docelowo Jaźń ma odbierać:

- text-only;
- attachment-only;
- text + attachment;
- text + wiele attachments;
- pliki tekstowe/kod;
- dokumenty w granicach dostępnych parserów;
- obrazy dla ścieżki multimodalnej.

## Invariants

1. Dokładna treść tekstowa użytkownika nie jest streszczana przed runtime.
2. Załącznik ma jawny kontrakt i provenance.
3. Attachment-only jest legalną turą.
4. Odebranie pliku nie jest równoznaczne z zapisem do pamięci.
5. Promocja do L2/L3 przechodzi istniejące memory/truth/provenance/promotion gates.
6. Mutable staging używa host-level `workspace_runtime`.
7. Ścieżki, nazwy i MIME są nieufne i przechodzą policy gate.
8. Nie ufamy rozszerzeniu zamiast rzeczywistego typu/kontraktu.
9. Staging/cache jest bounded i usuwalny bez utraty trwałej pamięci.
10. Model text-only nie może udawać vision capability.
11. Brak wspieranej ścieżki vision jest fail-closed lub jawnie routed do wspieranego backendu.
12. Attachment ma stabilne identity oraz SHA-256 lub równoważne content identity, gdy bajty są dostępne.
13. Prywatne pliki użytkownika nie trafiają do repo, CI ani sanitized reports.

## Docelowy kontrakt wejścia

Preferowany kierunek to rozszerzenie kontraktu **wejścia tury**:

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

Przed implementacją trzeba sprawdzić odpowiedzialności istniejących:

- `latka_jazn/core/message_envelope.py`;
- turn/cognitive envelopes;
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
| `A.01` | audyt host->runtime + reprodukcja attachment-only + projekt kontraktu | znana root cause i kanoniczny ingress |
| `A.02` | text-only / attachment-only / text+attachments / multi-attachment | wszystkie typy tury bez placeholdera |
| `A.03` | secure bounded staging | brak per-release mutable root; path traversal fail-closed |
| `A.04` | text/document extraction + MIME policy + provenance | jawne source/provenance |
| `A.05` | image ingress + capability negotiation | obraz tylko do potwierdzonego vision backendu |
| `A.06` | Ollama multimodal integration | supported vision path; text-only fail-closed |
| `A.07` | runtime/model-context/MCP/ChatGPT integration | jeden kanoniczny routing E2E |
| `A.08` | memory boundary | zero automatycznej promocji pliku/faktów do L3 |
| `A.09` | regression/security/E2E closure | wymagane testy i live acceptance udokumentowane |
| `A.10+` | defect loop P0/P1 | każdy finding ma root cause i regresję |

## Finalny release v16.3.26

**Release name:** `host-attachment-multimodal-ingress-hardening`

Release może zostać zamknięty dopiero, gdy:

- attachment-only przechodzi kanoniczną ścieżkę host->runtime;
- text+attachments i multi-attachment zachowują ordering/identity/provenance;
- dokumenty przechodzą jawne parser/policy gates;
- obrazy są kierowane wyłącznie do backendu z potwierdzonym vision capability;
- unsupported typ/capability jest fail-closed;
- staging respektuje single canonical runtime workspace;
- attachment nie staje się automatycznie pamięcią;
- sanitized telemetry nie zawiera prywatnej treści;
- testy kontraktowe, security i E2E są powtarzalne;
- finalny branch ma kanoniczny `PACKAGE_VERSION = "16.3.26"`.

## Branch strategy

Po zamknięciu `16.3.25.4` utworzyć jeden branch ze świeżego mastera, np.:

```text
upgrade/v16.3.26-host-attachment-multimodal-ingress-hardening
```

Checkpointy A.xx są commitami/checkpointami planistycznymi tego jednego branchu. Nie wykonuje się częściowych merge'y A.xx jako osobnych release'ów.

## Research registry

Przy implementacji używać aktualnych źródeł pierwotnych/oficjalnych:

- OpenAI / ChatGPT file & image inputs oraz host capabilities;
- OpenAI API input-file/input-image contracts, jeśli warstwa API jest używana;
- Ollama vision/multimodal capabilities;
- Python/OS semantics dla bezpiecznej materializacji, temporary files i path handling;
- aktualne repo contracts i testy.

## Granica testów

Ten dokument jest planem. Sam nie dowodzi implementacji ani PASS. Implementacja v16.3.26 ma przejść normalny protokół repo:

```text
reproduce -> regression test -> fix -> focused suite -> full deterministic suite -> Windows/Ubuntu/live acceptance
```
