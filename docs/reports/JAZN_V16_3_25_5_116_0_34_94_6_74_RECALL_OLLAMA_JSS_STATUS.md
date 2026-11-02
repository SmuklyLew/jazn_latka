# Jaźń v16.3.25.5.116.0.34.94.6.74 — pamięć, Ollama i JSS

**Gałąź robocza:** `fix/v16.3.25.5.116.0.34.94.6.74-recall-ollama-jss-status`  
**Źródło:** `master@d420fb7bd6c666d65fafe58f1e074abb1e7875c9`  
**Zakres:** kod SYSTEM i testy; bez prywatnej MEMORY, runtime workspace, sekretów i zmian produkcyjnego Cloudflare.

## Dowody operatora z 2026-11-02

- `run.py status --json`: runtime `active_trusted`, `active_ready`, `runtime_core_ready=True`, endpoint identity i heartbeat zweryfikowane. Historyczne pole `daemon.marker.runtime_version_full` wskazywało wydanie `.53`, natomiast bieżący runtime `.73`.
- Ollama API lokalnie zwraca `gemma3:latest`; działająca rozmowa `chat-ollama` została wcześniej zaobserwowana. Samo `/api/tags` nie dowodzi generacji.
- Archiwum: `ready_for_search=True`, 94 504 wystąpień wiadomości; FTS dla pytania o sieć snów zwraca kandydatów.
- W teście `dev-preview`: `ArchiveCandidates=15`, `ArchiveAcceptedHits=0`, pięć innych źródeł `journal_reflection`, `AutobiographicalSources=0`, `truthful_degraded_cannot_answer_directly`.
- Szerokie zapytanie FTS: 20 zwróconych rekordów miało `review_status=unreviewed`, `identity_confidence=0.45`. Żaden nie przeszedł dotychczasowego progu `0.50`.
- Diagnostyka wykazała `Executor=host_bridge` w `--dev-preview`, mimo skonfigurowanej lokalnej Ollamy: klient `chatgpt_dev_preview` w starej implementacji wymuszał most hosta.
- Osobne, zabezpieczone kopie SQLite przeszły `PRAGMA integrity_check=ok` i `foreign_key_check=0`. 75 historycznych wpisów proceduralnych to 25 unikalnych treści po 3 wystąpienia, a bieżące 47 wpisów także zawiera te same 25 treści. Nie ma dowodu utraty odrębnych reguł.

## Poprawki w kodzie

1. `main.py`: jawna flaga `--preview-local-ollama` używana z `--dev-preview` lub `--runtime-preview`. W tym trybie przekazuje do pipeline komendę `--chat-ollama`, a domyślna semantyka host bridge pozostaje bez zmian.
2. `engine.py` i `archive_recall_policy.py`: ograniczony over-fetch FTS przed progiem tożsamości oraz metadane `conversation_archive_search.eligibility` (liczniki przyczyn odrzucenia bez treści wiadomości). Nie obniżono progu `0.50`. Autorzy i wpisy `unreviewed` nadal nie uzyskują automatycznego statusu źródła autobiograficznego.
3. JSS `core.py`: porównanie wersji wydania z żywym endpointem, a nie historycznym polem markera; gotowość rozmowy można dodatkowo potwierdzić jawnym `operational_state=active_ready` plus `runtime_core_ready=True` i `readiness_state=ready`. Nie jest to dowód zaakceptowanej odpowiedzi.
4. JSS `service_visual_state.py` i `view_events.py`: oddzielone stany `ready`, `reachable`, `unknown`, `stopped` i `error`. Brak opcjonalnego MCP/Cloudflare, stare dane i częściowo działająca MEMORY nie stają się automatycznie czerwone. Zielony stan dalej wymaga dowodów dla konkretnej capability.

## Lokalny test na Windows, po zsynchronizowaniu metadanych release

```powershell
$py = "D:\.AI\.venv\Scripts\python.exe"
& $py -X utf8 run.py status --json
& $py -X utf8 run.py --dev-preview --preview-local-ollama "Przypomnij naszą rozmowę o sieci snów"
& $py -X utf8 run.py chat-ollama --ollama-model gemma3:latest
```

**Uwaga:** `--dev-preview` to osobna, jednorazowa tura diagnostyczna. Nie jest dowodem tożsamości aktualnego daemona ani zastępstwem dla `chat-ollama`. Nie używać `--preview-persist` w diagnostyce pamięci.

## Kryteria dalszego odbioru

- [ ] Testy regresyjne i CI zaliczone na aktualnym HEAD.
- [ ] Kanoniczna synchronizacja `PACKAGE_INTEGRITY_MANIFEST.json` oraz `SOURCE_PROVENANCE.json` przez `release_metadata_sync`, bez ręcznych edycji.
- [ ] Odbiór Windows: dwa pytania przez `chat-ollama`, reconnect i dowód accepted finalization.
- [ ] JSS: stan `active_trusted` jest zielony tylko z zgodnym ROOT, wersją i heartbeat; lokalne API Ollama bez testu generacji jest bursztynowe; nieskonfigurowane MCP/Cloudflare są neutralne.
- [ ] Oddzielny audyt tożsamości autorów historycznych wpisów i autoryzowana procedura zatwierdzania. Żaden rekord `identity_confidence=0.45` nie został automatycznie podwyższony.
- [ ] MEMORY: `normalization_stale`, `wake-state` i `full_autobiographical_recall_ready` wymagają oddzielnego operator maintenance na kopiach zweryfikowanych przez właściciela. Nie przeprowadza tego ten patch.
- [ ] Publiczny Cloudflare MCP wymaga właściwego OAuth/Access i poprawnego origin; nie jest publikowany przez zmianę statusów JSS.

## Referencje

- SQLite FTS5: https://www.sqlite.org/fts5.html
- Ollama Chat API: https://docs.ollama.com/api/chat
- GitHub Contents API: https://docs.github.com/en/rest/repos/contents
- `AGENTS.md`, `AGENTS.codex.md`, `AGENTS.ollama.md`, `AGENTS.chatgpt.md`.

**Granica prawdy:** sama gałąź Git i testy syntetyczne nie dowodzą odbioru live Windows, pamięci autobiograficznej, bezpiecznej bramy MCP ani poprawnej finalizacji w ChatGPT.
