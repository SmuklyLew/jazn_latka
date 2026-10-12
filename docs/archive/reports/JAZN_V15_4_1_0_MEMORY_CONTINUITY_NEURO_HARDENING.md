# Jaźń v15.4.1.0 — Memory Continuity Neuro Hardening

**Target:** `v15.4.1.0-memory-continuity-neuro-hardening`

## Cel

Aktualizacja wzmacnia ciągłość pamięci bez utożsamiania dużego archiwum, sidecara,
wake-state i pamięci roboczej. Najważniejsza zasada jest fail-closed dla twierdzeń
o ciągłości, ale fail-soft dla zwykłej rozmowy: brak lub niepełność wake-state nie
ma zerować dostępnego archiwum ani kierować całej rozmowy do ogólnego fallbacku.

## Błąd bazowy

W v15.4.0.1 `MemoryRecoveryPipeline.run()` przekazywał do normalizacji ukryty limit
`12000`. Na rzeczywistej paczce pamięci do normalizacji kwalifikowało się 63 589
rekordów, a pipeline kończył 12 000 rekordów i mógł dalej budować wake-state.
Oznaczało to fałszywie zieloną kompletność.

v15.4.1.0 usuwa ukryty limit. Jawny limit nadal istnieje jako narzędzie
operatora/testowe, ale jego wynik ma status `partial`; nie może zbudować
zweryfikowanego wake-state ani zezwolić na claim pełnej ciągłości.

## Nowy kontrakt continuity-readiness

`latka_jazn.memory.continuity_readiness` rozdziela pięć pojęć:

1. czy L0/conversation archive jest przeszukiwalne;
2. czy normalizacja obejmuje cały kwalifikujący się zbiór źródłowy;
3. czy istnieje jeden zweryfikowany wake-state;
4. czy runtime może użyć wake jako L1;
5. czy runtime może twierdzić o przywróconej ciągłości między sesjami.

Stany degradacji są jawne. `retrieval_only` i `partial_unverified` zachowują
zwykłą rozmowę. Jeśli archiwum jest przeszukiwalne, recall nadal jest dozwolony,
ale bez claimu pełnego wake/continuity. Błędy integralności blokują użycie
niezweryfikowanego snapshotu, nie całe działanie procesu.

## Coverage i wake-state

Każdy `normalization_run` zapisuje:

- `requested_limit`;
- `expected_item_count`;
- `normalized_item_count`;
- `coverage_complete`;
- `coverage_ratio`.

Stare sidecary bez wiarygodnych metadanych coverage są traktowane jako
`normalization_coverage_unverified` do czasu świeżej normalizacji. Wake-state
przenosi swój `normalization_coverage`, a runtime bridge sprawdza zgodność
snapshotu z rekordem źródłowego runu przed hydratacją L1.

## Walidacja na prywatnej dużej pamięci

Test został wykonany w izolowanym katalogu, bez commitowania danych prywatnych i
bez modyfikowania aktywnego runtime. Paczka split-ZIP została zweryfikowana per-part,
a złożony ZIP miał SHA-256:

`601cf45031ea9aff2ef6b07e485ccbb5e5e1f041dc734fcf8e075249c308e7f2`

Wynik pełnego pipeline na wybranych kanonicznych źródłach recovery:

- źródła recovery: recoverable, bez błędów;
- normalizacja: 63 589 / 63 589;
- `coverage_complete=true`, `coverage_ratio=1.0`;
- wake-state: `ready`, 63 589 elementów, 3 aktorów;
- recovered SQLite: `quick_check=ok`, foreign keys = 0;
- sidecar SQLite: `quick_check=ok`, foreign keys = 0;
- runtime bridge: `ready -> hydrated`;
- `continuity_claim_allowed=true` dopiero po pełnej walidacji;
- lokalny czas pełnego recovery+normalization+wake: ok. 17.5 s w środowisku testowym.

Ten pomiar jest dowodem dla tej paczki i tego środowiska, nie uniwersalnym SLA.

## Podstawa badawcza i granica analogii

Projekt wykorzystuje badania jako inspirację architektoniczną, a nie jako dowód,
że moduły software są biologicznymi odpowiednikami struktur mózgu.

- McClelland, McNaughton, O'Reilly (1995), *Why there are complementary learning
  systems in the hippocampus and neocortex*, Psychological Review,
  DOI `10.1037/0033-295X.102.3.419` — szybka pamięć epizodyczna i wolniejsza
  integracja wiedzy uzasadniają rozdział warstw zamiast jednego magazynu.
- Kumaran, Hassabis, McClelland (2016), *What Learning Systems do Intelligent
  Agents Need? Complementary Learning Systems Theory Updated*, Trends in
  Cognitive Sciences, DOI `10.1016/j.tics.2016.05.004` — replay i współpraca
  systemów pamięci są istotne również dla projektowania inteligentnych agentów.
- Klinzing, Niethard, Born (2019), *Mechanisms of systems memory consolidation
  during sleep*, Nature Neuroscience, DOI `10.1038/s41593-019-0467-3` — replay
  i konsolidacja są procesami wieloetapowymi; w Jaźni odpowiada temu wyłącznie
  inżynierska inspiracja: L0 -> sidecar/review -> L1/L2 -> jawnie zatwierdzane L3.
- Park et al. (2023), *Generative Agents: Interactive Simulacra of Human Behavior*,
  UIST/ACM, DOI `10.1145/3586183.3606763` — pamięć, refleksja i planowanie są
  funkcjonalnie rozdzielone i oceniane przez ablacje.
- Packer et al. (2023), *MemGPT: Towards LLMs as Operating Systems*,
  arXiv `2310.08560` — hierarchiczna pamięć i jawne przenoszenie informacji między
  ograniczonym kontekstem a pamięcią zewnętrzną.
- Lewis et al. (2020), *Retrieval-Augmented Generation for Knowledge-Intensive NLP
  Tasks*, arXiv `2005.11401` — jawna pamięć nieparametryczna daje provenance i
  możliwość aktualizacji wiedzy bez polegania wyłącznie na wagach modelu.
- Kirkpatrick et al. (2017), *Overcoming catastrophic forgetting in neural
  networks*, PNAS, DOI `10.1073/pnas.1611835114` — aktualizacja wag przy uczeniu
  sekwencyjnym może niszczyć wcześniej nabytą wiedzę; dlatego ta aktualizacja nie
  używa prywatnej historii do automatycznego fine-tuningu modelu językowego.

## Zasady bezpieczeństwa

- prywatne `memory/`, SQLite, ZIP-y i `workspace_runtime/` nie trafiają do Git;
- recovery odbudowuje nowe SQLite i nie naprawia źródłowej bazy w miejscu;
- częściowa normalizacja nie jest pełną pamięcią;
- przeszukiwalne L0 nie jest tym samym co zweryfikowany wake;
- wake nie jest tym samym co L3;
- L3 nadal wymaga dokładnego SHA manifestu i jawnego `approved_by`;
- brak wake nie jest automatycznie powodem ogólnego fallbacku rozmowy;
- brak dowodu ciągłości blokuje tylko claim ciągłości i użycie niezweryfikowanego kontekstu.
