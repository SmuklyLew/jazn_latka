# Current project state

**Snapshot date:** 2026-09-01  
**Repository:** `SmuklyLew/jazn_latka`

Ten plik jest krótkim overlayem bieżącego stanu. Nie zastępuje `latka_jazn/version.py`, Git ani machine-readable evidence. Po zmianie mastera/aktywnych branchy snapshot należy ponownie zweryfikować.

## Canonical master

Przy tym audycie:

- `master` HEAD: `03f2562cf314ad76242eba14cbcdb499f757918e`;
- canonical runtime line: `16.3.25.3.6-agents-chatgpt-single-startup-source`;
- `AGENTS.md` jest routerem odpowiedzialności;
- startup ChatGPT ma jedno źródło: `AGENTS.md -> AGENTS.chatgpt.md`;
- duplicate packaged `latka_jazn/resources/chatgpt_startup_loader.txt` został usunięty z aktywnego kontraktu;
- Pack Generator v8.7 i package-discovery/provenance hardening są już w master.

Numer bieżącej wersji zawsze czytaj z `latka_jazn/version.py`; powyższa wartość jest wyłącznie datowanym snapshotem.

## Active parallel implementation: Memory Rebuild v4

Branch:

`upgrade/memory-rebuild-v4-consolidation`

Przy tym audycie:

- HEAD: `39317cb23626cb930b05dda68c4a20c88dde6877`;
- względem master: `22 ahead / 7 behind`;
- merge-base: `3983c577bc86ffdf6fa5bae138a4a20120bd9d5c`;
- branch posiada własne nowsze zmiany Memory Rebuild v4, w tym `ProtocolEngine`, `RunManifest`, source-fidelity/union i testy;
- jednocześnie nie zawiera jeszcze siedmiu późniejszych commitów mastera z linii AGENTS/ChatGPT startup.

### Ownership do chwili merge

Dla **bieżącego statusu implementacji Memory Rebuild v4** branch roboczy jest źródłem nowszej informacji niż kopia `PLAN.md/STATUS.md` na masterze.

Dla **AGENTS, startup ChatGPT, ogólnego runtime, package discovery i innych obszarów poza zakresem Memory Rebuild** źródłem jest aktualny master.

Przed PR/merge Memory Rebuild branch musi ponownie zsynchronizować aktualny master i zachować nowe kontrakty `AGENTS.md -> AGENTS.chatgpt.md`. Po synchronizacji należy ponownie uruchomić wymagane testy; wcześniejsze PASS-y nie są automatycznie dowodem po merge mastera.

## Release train

```text
CURRENT MASTER
16.3.25.3.6
    |
    v
ACTIVE PARALLEL
16.3.25.4 Memory Rebuild v4
    |
    v
PLANNED
16.3.26 attachment / multimodal ingress
    |
    v
16.4.0 -> 16.4.2 evidence-aware Polish NLP
    |
    v
16.5.x final source-aware memory verification / attach / recall / acceptance
    |
    v
16.6.0 final convergence of program v16
    |
    v
FUTURE / CONDITIONAL
17.0.0 measured architecture consolidation
```

Kolejny release zaczyna się ze świeżego mastera po merge poprzedniego etapu, chyba że jawnie kontynuowany jest istniejący aktywny branch.

## Branch truth rule

`ahead > 0` nie oznacza automatycznie, że branch jest nowszym systemem.

Branche klasyfikujemy jako:

- `ACTIVE_PRODUCT` — jawnie wskazana niepołączona linia produktu;
- `MERGED` — zakres już obecny na master;
- `SUPERSEDED` — historia implementacji zastąpiona finalnym branchem/PR;
- `BACKUP` — punkt przywracania;
- `ARCHIVE` — materiał audytowy/historyczny;
- `FUTURE` — planowana linia, która nie powinna jeszcze nieść implementacji.

Na dzień snapshotu jedyną jawnie aktywną niepołączoną linią produktu jest `upgrade/memory-rebuild-v4-consolidation`.

## Documentation truth rule

- `docs/project/CURRENT_STATE.md` — bieżący overlay;
- `docs/plans/.../PLAN.md` + `STATUS.md` — właściciel zakresu release;
- `docs/plans/16.6.0-final-convergence/ROADMAP.md` — kolejność całego programu v16;
- `docs/archive/` — historia; nie przepisywać jej do bieżącego stanu;
- datowane audyty zachowują stare SHA/wersje jako provenance.

## Governance gap

Przy snapshotcie GitHub raportuje `master` jako `protected=false`. Finalny gate v16.6 wymaga branch protection/ruleset albo jawnie udokumentowanego równoważnego enforcement/zaakceptowanego wyjątku.
