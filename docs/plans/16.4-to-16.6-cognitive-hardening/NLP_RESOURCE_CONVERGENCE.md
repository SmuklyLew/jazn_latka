# v16.4.x — Polish NLP resource convergence and Studio plan

## Status and sequencing

- lifecycle: `PLANNED_AFTER_CURRENT_HOTFIX_GREEN`
- current prerequisite: `16.3.25.3.8-readable-health-check-wake-routing`
- canonical target line: `v16.4.0 -> v16.4.2`
- implementation must start from the then-current `master`; do not blind-cherry-pick historical NLP branches
- research baseline: `docs/nlp/NLP_RESOURCE_CONVERGENCE_RESEARCH.md`

The existing release timeline already reserves v16.4.0–v16.4.2 for evidence-aware Polish NLP, lexical resources and query evidence. This plan makes that scope executable and explicitly adds operator-side resource lifecycle tooling.

## Current code inventory / gaps

Current code already contains:

- `latka_jazn/nlp/providers/optional_morfeusz_provider.py`;
- `latka_jazn/nlp/providers/optional_stanza_provider.py`;
- `latka_jazn/nlp/providers/plwordnet_optional_provider.py`;
- `latka_jazn/nlp/lexical_intelligence.py`;
- `latka_jazn/nlp/language_resource_registry.py`;
- `latka_jazn/nlp/dictionary_readiness.py`;
- `latka_jazn/nlp_reasoning/` adapters/pipeline/diagnostics;
- `tools/bootstrap_polish_reasoning_resources.py` and the PowerShell installer;
- `docs/nlp/POLISH_REASONING_RESOURCE_BOOTSTRAP.md`.

Known convergence gaps to resolve rather than work around:

1. plWordNet provider uses `resources/plwordnet/index.sqlite3`, while the resource bootstrap defines a canonical persistent NLP data root under `latka_jazn/local_resources/nlp` or `LATKA_NLP_DATA_DIR`.
2. `LexicalIntelligenceEngine.source_versions()` records coarse availability labels (`available`, `local-index-if-present/v1`) instead of exact resource version/hash identities; cache invalidation therefore needs hardening before resource updates are trusted.
3. Morfeusz adapters create a default `Morfeusz()` instance but do not expose the active dictionary variant/version as first-class provenance.
4. Current plWordNet `lexical_entries` adapter is useful as a bounded lookup contract, but full graph convergence needs explicit synset/relation identity and import provenance rather than only flattened definitions/JSON relations.
5. The current installer provisions Morfeusz and Stanza but deliberately excludes plWordNet pending license/format review and adapter hardening.
6. Resource registry/readiness, reasoning adapters and dictionary lookup need one canonical resource identity contract instead of parallel best-effort status descriptions.

## v16.4.0 — canonical Polish NLP normalization + resource identity

Deliverables:

- one canonical persistent NLP data root for Morfeusz metadata, Stanza models, plWordNet index and future lexical resources;
- `NLPResourceIdentity`/manifest contract with provider, exact version, variant, source URI/handle, SHA-256, license/rights note, installed_at, activated_at and local path;
- exact active resource identities included in lexical/reasoning cache keys;
- canonical Unicode/case/diacritic normalization remains deterministic and source-preserving;
- resource registry/readiness reports are generated from the same manifests used by runtime providers;
- no network download during ordinary runtime turns.

Acceptance:

- changing a resource version/hash invalidates affected cache entries;
- absent optional resources degrade explicitly and do not create guessed lexical evidence;
- restart preserves the same resource identities;
- `doctor`/NLP audit can distinguish `not_installed`, `installed_unverified`, `verified_inactive`, `active_verified`, `update_available`, `rollback_available`.

## v16.4.1 — NLP Resource Studio + Morfeusz/plWordNet convergence

Add an operator tool, preferably callable from PowerShell and Python:

```text
status
verify
plan-update
update
benchmark
activate
rollback
export-report
```

