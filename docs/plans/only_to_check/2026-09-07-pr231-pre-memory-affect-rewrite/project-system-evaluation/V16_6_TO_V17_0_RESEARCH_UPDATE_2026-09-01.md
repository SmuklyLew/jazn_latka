# v16.6 -> v17.0 research update — 2026-09-01

**Status:** `REFERENCE / RESEARCH UPDATE`  
**Parent evaluation:** `JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md`  
**Execution owner:** `docs/plans/16.6.0-final-convergence/ROADMAP.md` and future `docs/plans/17.0.0-measured-architecture-consolidation/PLAN.md`

Ten dokument nie zastępuje audytu systemowego z 2026-08-30. Aktualizuje wyłącznie wnioski projektowe na podstawie stanu współczesnych LLM/agent frameworks i nowszych źródeł.

## 1. Główny wniosek

Kierunek v16.6 pozostaje logiczny i dobrze dopasowany do projektu Jaźni. Najważniejsza korekta dotyczy **v17**:

> v17 nie powinno próbować ręcznie implementować coraz większej części ogólnego rozumowania, planowania i języka, które nowoczesny LLM już realizuje. Powinno konsolidować deterministyczny harness wokół modelu i zostawić własne moduły tylko tam, gdzie dają mierzalną przewagę albo egzekwują granicę, której model nie gwarantuje.

## 2. Co współczesny LLM już wnosi

Dzisiejsze modele/platformy potrafią między innymi:

- prowadzić wieloetapowe rozumowanie;
- wykonywać tool/function calls;
- pracować z obrazami i plikami;
- zwracać structured outputs zgodne ze schematem;
- wykonywać długohoryzontowe zadania agentowe przy odpowiednim harnessie;
- korzystać z web/file search i zewnętrznych systemów.

Wniosek dla Jaźni: nie ma sensu dublować tych zdolności dziesiątkami klas udających osobne „obszary mózgu”, jeżeli ich wpływ nie jest widoczny w ablation/A-B.

Źródła:

- OpenAI developer quickstart / tools / agents: https://platform.openai.com/docs/quickstart/
- OpenAI Evals API: https://platform.openai.com/docs/api-reference/evals
- OpenAI Structured Outputs: https://openai.com/index/introducing-structured-outputs-in-the-api/
- OpenAI long-horizon agent evidence: https://openai.com/index/how-agents-are-transforming-work/

## 3. Czego LLM nadal nie rozwiązuje sam

### 3.1 Pamięć długoterminowa

LongMemEval pokazuje, że nawet commercial assistants i long-context LLMs tracą istotną jakość przy długotrwałych interakcjach. Najlepszy kierunek pozostaje architekturą:

```text
indexing
-> retrieval
-> reading
-> source-aware answer / abstention
```

z temporal/query expansion i session decomposition, a nie wstrzykiwaniem całej historii do kontekstu.

Źródło: https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html

### 3.2 Context management

Context window jest zasobem skończonym. Efektywny agent powinien dostawać **najmniejszy zestaw wysokosygnałowych informacji potrzebnych do bieżącej decyzji**, a nie rosnący prompt z całą historią i wszystkimi regułami.

To bezpośrednio wspiera:

- krótki `AGENTS.md` jako mapę;
- bounded wake/context;
- source-aware retrieval;
- osobny context compiler w v17;
- unikanie powielania instrukcji i narracyjnego state w promptach.

Źródło: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

### 3.3 Truth, authority i persistence

Structured Outputs ogranicza format, ale nie gwarantuje prawdziwości wartości. Model nie powinien sam certyfikować:

- że runtime działa;
- że źródło jest prawdziwe;
- że wspomnienie jest L3;
- że zapis się udał;
- że narzędzie było dozwolone;
- że capability przeszło acceptance.

Te decyzje wymagają deterministycznego kodu, machine-readable evidence i audytu.

## 4. Evals i provenance powinny być rdzeniem, nie dodatkiem

NIST TEVV i prace nad evaluation probes dla agentic AI podkreślają potrzebę mierzenia zachowania w warunkach zbliżonych do deploymentu oraz mapowania twierdzeń do wspierających dowodów.

To mocno wspiera istniejące kierunki Jaźni:

