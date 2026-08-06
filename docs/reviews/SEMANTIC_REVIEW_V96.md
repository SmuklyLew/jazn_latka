# Semantic review gate — v15.1.0.3.96

This file records the review boundary for the semantic-routing completion update.

## Automated independent lane

`python -X utf8 -m latka_jazn.tools.semantic_route_audit --root . --json`

The lane uses a scenario corpus separate from the classifier implementation and generates combinations of:

- connector prefixes;
- spelling and phrase variants;
- punctuation and conversational suffixes;
- compound primary and supporting intents.

It must pass before the full deterministic suite in `release-hardening.yml`.

## Human review still required

The automated lane is independent code, not an independent person. Before merge, a human reviewer should verify:

1. connector markers never replace the primary user goal;
2. exactly one host regeneration is allowed;
3. the second invalid host answer fails closed;
4. `.96` accurately identifies the changed runtime behaviour;
5. package finalization occurs only after merge.
