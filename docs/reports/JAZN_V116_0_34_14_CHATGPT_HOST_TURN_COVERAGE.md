# Jaźń v16.3.25.5.116.0.34.14 — ChatGPT host turn coverage acceptance

## Diagnosis / platform boundary

A live daemon, verified SYSTEM ZIP, or published MCP tool catalog cannot prove
that ordinary ChatGPT has invoked Jaźń for every message. The ChatGPT
app/plugin/host layer decides whether an MCP action is exposed and invoked.
The repository cannot install an unconditional hook in stock ChatGPT or
silently make one app selection apply to the whole conversation.

Primary sources (checked 2026-10-20):
- OpenAI — Developer mode and MCP apps: https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt
- OpenAI — Connect and test a plugin: https://developers.openai.com/plugins/deploy/connect-chatgpt
- MCP 2026-07-28 release: https://blog.modelcontextprotocol.io/posts/2026-07-28/

## Code changes

1. New read-only latka_jazn/mcp/turn_coverage.py reconciles an independent host
   manifest with accepted Jaźń gate and finalization receipts. It fails closed
   for missing messages, duplicate IDs, digest mismatches, extra receipts,
   unbound turns, mismatched trace/turn IDs or missing accepted finals.
   No raw user text is needed.
2. Public MCP jazn_status labels readiness as backend only. It cannot observe
   whether this ChatGPT message exposed the tools or whether earlier messages
   bypassed MCP.
3. Regression tests verify complete and incomplete manifest coverage, hash
   binding, finalization, unique lineage, and CLI exit semantics.

## Use with a client-controlled host

The host must independently record every message it sends, including greetings
and follow-ups. A manifest derived from daemon logs can silently omit the
exact problem being diagnosed.

Expected manifest (JSON array of objects):
  {"message_id":"host-turn-1","user_text_sha256":"<sha256 of original UTF-8 user text>"}

Observed receipts (JSON array of objects):
  {"message_id":"host-turn-1","gate":<host_pre_response_gate telemetry>,
   "final":<accepted MCP display_exact result>}

Read-only audit command (no message replay):

    python -X utf8 -m latka_jazn.mcp.turn_coverage --expected expected.json --observed observed.json

Exit 0 means every supplied expected turn has a bound and accepted final
receipt; exit 2 means incomplete or invalid coverage. Reports contain IDs,
counts, and generic reason codes rather than raw messages or secrets.
Even on success, chatgpt_platform_auto_routing_verified remains false.
It cannot establish that the host actually supplied all ChatGPT messages.

## Real integration acceptance (outside the repo)

1. Start the operator-owned daemon and verify live readiness, not just a marker.
2. Publish authenticated HTTPS/MCP or configure Secure MCP Tunnel. Never expose
   private daemon, Ollama or MEMORY directly on the public Internet.
3. Register/Refresh the ChatGPT plugin and confirm all four canonical tools
   are callable for the current message. Invoke jazn_status as real evidence;
   a local tools/list PASS is not a ChatGPT host PASS.
4. Send five consecutive messages (including follow-ups) through a client
   where all messages are intercepted at the mandatory host entrypoint.
   Record unique request/turn/trace lineage and accepted finalization.
5. Compare the independent expected host manifest with captured receipts.
   Fail closed on missing/unaccepted messages, and do not attribute such
   responses to Jaźń.
6. Verify test suite, Pyright, release metadata sync, Linux/Windows CI,
   package smoke, recovery, and a real ChatGPT integration.

## Non-goals and remaining blockers

This patch does not create an external app connection, configure OAuth,
change plugin permissions, attach MEMORY, or force the ChatGPT platform to
invoke an app for each message. A hard 100% requirement needs a controlled
conversation entrypoint or an explicit host-provided invocation hook.
Without it, source-level changes can ensure fail-closed behavior after ingress
and offline detection of omissions in an independently supplied transcript,
but cannot intercept platform messages before ingress.

## GitHub Actions Windows regression triage (2026-10-20)

- Release-hardening run [39409300101](https://github.com/SmuklyLew/jazn_latka/actions/runs/39409300101), Windows job 118585889751 originally failed the **unchanged** health-check SLA: `5.06998980000003 < 5.0` was false. The excess was about 70 ms.
- A targeted re-run of the same Windows job and code [succeeded](https://github.com/SmuklyLew/jazn_latka/actions/runs/39409300101): the isolated strict health-check and other targeted Windows tests passed. No assertion, limit, production timeout, or coverage was weakened. This supports transient timing variation, not a proven root cause.
- The separate PowerShell regression run [39409303595](https://github.com/SmuklyLew/jazn_latka/actions/runs/39409303595) failed because its older checked-out test contract catalog was stale. The branch subsequently received automatic Studio Testów contract catalog and release manifest/provenance sync commits; the failing run predates these generated updates.
- Acceptance still requires CI on the synchronized head, particularly PowerShell, Pyright, Ubuntu, Windows and full release-hardening. A previous-run PASS does not attest a later commit. If strict Windows health latency fails repeatedly, investigate stage timings and optimize the runtime instead of relaxing the bound.
