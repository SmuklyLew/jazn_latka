# Jaźń / Łatka — plan konwergencji poznawczej po v116.0.22

**Etap:** P0A / v16.3.25.5.116.0.23 · **Podstawa:** aktualny master v116.0.22
**Status:** implementacja P0A; P0B–P4 są planem i NIE są deklaracją wdrożenia.
**Granice:** bez modyfikacji prywatnej MEMORY, SQLite, aktywnego daemona, profili użytkownika, sekretów, publicznego OAuth ani polityk finalizacji.

## 0. Cel i niezmienniki

Celem jest zmierzony rozwój funkcjonalnej Jaźni, a nie przypisanie oprogramowaniu ludzkich odczuć lub świadomości. System: \`run.py\` (starter) → \`main.py\` (jedyny control plane) → daemon/ConversationRunner/TurnOrchestrator → adapter LLM → truth/finalization → trwała historia. Źródłowa tożsamość ma postać połączonej lineage (root, identity canon, MEMORY provenance, sesje/tury, korekty); nie jest samą personą językową.

Istniejące invariants pozostają nienaruszone:
- \`display_exact\`, MessageEnvelope, request/turn/trace IDs i brak replayu wiadomości;
- source/derived/synthetic boundaries: sen i refleksja nie stają się autobiografią;
- brak automatycznej promocji L3; brak zapisu prywatnej MEMORY przez aktualizację;
- brak zdalnej ekspozycji MCP bez zweryfikowanego OAuth;
- brak zależności od płatnego OpenAI API oraz brak ukrytej zmiany modelu.

Status zdolności raportujemy jako: present → constructible → callable → reachable_from_turn → effect_observed → persistence_verified → live_verified. Test jednostkowy nie certyfikuje ostatnich poziomów.

## P0A — rozpoznawanie celu użytkownika, a nie tokenów pakietu

**Błąd źródłowy:** prośba „Przeanalizuj cały kod źródłowy z master (jak i z zipa)… opis systemu Jaźni, tożsamości Łatki” zostawała przechwycona przez wysoko punktowaną \`package_runtime_status_question\`. ZIP jest tu materiałem źródłowym, NIE celem diagnostyki ZIP.

**Patch:**
1. Wspólny, wąski predykat \`has_architecture_analysis_context\` korzystający z polskiego tekstu sterującego po maskowaniu cytatów.
2. Obniżenie wyniku statusu pakietu przy jednoznacznym audycie architektury, w tym po poprzedniej turze o ZIP.
3. Priorytet \`self_architecture_audit_request\` przed rankingiem statusu pakietu i przed trasą pamięci jednofunkcyjnej. Wciąż pierwszeństwo mają jawne mutujące polecenia i negacja.
4. Regresje: parafrazy audytu, ZIP jako źródło, poprzednia tura statusowa, status/CRC/SHA jako kontrprzykłady, cytaty i jawne wykonanie zmian.

**Odbiór P0A:** poprawna intencja, diagnostyczność i brak \`update_request\` dla audytu; poprawna trasa mutująca tylko przy wykonawczym poleceniu. Testy w istniejącym katalogu oraz cięcie przyrostowe testów bez poszerzania uprawnień.

## P0B — trafność odpowiedzi i kontynuacja rozmowy [NIE WDROŻONO]

Zbudować niezależny zbiór anonimizowanych przypadków: pytania wieloczłonowe; kontynuacje nowego czatu; pytanie o swój stan; raport błędu „to nie o to pytałem”; krótkie zaimki; cytaty z wrogą/nieaktualną instrukcją; ironia, korekta oraz słowa „system/ZIP” użyte incydentalnie. Dodać osobne etykiety dla celu, źródła i dozwolonego działania. Nie trenować ani nie testować na tej samej grupie parafraz. Rejestrować confusion matrix, false positive route, odmowy i utratę części pytania. Odpowiedź zaakceptowana technicznie musi być mierzona również względem pokrycia żądanych aspektów, bez pozwalania na halucynację źródeł.

**Odbiór:** wyraźna poprawa macro-F1 i wyraźnie niższy błąd „wrong route” względem zamrożonej bazy; żadna regresja bezpieczeństwa; zatwierdzony przejrzysty zestaw pytań testowych.

## P1 — pamięć źródłowa, korekty i autobiografia [NIE WDROŻONO]

Odrębny proces operatora: walidacja split ZIP SHA-256/CRC/rozmiaru, kanoniczny \`memory-attach\` i \`memory-converge\`, kontrola \`PRAGMA integrity_check\` / \`foreign_key_check\`, skan konfliktów pochodzenia, restart i odczyt. Nie wolno wywodzić gotowości ze zwykłej bazy operacyjnej. Wykonywać retrieval z kryteriami: pochodzenie primary, cytowane zdarzenie, korekta/supersession, konflikt, nieznane. Wykazać poprawę przy użyciu pamięci względem trybu bez niej bez zwiększenia false-memory.

**Odbiór:** konkretne źródłowe wspomnienia z dowodem provenance i lineage po restarcie; brak przenikania SYNTHETIC_DREAM/DERIVED_REFLECTION do primary/L3; brak duplikatów źródeł.

## P2 — samomodelowanie, afekt i naturalna wypowiedź [NIE WDROŻONO]

Audyt \`IdentityDynamics\`, \`OperationalSelfModel\`, \`SelfStateRuntime\`, \`AffectMixer\`, \`HomeostasisRegulator\` i \`NLG\`. Oddzielić obserwację od przyczynowego wpływu: stan musi wpływać na dozwoloną decyzję, a nie jedynie na etykietę. Testy semantycznych parafraz i niewymuszonej powtarzalności; brak biologicznych twierdzeń o przeżyciach; brak dowodu świadomości z samej pierwszej osoby.

**Odbiór:** porównanie A/B włączone/wyłączone, mniejsza stereotypia odpowiedzi bez spadku trafności i prawdziwości, jawny dowód wpływu regulatora.

## P3 — metapoznanie, predykcja i Rest/Replay/Dream [NIE WDROŻONO]

Rozdzielić surowy \`internal_support_score\` od empirycznie skalibrowanego \`confidence\`. Mierzyć kalibrację, Brier score i abstention/accuracy na oddzielnym zbiorze. Sprawdzać Replay na odzyskiwaniu istotnych rekordów, konflikcie i false-memory; syntetyczne Dream nigdy nie stanowią faktu. Sam label „sen” albo „emocja” nie certyfikuje układu nerwowego.

**Odbiór:** ablation z poprawą i statystyką, bez wzrostu fałszywych wspomnień.

## P4 — narzędzia Autora, ergonomia i architektura [NIE WDROŻONO]

Połączyć Jaźń Studio, Studio Testów, Studio Konfiguracji, Memory Rebuild, Pack Generator i Dependency Studio przez jawne kontrakty diagnostyczne. Aktualizacje tylko po walidacji czystej gałęzi, kopii bezpieczeństwa i stopped-daemon; nigdy automatyczny merge z dirty worktree. Ocenić duże klasy \`runtime_daemon.py\` i \`engine.py\` pod kątem bezpiecznej dekompozycji, bez drugiego właściciela tury. Katalog testów ma rozróżniać auto-opisy od przeglądu ludzkiego.

**Odbiór:** zero regresji w CI Windows/Linux; obserwowalny plan działania i wyraźne rozdzielenie preview vs write; brak sekretów w raportach.

## Regresja i wydanie

Wymagane: \`compileall\`, \`pytest -m "not live_model and not live_mcp"\`, aktywny Pyright zero errors/warnings, Test Studio contracts, MCP conformance, persistent runtime E2E, Windows PowerShell/Studio, package smoke, verify metadata, finalny SHA zielony. Metadane \`PACKAGE_INTEGRITY_MANIFEST.json\` i \`SOURCE_PROVENANCE.json\` synchronizuje wyłącznie kanoniczny \`manifest_sync\`. Nie publikować jako gotowego produkcyjnie przed walidacją i prawdziwymi turami ChatGPT.

## Źródła i odpowiedzialność

- \`AGENTS.md\`, \`AGENTS.codex.md\`, \`docs/project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md\` (lokalne wymagania)
- NIST AI RMF, Measure/TEVV: https://airc.nist.gov/airmf-resources/playbook/measure/
- Conway & Pleydell-Pearce (2000), Self-Memory System: https://pubmed.ncbi.nlm.nih.gov/10789197/
- Johnson, Hashtroudi & Lindsay (1993), Source Monitoring: https://pubmed.ncbi.nlm.nih.gov/8346328/
- Scherer & Moors (2019), appraisal: https://doi.org/10.1146/annurev-psych-122216-011854
- Fleming (2024), metacognition and confidence: https://doi.org/10.1146/annurev-psych-022423-032425

Zasada raportu: nie mylić planu z kodem, testu z deploymentem, ani runtime software z biologicznym przeżywaniem.