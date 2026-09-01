# NLP resource convergence — research baseline

Status: `PLANNED`, implementation gated behind the current `16.3.25.3.8-readable-health-check-wake-routing` hotfix becoming green.

This document records the external evidence used to plan the next Polish NLP/resource convergence work. It does not activate network access or downloaded resources in the runtime.

## Morfeusz 2 / SGJP

Official source: https://morfeusz.sgjp.pl/

Relevant conclusions:

- Morfeusz 2 is a Polish inflectional analyser and generator. It returns possible morphological interpretations and does not by itself resolve which interpretation is correct from sentence context.
- The official site exposes programmer tools and tools for compiling custom dictionaries.
- The official documentation distinguishes SGJP, Polimorf and historical SIaT resource variants. SGJP is the preferred precision-oriented baseline for current Jaźń morphology work.
- A custom dictionary must be treated as a versioned extension with provenance and benchmark evidence; it must not silently replace the SGJP baseline.

Official background: https://morfeusz.sgjp.pl/doc/about/en

## Stanza

Official source: https://stanfordnlp.github.io/stanza/

Relevant conclusions:

- Stanza provides contextual tokenization, POS, morphology, lemmatization and dependency parsing via chained processors.
- Models can be explicitly pre-downloaded with `stanza.download()` into a chosen model directory.
- Runtime construction can disable automatic downloads with `download_method=None`.
- This matches Jaźń's local-first rule: Studio/operator tooling may provision models, while ordinary conversation turns remain network-free.

Official model download contract: https://stanfordnlp.github.io/stanza/download_models.html

## plWordNet / Słowosieć

Official CLARIN-PL catalogue: https://clarin-pl.eu/

Relevant conclusions:

- CLARIN-PL exposes a downloadable plWordNet 4.5 lexical-conceptual resource (444 MB snapshot in the catalogue).
- CLARIN-PL also contains a 2025 publication describing plWordNet 5.0. A publication describing 5.0 is not equivalent to a verified downloadable 5.0 dataset artifact.
- Studio must therefore distinguish `latest described resource line` from `latest downloadable and verified dataset`.
- Import must preserve resource version, source URL/handle, retrieval timestamp, license/rights metadata, SHA-256 and semantic identity (synsets/relations), rather than flattening data into anonymous definitions.

Catalogue evidence: https://clarin-pl.eu/dspace/browse?type=subject&value=plWordNet

## LanguageTool

Official API documentation: https://languagetool.org/http-api/swagger-ui/

Relevant conclusions:

- LanguageTool is suitable as an optional grammar/style/spelling checker, not as lexical truth or a substitute for Morfeusz/plWordNet.
- The public API is rate-limited and the project's public-API guidance discourages automated production-style use; a self-hosted or explicitly provisioned endpoint is preferable for systematic automation.
- Ordinary Jaźń turns must not silently send conversation text to an external LanguageTool endpoint.

## Integration principles for Jaźń

1. `runtime != installer`: conversation runtime never downloads models/dictionaries.
2. All large NLP resources live under the canonical local NLP data root (`LATKA_NLP_DATA_DIR` / project local resources), not under transient `workspace_runtime`.
3. Every active resource has a manifest containing provider, exact version, variant, local path, source URI, SHA-256, license/rights note and install/update timestamp.
4. Resource updates use staging -> verify -> benchmark -> atomic activation -> rollback capability.
5. Missing optional resources degrade explicitly; no guessed definitions or fake semantic relations.
6. Lexical/morphological evidence may improve routing/query/retrieval, but cannot promote memory truth or identity claims.
7. Cache keys must include exact active resource identities/hashes so an NLP resource update cannot leave stale lexical results looking current.
8. Custom Morfeusz dictionaries are extensions, never silent replacements for the tested SGJP baseline.
9. plWordNet import must preserve graph identity/relations sufficiently for provenance-aware semantic evidence.
10. Routing regressions such as `Obudź się Łatko.` -> technical health-check remain independent acceptance tests; a richer dictionary may not override explicit routing truth contracts.
