# v116.0.29 — Jaźń Studio independent-case intake (P0B / P4)

## Operator command

```powershell
python -X utf8 tools/jazn_studio.py --cognitive-cases D:\\Tests\\jazn_intents.json
```

JSON example (fake/synthetic, not a validated holdout):
```json
{
  "cases": [
    {"name": "case-1", "utterance": "Czy Jaźń działa?", "expected": "runtime_health_check"},
    {"name": "case-2", "utterance": "Przeanalizuj kod źródłowy Jaźni i Łatki", "expected": "self_architecture_audit_request"}
  ]
}
```

File up to 256 KiB, at most 500 cases, no symlinks, no duplicate JSON keys or duplicate case names; no added dependencies, no network access, no daemon started and no memory writes.

Results: intent accuracy, confusion matrix, macro F1, wrong-route count/rate and case names; **no user input utterances are included in output**. Operator is responsible for ensuring anonymization and separate holdout creation. Results never auto-declare generalization or live continuity. This does not replace response-level human review, LongMemEval, or authenticated autobiographical acceptance.

Sources: https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html and https://airc.nist.gov/
