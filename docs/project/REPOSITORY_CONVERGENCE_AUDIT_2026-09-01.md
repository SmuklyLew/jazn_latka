# Repository & documentation convergence audit — 2026-09-01

**Repository:** `SmuklyLew/jazn_latka`  
**Audit base:** `master @ 03f2562cf314ad76242eba14cbcdb499f757918e`  
**Canonical version snapshot:** `16.3.25.3.6-agents-chatgpt-single-startup-source`  
**Purpose:** converge active documentation before continuing the release train to v16.6.0 and formalize a measured v17.0.0 direction without rewriting history.

> The version/SHA above are audit provenance. Current values must always be re-read from Git and `latka_jazn/version.py`.

## 1. Scope and truth hierarchy

This audit treats the repository as a system of record with three different temporal classes:

1. **current** — active `AGENTS*`, code, tests, machine-readable evidence, current-state docs and active plans;
2. **parallel active work** — explicitly owned unmerged release branches;
3. **history** — archive, backup, superseded branches, old plans/reports and patches.

`ahead > 0` is never sufficient to promote an old branch to current product truth.

## 2. Current master findings

At the audit base master already contains:

- responsibility-based `AGENTS.md` routing;
- `AGENTS.chatgpt.md` as the canonical ChatGPT host/runbook path;
- removal of duplicate packaged `latka_jazn/resources/chatgpt_startup_loader.txt`;
- package-discovery/bootstrap hardening;
- Pack Generator v8.7 and portable/split package work;
- stable release/schema metadata semantics.

There were no open pull requests at audit start.

GitHub reported `master` as `protected=false`; this remains an explicit governance gap for the final v16.6 gate.

## 3. Active parallel branch: Memory Rebuild v4

`upgrade/memory-rebuild-v4-consolidation` is not history and must not be flattened into the documentation branch.

Audit snapshot:

- HEAD `39317cb23626cb930b05dda68c4a20c88dde6877`;
- `22 ahead / 7 behind` relative to the audit master;
- merge-base `3983c577bc86ffdf6fa5bae138a4a20120bd9d5c`.

The branch carries real unique scope: ProtocolEngine/Test00→Final, RunManifest, source fidelity/union, archive/test policy and related regressions. It also lacks seven newer master commits, including the current AGENTS/ChatGPT startup convergence.

### Required integration rule

Before Memory Rebuild v4 PR/merge:

1. synchronize the then-current master into the active branch;
2. preserve current `AGENTS.md -> AGENTS.chatgpt.md` startup semantics;
3. resolve version/release metadata through canonical tooling;
4. rerun required focused/full validation after integration;
5. update Memory Rebuild `PLAN/STATUS` from actual post-sync results;
6. do not copy older PASS claims forward without re-execution where the merge can affect them.

This documentation pass intentionally avoids taking ownership of branch-local Memory Rebuild implementation status.

## 4. Documentation drift found

### 4.1 Stale current-line labels

Several active planning documents still contained the audit-era label `16.3.25.3-release-metadata-semantics`. A dated audit may retain that value, but active roadmap/current-state text must not present it as today's release line.

### 4.2 Moved project-wide documents

Some active plans still pointed at compatibility pointers under `docs/plans/` although canonical project-wide documents now live under `docs/project/`. Compatibility pointers are valid for old links, but new/current documentation should prefer canonical paths.

### 4.3 Moved release reports

The repository taxonomy moved historical implementation/research reports to `docs/archive/reports/`, while the active root README and final roadmap still had links to old `docs/reports/...` locations. Active links must be updated; archived documents keep their historical paths unchanged.

### 4.4 Root README accumulated history

The root README had become a long mixed manual with links to historical v15 plans/reports. That makes it compete with `AGENTS*`, current domain docs and the roadmap. It is replaced by a concise map/current architecture entrypoint.

### 4.5 No explicit v17 owner plan

`JAZN_V16_6_TO_V17_PLUS_SYSTEM_EVALUATION.md` already described a v17 direction, but there was no dedicated future/conditional v17 plan owning that scope. A new v17.0 plan is added with a hard entry gate: it does not begin until v16.6 evidence exists.

### 4.6 Historical docs must not be normalized to current paths

Old roadmaps, implementation reports, patches and legacy host documents deliberately retain old names, versions, paths, FAIL/NOT RUN outcomes and abandoned designs. Rewriting them would destroy their value as provenance/change history.

## 5. Research review: are v16.6 -> v17 plans still sensible?