Studio rules:

- download only after explicit operator action;
- stage outside active resource directories;
- verify archive/path safety, hashes and expected format before activation;
- record license/rights and source provenance;
- benchmark before/after;
- activate atomically only after verification gates pass;
- preserve previous verified resource for rollback;
- emit compact JSON reports for agents/CI so conversation context does not need raw installer logs.

### Morfeusz

- keep official Morfeusz2 + SGJP as the canonical precision baseline unless an evidence-backed decision changes it;
- expose package version and dictionary variant in runtime provenance;
- verify both `analyse()` and `generate()` smoke cases;
- add ambiguity corpus where Morfeusz returns multiple analyses and contextual disambiguation is left to a contextual layer (e.g. Stanza/routing evidence), not guessed by morphology alone;
- support custom dictionary compilation only as a versioned extension profile with source manifest, delta benchmark and rollback.

### Stanza

- pre-download Polish processors explicitly in Studio;
- runtime constructs the pipeline with downloads disabled (`download_method=None` or equivalent pinned behavior);
- keep model directory under the canonical NLP resource root;
- record model/package/resource metadata in the same resource manifest system;
- use contextual POS/lemma/dependency evidence to rank morphology candidates without treating it as external fact truth.

### plWordNet

- add an explicit importer/indexer for a verified CLARIN-PL dataset artifact;
- do not infer a downloadable v5 dataset merely from a v5 publication;
- preserve source version, synset IDs, lexical units and relation types/targets sufficiently for source-aware graph queries;
- expose a read-only runtime provider over the activated index;
- move provider path resolution to the canonical NLP data root while retaining a documented compatibility fallback if needed;
- never redistribute imported data unless the recorded rights/license allow it.

Acceptance:

- Studio can install/update/verify/rollback without editing code;
- runtime does not auto-download;
- same test corpus before/after produces a machine-readable comparison;
- provider provenance identifies exact active resource artifact;
- failed update leaves the previous verified resource active.

## v16.4.2 — query/routing evidence integration

Use verified lexical/morphological/contextual evidence only where it measurably helps:

- intent/routing ambiguity;
- Polish inflection/lemma matching;
- paraphrase/query expansion;
- memory-recall query planning;
- dictionary/lexical questions;
- typo/diacritic normalization.

Regression matrix must include:

- direct query;
- paraphrase;
- inflected variants;
- ambiguity;
- negation;
- temporal wording;
- referential follow-up;
- OOV/unknown words;
- wrong-conversation near-match;
- lexical evidence conflicting with memory provenance;
- wake/presence phrases such as `Obudź się Łatko.` vs explicit technical health-check requests.

No resource may:

- promote derived memory into primary memory;
- turn lexical similarity into identity/continuity evidence;
- override a stronger current-turn/routing truth signal;
- create a biological/subjective claim;
- silently call an online dictionary or grammar service.

## Metrics / green gate

Track at minimum:

- morphology lemma/POS accuracy on the frozen Polish test set;
- contextual disambiguation accuracy;
- OOV/abstention behavior;
- routing intent accuracy, including wake-vs-health regressions;
- query expansion benefit vs wrong-conversation rate;
- plWordNet relation lookup precision on frozen cases;
- cold/warm latency;
- cache invalidation correctness;
- resource provenance completeness;
- zero unexpected network calls in runtime tests.

Every resource change follows:

```text
frozen baseline
-> staged resource/update
-> verification
-> benchmark A/B
-> truth/routing/recall/latency regression checks
-> activate or rollback
```

## Explicit non-goals

- no mass scraping of WSJP/SJP;
- no automatic online LanguageTool use for private conversation turns;
- no replacement of Morfeusz with a custom dictionary without measured evidence;
- no claim that morphology alone performs contextual word-sense disambiguation;
- no dependency on a large lexical resource for basic runtime liveness;
- no NLP implementation work before the current 16.3.25.3.8 hotfix is green.
