# Jaźń v16.3.25.5.87.6.1 — Pyright repair

Patch naprawia wyłącznie kontrakt typów w teście `test_chatgpt_remote_runtime_evidence.py`.

Pyright 1.1.411 zgłaszał cztery błędy, ponieważ `_public_evidence()` świadomie zwraca `dict[str, object]`, a konstruktor `dict(evidence["readiness"])` nie zawężał statycznie typu `object` do mapowania. Dodano jawny `cast(dict[str, object], ...)`.

Semantyka runtime, remote-runtime classifiera, freshness gate i instance binding z v16.3.25.5.87.6 pozostaje bez zmian.
