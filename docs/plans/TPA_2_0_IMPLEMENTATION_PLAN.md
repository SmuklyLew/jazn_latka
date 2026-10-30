# TPA 2.0 — plan implementacji

Źródło bazowe: `origin/master` / `55948d3813664923ae64c6e24f345369632a1b24`.
Branch: `latka_work/tpa-2-auto-acceptance-history`.
Praca wyłącznie w osobnym worktree; prywatna MEMORY i aktywne procesy pozostają poza zakresem.

Stan checkpointu .94.6.46: etapy I–III / P0–P2 zaimplementowane i wypchnięte.
Aktualizacja .94.6.47: dodano poprawkę serializacji checkpointów P2 (stabilny
hash tożsamości SYSTEM, oddzielenie danych redagowanych od pól strukturalnych)
oraz nowe testy kolizji redaktora. Wyniki CI tej poprawki nie są jeszcze dowodem
PASS; metadane wydania wymagają ostatecznej kanonicznej synchronizacji.

Decyzja operatorska: **rzeczywiste dwie tury Ollama oraz pełne próby
Ollama/reconnect/resume/restart wykonać po merge do master**, nie jako warunek
wcześniejszego ukończenia P3 i poprawek kodu. Przed merge wymagane są testy
syntetyczne, GUI tam gdzie dostępne, regresje, audyt źródeł, dowody CI oraz
jawny wykaz odroczonych odbiorów jako NOT_RUN/BLOCKED (nigdy PASS).
TPA: 149 passed, 1 skipped; package-smoke system: 15/15; metadane sprawdzone
niezależnie. Szersza regresja: 3539 passed, 31 skipped, 1 failed (HTTP MCP
framing). Etap IV / kreator P3 oraz rzeczywiste odbiory pozostają nieukończone.
Szczegółowe dowody i prompt wznowienia zawiera TPA_2_0_CHECKPOINT.md.

1. **P0 / etap I**: niezmienne rewizje raportów, odzyskanie po przerwaniu zapisu,
   odbudowywalny zbiorczy stan 22 scenariuszy, oddzielna regresja/live/pełny odbiór,
   aktualność źródeł i weryfikacja dowodów. Domyślny widok zbiorczy, wybór run_id
   otwiera osobny zakres historii. Testy restartu, korupcji i nieprzesłaniania PASS
   przez NOT_RUN. Commit i potwierdzony push.
2. **P1 / etap II**: resolver master/branch/PR/merge/local/ZIP, dokładny SHA,
   kanoniczna weryfikacja integralności, detached worktree oraz własne zasoby.
   Żadnego przejmowania produkcyjnego daemona. Testy ownership i izolacji.
3. **P2 / etap III**: trwały plan zależności preflight → regresja → live;
   blokowanie zależnych kroków, fazowe timeouty i wznowienie tego samego request_id.
4. **P3 / etap IV**: kreator półautomatyczny, checkpoint planu, niezbędne
   potwierdzenia operatora i dowody z hashami; klawiatura, motyw i rozmiary.
5. **Etap V**: szersza regresja, kanoniczna synchronizacja wersji/metadanych,
   idempotencja, Draft PR do master i CI dla końcowego SHA. Odbiory fizyczne
   Windows/EXE/Ollama raportować oddzielnie; brak wykonania nigdy nie oznacza PASS.

## Walidacja i budżet

Najpierw nowe testy kontraktów oraz istniejące testy TPA, potem odpowiednie testy
integracyjne. Nie zmieniać istniejących testów bez append-only snapshotu.
Po każdym etapie aktualizować `TPA_2_0_CHECKPOINT.md`, commitować i wypychać.
Limit odczytywać narzędziem hosta: start 1% puli 300 minut / 54% tygodnia.
Obowiązkowy checkpoint do 60%, zakaz nowego dużego etapu od 65%, stop przy 70%.
Nie utożsamiać kontekstu z limitem. Nie uruchamiać płatnych API ani agentów.
