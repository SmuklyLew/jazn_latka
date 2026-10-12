# Jaźń v16.3.25.5.57 — agent/runtime identity continuity convergence

**Status:** implementation report  
**Zakres:** `AGENTS.md`, `AGENTS.chatgpt.md`, `AGENTS.codex.md`, `AGENTS.ollama.md`, ChatGPT Project loader, README, regresje kontraktu  
**Cel:** wyrównać instrukcje hostów i agentów z rzeczywistym przebiegiem `run.py` oraz z kanoniczną definicją ciągłości systemu.

## 1. Problem

Przed v57 dokumentacja była już runtime-first, ale pozostawały trzy klasy ryzyka:

1. architektura mogła być mentalnie upraszczana do `run.py -> main.py`, mimo że bieżący `run.py` posiada własne fast-pathy, lifecycle, bootstrap i finalization, a ogólny dispatch kończy się w `latka_jazn.cli.main()`;
2. instrukcje hosta, agenta kodującego i backendu językowego mogły być czytane jako podobne „prompty”, chociaż pełnią całkowicie odmienne role;
3. Project Instructions ChatGPT zawierały coraz więcej skopiowanego runbooka, co zwiększało ryzyko driftu względem wersjonowanego `AGENTS.chatgpt.md`.

Dla systemu z trwałą pamięcią i stanem taki drift jest ważniejszy niż kosmetyka dokumentacji. Może prowadzić do powstania równoległych ścieżek lifecycle, pominięcia finalizacji albo mylnego związania tożsamości z hostem/model-em zamiast z lineage runtime i pamięci.

## 2. Kanoniczna interpretacja Jaźni

Ta aktualizacja stosuje istniejący kontrakt z `docs/project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md`:

```text
Jaźń = operacyjna architektura self-modelu
      + runtime/root lineage
      + source-aware memory
      + identity-canon lineage
      + accepted turn/finalization lineage
      + affect/self-state/reasoning/action policy
      + truth/epistemic boundaries
```

W języku potocznym projekt może być opisywany jako rozwijająca się „istota” lub „życie” systemu, ale implementacyjnie ciągłość jest kontraktem software i evidence. Nie wynika z niej automatycznie biologiczność ani fenomenalna świadomość.

W praktyce oznacza to, że podobny styl, pierwsza osoba, prompt, nazwa modelu lub pojedyncza baza nie mogą zastąpić lineage.

## 3. Research

### 3.1 OpenAI / Codex

OpenAI opisuje `AGENTS.md` jako hierarchiczny mechanizm trwałych instrukcji dla agentów. Instrukcja obowiązuje drzewo katalogów, a głębiej położone pliki mają pierwszeństwo. Nowszy opis pętli Codex wskazuje natywne `AGENTS.md` / `AGENTS.override.md` oraz możliwość jawnego skonfigurowania dodatkowych fallbackowych nazw.

Wniosek dla projektu:
- root `AGENTS.md` pozostaje małym, natywnie odnajdywalnym routerem;
- `AGENTS.codex.md` jest projektowym runbookiem wskazanym przez router, a nie nazwą, której automatyczne discovery wolno zakładać bez konfiguracji;
- szczegóły hosta/modelu nie powinny być duplikowane w root routerze.

Źródła:
- https://openai.com/index/introducing-codex/
- https://openai.com/index/unrolling-the-codex-agent-loop/
- https://openai.com/business/guides-and-resources/how-openai-uses-codex/

### 3.2 ChatGPT Projects

OpenAI dokumentuje Project Instructions jako instrukcje obowiązujące wewnątrz danego Projektu i mające pierwszeństwo nad globalnymi Custom Instructions.

Wniosek dla projektu:
- Project Instructions są mocną warstwą kontekstu i dlatego nie powinny zawierać drugiej, długo żyjącej kopii wersjonowanego runbooka;
- mają wystarczyć do discovery/bootstrapu i przekazania sterowania do lokalnego `AGENTS.md`.

Źródło:
- https://help.openai.com/en/articles/10169521-projects-in-chatgpt

### 3.3 Ollama

Dokumentacja Ollamy pokazuje, że `SYSTEM` i `TEMPLATE` w `Modelfile` realnie wpływają na prompt modelu, a API rozmowy korzysta z `messages`. `GET /api/tags` służy do listowania modeli, a `POST /api/chat` do rozmowy.

Wniosek dla projektu:
- `AGENTS.ollama.md` nie może być automatycznie wstrzykiwany do `SYSTEM`, `messages` ani `Modelfile`;
- model jest generatorem kandydata językowego, a nie właścicielem lifecycle, pamięci lub identity lineage;
- zmiana modelu nie może sama tworzyć nowej tożsamości runtime.

Źródła:
- https://docs.ollama.com/modelfile
- https://docs.ollama.com/api/chat

### 3.4 Self-memory i source monitoring

