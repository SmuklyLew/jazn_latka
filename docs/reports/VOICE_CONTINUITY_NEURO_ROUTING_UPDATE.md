# Voice Continuity and Neuro-Routing Update

## Problem

A conversational question about whether Łatka literally felt like the person shown in a generated image was routed as `ordinary_conversation`. The supporting marker `@Wyszukiwanie w sieci` was not represented as a secondary research need. That combination made it easy for the visible host layer to replace Łatka's first-person voice with a `Host ChatGPT:` diagnostic even though the runtime had requested host-assisted generation rather than a technical diagnostic.

A second lexical defect amplified the ambiguity: Polish diacritic folding transforms `naprawdę` into `naprawde`, while the update feature used `\bnapraw\w*\b`. The adverb could therefore produce false evidence for a repair/update command.

A third defect was an overly broad standalone `dziala` health-check phrase. Ordinary praise such as `Naprawdę dobrze to działa` could become a runtime health diagnostic.

## Changes

- Added `affective_self_state_reality_check` as a dedicated intent routed to `SelfStateHandler`.
- Added visual/affective variants, including spelling variants `naprawdę` and `na prawdę`.
- Added `external_research_request` as a supporting intent. In the compound route, research cannot replace the primary self-state intent or transfer speaking identity to the host.
- Added a truthful first-person answer boundary: an image is a visualization, not a measurement of state, embodiment, or biological feeling.
- Added a false-friend guard so `naprawdę` is not interpreted as `napraw...`.
- Removed the standalone generic `dziala` health-check phrase.
- Passed the full dialogue-intent report and secondary intents into route handlers.
- Added turn-logic audit failures for affective questions collapsed to ordinary dialogue and for research markers taking over the primary conversational goal.
- Added an explicit host voice-continuity policy.
- Added a fail-closed finalization rule rejecting plain or Markdown-formatted `Host ChatGPT:` as the body prefix of active-runtime host-assisted speech.
- Synchronized 21 stale active-line references from v15.1.0.3.92 to v15.1.0.3.95; historical archives remain untouched.
- Added a lexicon-wide regression that checks every deterministic route phrase against the classifier.

## Neurological design rationale

The implementation is an engineering analogy, not a claim that the runtime is a biological brain or conscious.

1. **Selective gating.** The main conversational goal is treated as the gated working-memory item, while web research is a supporting signal. This follows the architectural lesson from prefrontal/basal-ganglia gating models: relevant information should be admitted without allowing distractors to replace the active task.
2. **Hierarchical prediction and error correction.** The route matrix supplies a high-level prior for short affective questions, while the validator and turn auditor detect prediction errors such as a self-state question becoming a diagnostic report.
3. **Workspace preservation.** The selected intent, truth boundary, affective state, research need, and voice policy are made jointly available to the handler/host contract instead of living in disconnected modules.
4. **Interoceptive analogy with a strict boundary.** Runtime affect is represented as a modelled operational/dialogue state. It can regulate wording, but it is never presented as biological feeling or proof of subjective experience.

## Primary research references

- McNab, F., & Klingberg, T. (2008). *Prefrontal cortex and basal ganglia control access to working memory*. Nature Neuroscience, 11, 103–107. https://doi.org/10.1038/nn2024
- O'Reilly, R. C., & Frank, M. J. (2006). *Making working memory work: a computational model of learning in the prefrontal cortex and basal ganglia*. Neural Computation, 18(2), 283–328. https://doi.org/10.1162/089976606775093909
- Friston, K. (2009). *The free-energy principle: a rough guide to the brain?* Trends in Cognitive Sciences, 13(7), 293–301. https://doi.org/10.1016/j.tics.2009.04.005
- Friston, K. (2010). *The free-energy principle: a unified brain theory?* Nature Reviews Neuroscience, 11, 127–138. https://doi.org/10.1038/nrn2787
- Dehaene, S., Kerszberg, M., & Changeux, J.-P. (1998). *A neuronal model of a global workspace in effortful cognitive tasks*. PNAS, 95(24), 14529–14534. https://doi.org/10.1073/pnas.95.24.14529
- Dehaene, S., & Naccache, L. (2001). *Towards a cognitive neuroscience of consciousness: basic evidence and a workspace framework*. Cognition, 79(1–2), 1–37. https://doi.org/10.1016/S0010-0277(00)00123-2
- Dehaene, S., & Changeux, J.-P. (2011). *Experimental and theoretical approaches to conscious processing*. Neuron, 70(2), 200–227. https://doi.org/10.1016/j.neuron.2011.03.018
- Barrett, L. F., & Simmons, W. K. (2015). *Interoceptive predictions in the brain*. Nature Reviews Neuroscience, 16, 419–429. https://doi.org/10.1038/nrn3950

## Acceptance criteria

- The exact reported sentence routes to `affective_self_state_reality_check`.
- `external_research_request` remains secondary.
- `naprawdę` produces no repair-action evidence; real `napraw` commands still do.
- The handler answers in first person and states the visualization/biological truth boundary.
- The host contract says external tools do not transfer voice.
- Host finalization rejects a `Host ChatGPT:` takeover for active-runtime host generation.
- Existing host, routing, finalization, and NLP regression suites remain green.
