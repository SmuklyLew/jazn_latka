# v116.0.30 — P0B/P2: feedback must change actual response

The classifier already routes the user's report "Nowy czat, a Ty mówisz o jego otwieraniu" as a current-turn correction. However, OrdinaryDialogueHandler previously returned a generic apology or a structured candidate with no corrective requirement.

This version changes both paths:
- deterministic fallback now admits that the current chat already exists and explicitly identifies the misinterpretation, rather than claiming a template was "retracted";
- structured LLM realization adds a narrow instruction for the same correction, preserving existing truth, background and memory limits;
- regression tests cover classifier-to-handler, final fallback text, and the model-facing constraint.

No private conversation is copied to repo. This narrow correction is not a claim of human emotion, live memory continuity or LLM model training. CI and host integration remain required.