Yes, with one important refinement: **the project should exploit modern LLM capability rather than reimplementing broad generative cognition as a growing set of hand-coded pseudo-psychological modules.**

### Evidence used

- OpenAI, *Harness engineering: leveraging Codex in an agent-first world* (2026): repository knowledge as system of record, short AGENTS map, structured docs and mechanical feedback loops.  
  https://openai.com/index/harness-engineering/
- OpenAI API/current platform: models support tools, vision, structured outputs and agent workflows; model outputs remain probabilistic and still need deterministic application constraints/evals.  
  https://platform.openai.com/docs/quickstart/  
  https://platform.openai.com/docs/api-reference/evals
- OpenAI, *Structured Outputs*: schema-constrained outputs improve interoperability, but structured shape does not guarantee semantic correctness.  
  https://openai.com/index/introducing-structured-outputs-in-the-api/
- Anthropic, *Effective context engineering for AI agents* (2025): context is finite; the useful target is the smallest high-signal context, not prompt accumulation.  
  https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- LongMemEval, ICLR 2025: long-term interactive memory still challenges commercial assistants and long-context LLMs; explicit indexing/retrieval/reading plus time-aware query handling materially helps.  
  https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html
- NIST TEVV/AIRC and agentic evaluation probes: trustworthy agent systems benefit from explicit test/evaluation/verification/validation, grounding evidence and machine-readable audit trails.  
  https://www.nist.gov/artificial-intelligence/ai-research/tevv-athlon-framework-evaluating-ai-systems  
  https://www.nist.gov/programs-projects/building-evaluation-probes-agentic-ai
- OWASP LLM01 Prompt Injection: external documents/web/files must remain untrusted data; least privilege and human approval for high-risk actions are required mitigation layers.  
  https://genai.owasp.org/llmrisk/llm01-prompt-injection/

## 6. Resulting architecture decision

### Keep / strengthen in v16

- deterministic runtime identity and finalization;
- source-aware autobiographical memory and retrieval;
- provenance, claim/evidence boundaries and abstention;
- tool/write/promotion authority outside the model;
- bounded context compiler instead of unbounded memory injection;
- capability negotiation for local/frontier models;
- deterministic CI separated from live-model/private acceptance;
- ablation/A-B evidence for cognitive/affective modules.

### Reframe for v17

v17 should be a **measured consolidation release**, not a feature-explosion release.

The default question becomes:

```text
Does this module add measurable causal value beyond what the LLM + context + tools already provide?
```

If not, merge/remove/demote it to advisory/observability.

### Do not delegate to the LLM

Even with strong frontier models, the model must not become the sole authority for:

- active-runtime identity;
- source truth/provenance;
- durable writes and atomic commit;
- memory promotion/forgetting policy;
- tool privileges;
- security boundaries;
- acceptance status.

## 7. Documentation changes in this convergence pass

The pass creates/updates:

- concise root `README.md`;
- `docs/README.md` taxonomy/current entrypoints;
- `docs/project/README.md`;
- `docs/project/CURRENT_STATE.md`;
- `docs/project/RELEASE_TIMELINE.md`;
- this convergence audit;
- a dated v16.6→v17 research update;
- final v16.6 roadmap/current status;
- explicit future/conditional v17.0.0 plan/status.

`docs/archive/` is deliberately not rewritten.

## 8. Follow-up code debt deliberately not folded into this docs branch

Search still finds historical/current-line code references to `START_CHATGPT_FROM_HERE.txt` in places such as version/repository planning utilities. The active Memory Rebuild branch already modifies at least `version_consistency_audit.py`; changing the same code in a documentation convergence PR would create avoidable cross-branch conflict and turn this into a system patch.

These code references must be reviewed during/after Memory Rebuild master synchronization as a separate code-scoped patch with version bump and full tests. Archive references remain untouched.

## 9. Final audit rule

After this pass, a reader should be able to answer without branch archaeology:

1. what is current master? -> `CURRENT_STATE.md` + Git/version.py;
2. what is being actively developed? -> active branch ownership in `CURRENT_STATE.md`;
3. what is the final v16 program? -> `16.6.0-final-convergence/ROADMAP.md`;
4. what starts after v16? -> conditional `17.0.0-measured-architecture-consolidation/PLAN.md`;
5. where is history? -> `RELEASE_TIMELINE.md` -> `docs/archive/`;
6. what proves a capability? -> current tests/evidence, never a prose claim alone.
