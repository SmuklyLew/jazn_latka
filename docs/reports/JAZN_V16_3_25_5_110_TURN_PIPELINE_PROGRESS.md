# v110 turn pipeline progress

Status: IN_PROGRESS. Baseline: v109 a41c2fe (PR #319), including the fresh
composition reachability audit fix. v109 remains unmerged.

JaznEngine.process_turn and build_cognitive_frame delegate to TurnOrchestrator
and CognitiveFrameBuilder. Detailed turn work is split into ContextCoordinator,
MemoryCoordinator, AffectCoordinator, DialogueRouter, ResponsePipeline,
ValidationPipeline, RecoveryPolicy and PersistenceCoordinator. The orchestrator
passes one TurnPipelineState through ordered stages. Each next request receives
its own state; no second session or runtime owner is created.

MemoryProbeRequest/Result preserve the existing gated recall context, contract
and diagnostics. AffectRequest/Projection wraps the existing affect runtime;
it is advisory and creates no durable authority. DialogueRouteDecision describes
intent, route, handler and required components, with support distinct from a
probability. ResponsePlan carries required points, forbidden claims and selected
evidence references into model generation without granting fact or memory writes.
RecoveryPolicy owns repair, reasoning regeneration, fallback classification and
route-failure decisions. Validators report evidence and gate outcomes. Phase-2
remains the v109 FinalizationService; no legacy automatic failover is introduced.

The v109 helpers are relocated once to turn_pipeline_support; compatibility
imports retain existing callers. Active test assertions and limits are retained.
New budgets cover the orchestrator and extracted hotspots without raising old
limits. Changed committed tests are archived byte-for-byte.

Validation at this checkpoint:
- component/seam/diagnostic/lifecycle checks: 24 PASS;
- temporal carryover and existing final integrity regressions: 12 PASS;
- pipeline order, stage failure, source constraints and affect/memory role tests:
  PASS in targeted runs;
- Pyright: 0 errors, 1 existing __all__ warning before latest port changes;
- compileall and route graph audit: PASS;
- full local suite: IN_PROGRESS with fresh failures to diagnose, not PASS;
- deterministic v109 snapshot parity: IN_PROGRESS;
- CI Linux/Windows E2E, release-hardening and cleanroom: NOT RUN for v110.

No merge-ready or v111 completion claim is made here. The v111 cutover still needs
ConversationRunner, canonical TurnStateMachine and ordinary-dialogue migration.

Primary architecture source checked 2026-10-06:
https://modelcontextprotocol.io/specification/2026-07-28/basic/transports
MCP transport metadata or a task handle does not establish an application session
owner or replace durable finalization authority.
