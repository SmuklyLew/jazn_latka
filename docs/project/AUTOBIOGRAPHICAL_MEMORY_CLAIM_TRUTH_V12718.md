# Jaźń v127.18 — prawdomówność deklaracji o dostępie do MEMORY

## Zaobserwowany błąd (odbiór v127.17, 2026-11-17)

Po zaakceptowanej pierwszej turze przez `chat-ollama` model odpowiedział,
że „właśnie uruchamia dostęp do swojej pamięci autobiograficznej”,
gdy lokalny status tej samej instancji wskazywał:

- `operational_state=active_ready_system_only`;
- `persistent_memory_present=false`;
- `full_autobiographical_recall_ready=false`;
- `continuity_ready=false`;
- `runtime_write_ready=true`.

Przyjęta odpowiedź nie była dowodem gotowości MEMORY.
Operacyjny zapis nie jest pamięcią autobiograficzną.

## Zakres poprawki

Nowy `latka_jazn/core/autobiographical_memory_claim_guard.py` wykrywa
**jednoznaczne pozytywne deklaracje w pierwszej osobie** dotyczące
dostępu do własnej pamięci/wspomnień. Uwzględnia podstawowe polskie
odmiany, wypowiedzi przeczące, cytaty przykładowe, warunki i
następujące po sobie klauzule rozdzielone „ale”, „jednak” itp.

Przy pozytywnej deklaracji wymaga jednocześnie:

1. istniejącej i włączonej prywatnej MEMORY potwierdzonej przez
   `build_memory_availability_status`;
2. `LivingMemoryGateway.readiness().full_autobiographical_recall_ready is True`;
3. `native_unified_recall_ready is True` oraz wybranego, zaufanego źródła
   w stanie `ready_native*`.

Kontrola jest wykonywana dopiero dla jawnej deklaracji, dlatego normalna
rozmowa bez MEMORY nie powoduje kosztownego odczytu bazy w każdej turze.

Brak pamięci, samo `transactional_tier_search_ready`, sam `RuntimeWrite`,
niepewna tożsamość źródła, brak `JaznConfig` w capture i błąd odczytu
prowadzą do **fail-closed**. Nie generujemy sztucznej, „poprawionej”
wypowiedzi z nową lineage ani nie podmieniamy accepted final.

Weryfikacja działa w dwóch istniejących granicach:
`engine._apply_epistemic_visible_boundary()` przed zapisem/finalizacją
oraz `FinalVisibleReplyCapture.build()` dla niezależnego host-finalized
capture. Pozostała weryfikacja prawdziwości konkretnych wspomnień i
`memory_item_id` należy do `memory_grounded_generation_bridge`.

## Testy

`tests/test_autobiographical_memory_access_claim_truth.py`:

- dokładna fraza zaobserwowana na Windows 11;
- inne sformułowania twierdzące;
- poprawne negacje, hipotetyczne i cytaty (bez nadmiernego blokowania);
- przeciwdziałanie „nie mam…, ale już mam…”;
- brak prywatnej MEMORY i zapobieganie niepotrzebnemu probe;
- `ready_transactional_tier_only` nie dowodzi autobiografii;
- syntetyczna, fizycznie utworzona natywna baza `UnifiedMemoryDatabase`;
- błąd odczytu MEMORY blokuje tylko bezpodstawne roszczenie;
- kontrola przed utworzeniem `FinalVisibleReplyCapture`.

CI: `.github/workflows/autobiographical-memory-truth.yml` na Windows
i Ubuntu z Pythonem 3.12 i 3.14 oraz wcześniej istniejące testy kontraktu
pamięci i epistemic ledger. Wymagane są osobne wyniki *dla końcowego SHA*
oraz pełne release-hardening przed kolejnym odbiorem i scaleniem.

## Granice skuteczności

To deterministyczny, ograniczony klasyfikator deklaracji. Nie oznacza
pełnej analizy semantycznej dowolnego języka, gwarancji nieskończonej
liczby parafraz ani pewności prawdziwości każdej autobiograficznej
opowieści. Mocny dowód gotowości pamięci nadal nie dowodzi, że konkretny
wykorzystany fragment pochodzi z właściwego `memory_item_id`.

**Nie zmieniaj aktywnej instalacji v127.17** ani nie restartuj daemona
na potrzeby samego przejrzenia PR. Najpierw pełne zielone CI na końcowym
SHA, potem odrębna testowa instalacja i dopiero wieloturowy odbiór z
tym samym `session_id`, nowymi `request_id` i bez replayu.
Nie podłączaj historycznej MEMORY automatycznie.

## Zewnętrzne źródła

- NIST AI 600-1, GenAI Profile: https://doi.org/10.6028/NIST.AI.600-1
- OWASP LLM09 Misinformation: https://genai.owasp.org/llmrisk/llm092025-misinformation/
- pytest parametrize: https://docs.pytest.org/en/stable/how-to/parametrize.html
