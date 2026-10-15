# Jaźń v16.3.25.5.116.0.28 — P0B / P1 / P3 evidence hardening

## Why this patch

The previous intent probe counted only overall accuracy. This conceals failures of small intent classes and provides no wrong-route matrix. The Rest reflection evaluator previously computed scene token overlap against *all* replay records, including inferred/symbolic content and records not cited by the scene, while separately counting one real-source anchor. This could inflate groundedness of synthetic material.

## Implemented

- P0B: `summarize_label_pairs` adds confusion matrix, wrong-route count/rate, per-intent precision/recall/F1 and macro-F1. It is integrated into `evaluate_intents` and thus Jaźń Studio `--cognitive-audit`.
- P1/P3: Rest evaluator computes groundedness only from replay items with a verified truth status AND IDs cited by the scene. Inferred or uncited text cannot increase grounding; diagnostic counters track excluded items. Rest/Replay/Dream remains synthetic and cannot auto-promote to L3.
- New synthetic tests cover misrouted labels, inferred copy with unrelated verified source, and uncited verified source.

## Explicit non-goals

This does NOT authenticate true provenance of attached private MEMORY, calibrate probabilities, certify live source recall, validate real user dialogue through ChatGPT, or establish subjective awareness. `is_real_source_anchor` remains an existing truth-status gate, not proof of a cryptographically authenticated source.

## Release evidence required

Run the canonical Test Studio contract sync, static compile/Pyright, pytest, Windows+Ubuntu CI, Rest controller/replay tests, package manifest sync and final SHA verification. New active test must be registered by the same AST-based Test Studio catalog builder, never by inventing test descriptions.

## Background

- LongMemEval (ICLR 2025): https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html
- NIST AI RMF TEVV: https://airc.nist.gov/