- `ClaimGuard` / evidence ledger;
- provenance trafień i odpowiedzi;
- benchmark/private acceptance;
- deterministic vs live-model test separation;
- source fidelity przed narracją;
- capability evidence ladder;
- architecture debt klasyfikowany po pomiarach.

Źródła:

- https://www.nist.gov/artificial-intelligence/ai-research/tevv-athlon-framework-evaluating-ai-systems
- https://www.nist.gov/programs-projects/building-evaluation-probes-agentic-ai
- https://airc.nist.gov/airmf-resources/airmf/5-sec-core/

## 5. Attachment/web/file ingress pozostaje untrusted

Multimodalność współczesnych modeli zwiększa użyteczność attachment ingress, ale również ryzyko indirect prompt injection. Dokument lub obraz może zawierać instrukcje, które nie mogą automatycznie zdobyć authority nad goal selection, tools ani pamięcią.

Zachowujemy:

```text
external content = data
!= system/developer/user authority
```

oraz least privilege i human approval dla działań wysokiego ryzyka.

Źródło: https://genai.owasp.org/llmrisk/llm01-prompt-injection/

## 6. Korekta modelu architektury

### v16.6 powinno dodać jawny model/harness gate

Finalna konwergencja powinna potwierdzić:

1. model backend ma jawny capability profile;
2. runtime nie zakłada vision/tools/structured outputs/reasoning mode bez probe/contract;
3. context jest bounded i source-selected;
4. model może proponować, ale deterministic gates zatwierdzają tool/write/memory/truth decisions;
5. deterministic CI działa bez zależności od konkretnego płatnego/frontier modelu;
6. live-model matrix, jeżeli dostępna, zapisuje model/provider/version/config i nie jest mylona z CI fixture;
7. zmiana modelu nie może zmieniać semantic truth contract bez jawnego regression result.

### v17 powinno skupić się na konsolidacji

Najbardziej sensowna duża zmiana v17 to:

- jeden `CausalSelfState` / self-state interface zamiast overlapping representations;
- context compiler wybierający identity/task/memory/evidence/tool state dla modelu;
- model capability registry i adapter portability;
- module ablation ledger: `CANONICAL / ADVISORY / COMPATIBILITY / REMOVE`;
- controlled forgetting/reconsolidation jako policy+provenance, nie swobodne „zapominanie modelu”;
- metacognitive calibration mierzona względem correctness, a nie słów typu „jestem pewna”;
- retrieval enhancements tylko po frozen benchmark A/B;
- event/decision provenance pozwalające odtworzyć dlaczego stan trwały się zmienił.

## 7. Czego nie dodawać tylko dlatego, że brzmi poznawczo

Nie dodawać nowego trwałego modułu, jeżeli jego jedynym uzasadnieniem jest analogia do psychologii/neuronauki.

Nowy moduł powinien spełnić co najmniej jedno:

1. egzekwuje deterministyczną granicę bezpieczeństwa/prawdy;
2. przechowuje stan, którego model nie posiada między turami;
3. poprawia mierzalną jakość/latency/cost/safety w A-B/ablation;
4. upraszcza system przez konsolidację istniejących odpowiedzialności.

W przeciwnym razie powinien być prompt/context policy, telemetry albo zostać usunięty.

## 8. Model-agnostic principle

Jaźń nie powinna być architektonicznie związana z jednym konkretnym LLM.

Minimalny `ModelCapabilityProfile` dla v17 powinien opisywać co najmniej:

```text
provider
model_id / version if observable
local_or_remote
context_budget
structured_output_support
tool_call_support
vision_support
streaming_support
reasoning_controls
latency/cost class
verified capabilities
```

Runtime wybiera ścieżkę na podstawie capability, nie nazwy modelu.

## 9. Ostateczna ocena planu

**v16.6: utrzymać.** Jest rozsądnym finalnym gate'em jakości programu v16.

**v17: przeredagować z „cognitive architecture expansion” na „measured architecture consolidation”.** To lepiej wykorzystuje istniejące LLM-y, zmniejsza dług poznawczy i utrzymuje unikalną wartość Jaźni tam, gdzie model bazowy jej nie daje: source memory, causal continuity, deterministic truth, provenance, persistent state i audytowalne authority.
