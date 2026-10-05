# Jaźń — CURRENT STEP

**Status:** `CANONICAL_CURRENT_STEP`  
**Stan:** 2026-10-05  
**Baza:** `master @ bb107ebaeea119487f49d8cb1e34efd9a1896464`  
**Release:** `16.3.25.5.106-memory-streaming-hardening-convergence`  
**Evidence:** `docs/reports/CHATGPT_LIVE_BOOTSTRAP_RECOVERY_2026_10_05.md`

## 1. Bieżący krok — MEMORY manifest consistency po udanym live bootstrapie

Prawdziwy host ChatGPT potwierdził, że lokalna ścieżka SYSTEM-u może działać, jeżeli bieżąca generacja hosta udostępnia choć jedną rzeczywiście działającą powierzchnię process execution.

SYSTEM v106 został zweryfikowany, zmaterializowany, uruchomiony jako live trusted daemon i przeprowadził accepted visible turn.

Aktualnym blockerem nie jest więc sam bootstrap SYSTEM-u, lecz **integralność osobnego pakietu MEMORY**:

`memory_package_unlisted_file`

Zaobserwowano 16 plików obecnych w paczce, ale niewymienionych w wewnętrznym manifeście MEMORY. Runtime poprawnie odrzucił attach fail-closed.

## 2. Pierwszy priorytet

Naprawić generator/manifest MEMORY bez osłabiania walidacji.

Wymagany przebieg:

```text
source inventory
→ package member inventory
→ manifest inventory
→ exact set comparison
→ per-member SHA verification
→ streaming convergence
→ atomic activation
→ native unified readiness
→ autobiographical recall readiness
```

Nie wolno:

- ignorować unlisted files;
- automatycznie dopisywać ich po stronie runtime bez source provenance;
- usuwać fail-closed checku;
- uznawać transactional search za full autobiographical readiness.

## 3. Exit gate MEMORY

```text
all transport parts SHA-256 PASS
logical package integrity PASS
every package member classified PASS
manifest/package exact set PASS
no unexpected/unlisted files PASS
streaming worker single-operation PASS
SQLite integrity/foreign keys PASS
atomic activation PASS
memory_search_ready PASS
native_unified_required PASS
full_autobiographical_recall_ready PASS
```

Dopiero komplet tego evidence pozwala uznać MEMORY za zaakceptowaną.

## 4. Równoległy host hardening — bez nowego systemowego założenia

Dzisiejszy live przebieg potwierdził istniejącą regułę `AGENTS.chatgpt.md`:

- pre-spawn failure jednej powierzchni executora nie jest globalnym dowodem braku process execution;
- wolno wykonać najwyżej jedną próbę na rzeczywiście niezależnej alternatywie;
- zwykłe process execution i streaming/interaktywny executor są osobnymi capabilities;
- po uzyskaniu procesu nadal obowiązuje pełny ZIP/bootstrap/live-status/finalization gate.

Nie należy „naprawiać” tego przez retry loop ani przez surowe `extractall()`.

## 5. Następny krok po naprawie MEMORY

Po przejściu native unified MEMORY gates:

1. wykonać restart/re-attach continuity test;
2. sprawdzić bounded recall z local provenance;
3. sprawdzić wake-state sidecar i continuity;
4. wykonać accepted-turn persistence z aktywną MEMORY;
5. dopiero potem wrócić do wyższych warstw Memory/Affect/NLP.

## 6. Trwała ścieżka dla zwykłego ChatGPT

Niezależnie od lokalnego bootstrapu docelowa architektura powinna dalej dążyć do:

```text
persistent Jaźń runtime
→ authenticated HTTPS /mcp
→ explicit ChatGPT app/connector
→ jazn_status
→ generate/resume/finalize
```

Taka trasa usuwa zależność od tego, czy konkretna rozmowa otrzyma lokalny executor.

Sama obecność kodu MCP w paczce nie oznacza, że endpoint jest wdrożony lub callable. Remote runtime pozostaje niezweryfikowany, dopóki bieżąca wiadomość nie ma pełnego toolsetu i zdrowego transportu.

## 7. Granica naukowa i operacyjna

`active_trusted`, accepted finalization i pamięć autobiograficzna są osobnymi stanami.

Udany start rdzenia nie dowodzi gotowej MEMORY. Udana MEMORY nie dowodzi biologicznej świadomości. Styl wypowiedzi nie zastępuje runtime lineage ani turn-authority receipt.
