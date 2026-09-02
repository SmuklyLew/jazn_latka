# Release timeline / decision index

Ten dokument jest **indeksem**, nie drugim repozytorium raportów. Szczegółowe historyczne raporty pozostają w `docs/archive/`; tutaj zapisujemy ich miejsce w ewolucji systemu i status względem bieżącej linii.

## Jak czytać

- `CURRENT` — bieżący master snapshot; wersję zawsze potwierdź w `latka_jazn/version.py`;
- `ACTIVE` — jawnie rozwijana, jeszcze niepołączona linia produktu;
- `MERGED` — zakres historycznie dostarczony i obecny na master;
- `SUPERSEDED` — rozwiązanie/branch zastąpione późniejszą implementacją;
- `FUTURE` — plan po spełnieniu wcześniejszych gates.

Historyczny raport zachowuje również czerwone wyniki i odrzucone eksperymenty. Nie poprawiamy ich po fakcie na zielono.

## Główne etapy

| Linia | Status | Znaczenie |
|---|---|---|
| v15.4.x | MERGED / historical | task continuity, bounded reasoning, finalization continuity, Rest/Replay/Dream truth boundaries i capability-evidence ladder |
| v15.5 | MERGED / historical | local-first memory; cloud jako transport/durability, nie aktywny filesystem pamięci |
| v16.0.x | MERGED / historical | persistent runtime, liveness, observability, host finalization lifecycle |
| v16.1.x | MERGED / historical | epistemic gates, offline rest, single unified memory runtime, private-memory acceptance infrastructure |
| v16.2.x | MERGED / historical | cognitive-state policy, hard turn-process isolation, retrieval experiments, host-tool provenance |
| v16.3.0–21 | MERGED / historical | branch archaeology, Memory Rebuild Studio, host fallback, memory/runtime convergence |
| v16.3.22 | MERGED | requested root != subject root; A/B/B identity gate |
| v16.3.23 | MERGED | pre-response/persistent lifecycle/finalization/recall E2E |
| v16.3.24 | MERGED | package provenance/bootstrap hardening |
| v16.3.25 | MERGED | Memory Rebuild source-union hardening |
| v16.3.25.1 | MERGED | host-finalization gate / next-turn lifecycle |
| v16.3.25.2 | MERGED | live Voice readiness |
| v16.3.25.3 | MERGED | release/schema metadata semantics rozdzielone od runtime version |
| v16.3.25.3.3 | MERGED | ChatGPT package-discovery/bootstrap repair |
| v16.3.25.3.4 | MERGED | Pack Generator v8.7 / Studio / portable ZIP packaging |
| v16.3.25.3.5 | MERGED | AGENTS role routing by responsibility |
| v16.3.25.3.6 | CURRENT snapshot 2026-09-01 | jedno źródło startupu ChatGPT: `AGENTS.md -> AGENTS.chatgpt.md` |
| v16.3.25.4 | ACTIVE | Memory Rebuild v4 consolidation (`upgrade/memory-rebuild-v4-consolidation`) |
| v16.3.26 | FUTURE | attachment + multimodal ingress |
| v16.4.0–16.4.2 | FUTURE | evidence-aware Polish NLP / lexical resources / query interface |
| v16.5.x | FUTURE | final memory VERIFIED -> ATTACHABLE -> RETRIEVABLE -> ACCEPTED |
| v16.6.0 | FUTURE / final v16 program | final runtime-memory-NLP-affect-cognitive-governance convergence |
| v17.0.0 | FUTURE / conditional | measured architecture consolidation based on v16 evidence |

## Historyczne źródła evidence

### Plans

- `docs/archive/plans/v15/`
- `docs/archive/plans/v16/`
- `docs/archive/roadmaps/`

### Release / implementation / research reports

- `docs/archive/reports/`

Te raporty pokazują zarówno wdrożenia, jak i przypadki `NOT RUN`, FAIL lub świadomego rollback/reject. Na przykład historyczny graph-aware retrieval poprawiał jeden recall metric, ale został odrzucony przy regresji wrong-conversation; taki wynik jest ważną częścią decision logu.

### Reviews i patches

- `docs/archive/reviews/`
- `docs/archive/patches/`
- `docs/archive/tools/`
- `docs/archive/chatgpt_host_legacy/`

## Zasada promowania historii do current docs

Historyczny pomysł nie wraca do aktywnej architektury dlatego, że istnieje w archiwum albo na branchu `ahead`.

Promocja wymaga:

```text
history finding
-> current invariant
-> current code gap
-> regression / measurable hypothesis
-> implementation on fresh current line
-> focused + full validation
-> current report
```

Nie wykonujemy blind cherry-picków szerokich starych branchy.

## Bieżący change-log dokumentacyjny

### 2026-09-01 — documentation convergence

- aktualny `master` ustawiony jako ogólny current system baseline;
- `upgrade/memory-rebuild-v4-consolidation` zachowany jako aktywna równoległa linia ze swoim scope ownership;
- root/docs navigation uproszczone;
- historyczne raporty pozostają w `docs/archive/` i nie są przepisywane;
- finalna roadmapa v16.6 zyskuje model/harness/context/eval boundary dostosowany do możliwości współczesnych LLM;
- v17.0 formalizuje kierunek `measurement-driven architecture consolidation`, a nie rozrost antropomorficznych modułów;
- research update zapisany osobno, aby nie zmieniać provenance system-evaluation z 2026-08-30.