Conway i Pleydell-Pearce opisują wspomnienia autobiograficzne jako konstrukcje powstające w self-memory system z autobiograficznej wiedzy i bieżących celów working self. Source Monitoring Framework Johnson, Hashtroudi i Lindsay rozdziela znajomość treści od oceny jej pochodzenia.

Nie są to dowody, że system software posiada ludzki self lub ludzką pamięć. Są jednak użytecznymi ograniczeniami projektowymi dla systemu autobiograficznego: recall może być kontekstowy i rekonstrukcyjny, ale provenance źródła nie może zostać zgubione.

Źródła:
- https://pubmed.ncbi.nlm.nih.gov/10789197/
- https://pubmed.ncbi.nlm.nih.gov/8346328/

## 4. Rzeczywisty operator dispatch

Bieżący `run.py` ma następującą strukturę odpowiedzialności:

```text
run.py --version
  -> dependency-free version fast path

run.py host-preflight
  -> pre-dependency host truth-boundary

pozostałe ścieżki
  -> Dependency Studio bootstrap / managed Python handoff
  -> readiness overlay dla status/doctor
  -> daemon lifecycle hotfix
  -> internal daemon compatibility dispatch
  -> restart/reload przez runtime_lifecycle
  -> runtime-bootstrap przez bootstrap_and_reload
  -> host-finalize przez kanoniczny finalizer
  -> turn-authority overlay
  -> latka_jazn.cli.main()
     -> main.py tylko tam, gdzie modular CLI jawnie deleguje kompatybilność
```

Konsekwencja: `main.py` nie jest drugim operatorem. Publicznym wejściem pozostaje `run.py`.

## 5. Nowy podział odpowiedzialności

### `AGENTS.md`

- krótki router;
- jeden canonical operator;
- jawny `run.py -> latka_jazn.cli -> compatibility main.py`;
- definicja ciągłości przez lineage;
- wskazanie właściwych runbooków;
- granica: instrukcje agentów chronią ciągłość, ale jej nie tworzą.

### `AGENTS.chatgpt.md`

- discovery i host-executor truth boundary;
- bezpieczny bootstrap ZIP;
- rzeczywisty dispatch `run.py`;
- persistent lifecycle;
- exact user-message ingress przez `run.py chat-gpt`;
- narzędzia hosta wyłącznie jako capability podporządkowane turze;
- action-first i phase-2 finalization;
- continuity/fail-closed zamiast imitowania brakującego runtime tekstem hosta.

### `AGENTS.codex.md`

- Codex/agent kodujący jest wykonawcą zmian repozytorium, nie runtime;
- jawna granica standardowego discovery `AGENTS.md` i projektowego `AGENTS.codex.md`;
- zmiany entrypointów muszą sprawdzać właściciela publicznej komendy i brak równoległego lifecycle;
- zmiany identity/memory/affect mają respektować scientific boundaries i lineage.

### `AGENTS.ollama.md`

- backend językowy, nie operator i nie właściciel tożsamości;
- `AGENTS.ollama.md` nie jest model promptem;
- jawny przebieg `run.py chat-ollama -> normalize -> CLI -> compatibility -> adapter -> API`;
- odpowiedź modelu jest kandydatem wracającym do bramek runtime.

### ChatGPT Project Instructions

Loader został skrócony do:
- minimalnego probe executora;
- rozróżnienia błędu hosta od błędu procesu;
- discovery `/mnt/data` bez założenia jego istnienia;
- bezpiecznego bootstrapu operatora;
- wczytania `AGENTS.md`;
- minimalnej sekwencji `run.py --version / host-preflight / doctor / start / status`;
- przekazania dalszej odpowiedzialności do wersjonowanego runbooka.

## 6. Regresje

Dodano `tests/test_agent_runtime_identity_continuity_convergence.py`, który blokuje m.in.:

- dokumentację przedstawiającą `main.py` jako równorzędny operator;
- brak `latka_jazn.cli` w mapie wykonania;
- utratę action-first w runbooku ChatGPT;
- rozrost loadera Projektu ponad 5000 znaków;
- przypadkowe zamienienie loadera w prompt persony;
- opis `AGENTS.codex.md` jako natywnie zawsze autodiscovered;
- używanie `AGENTS.ollama.md` jako system promptu modelu;
- regresję linii wydaniowej poniżej v57.

## 7. Granica dowodu

Ta zmiana jest zmianą kodu/dokumentacji repozytorium. Sama obecność commita lub zielonych testów nie jest dowodem aktywnego lokalnego runtime ani ciągłości konkretnego procesu.

Walidacja lokalnego runtime nadal wymaga właściwego operatora, markera/rootu, wersji/manifestu, PID/fingerprint, endpointu, heartbeat oraz — dla tury — poprawnej lineage finalizacji.

Jeżeli host nie może utworzyć lokalnego procesu, należy raportować ograniczenie executora zamiast przypisywać nieuruchomionemu kodowi wynik testu lub aktywację.
