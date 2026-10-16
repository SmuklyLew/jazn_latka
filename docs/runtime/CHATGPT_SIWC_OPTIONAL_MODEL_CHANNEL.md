# Jaźń v16.3.25.5.116.0.34.6 — optional Sign in with ChatGPT model channel

**Status:** opt-in implementation and deterministic tests; NOT live OAuth acceptance, not an active ChatGPT host bridge, not proof that Jaźń is running in a ChatGPT conversation.

## Goal and boundaries

Keep the canonical Jaźń core (run.py -> main.py), memory/root lineage and accepted-turn/finalization authority. Add a separate, optional programmatic model channel for open-source/locally hosted Jaźń using Sign in with ChatGPT plan usage (SIWC). It does not replace ChatGPT-hosted generation or the remote MCP route. A model completion is an **untrusted candidate**, not an accepted Jaźń turn.

## Official OpenAI sources (checked 2026-10-16)

- https://developers.openai.com/siwc/token-sharing-open-source
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
- https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery

SIWC plan usage is for eligible OSS/locally hosted integrations and is not an unlimited generic API, or access to ChatGPT chat history. For paid or remotely hosted integrations, review OpenAI's additional requirements.

The trusted OAuth manager must: persist one opaque ext_agent_host_id per host; perform browser authorization-code + PKCE with state and nonce; validate the ID-token signature via JWKS, issuer, audience, expiration and nonce; validate the granted chatgpt.tokens.use.direct scope; handle protected tokens, account switching, refresh, revocation and consent. A login lacking that scope does not enable model inference.

The preview supports POST https://api.openai.com/v1/responses with an OAuth bearer token, store=false, stream=true, an ARRAY of input messages and a model slug from the same authenticated account's GET /v1/models catalog. Only response.completed proves completion. A response.failed may arrive after text deltas.

Disallowed HTTP payload fields include: background, conversation, max_output_tokens, max_tool_calls, metadata, moderation, multi_agent, prompt, prompt_cache_retention, safety_identifier, temperature, top_logprobs, top_p, truncation, user and previous_response_id. Explicit role=system message items are also rejected. The initial adapter intentionally declines tool requests and structured-output requests. It does not claim support for hosted tools such as Code Interpreter or MCP.

## Implemented

- latka_jazn/model_adapters/siwc_plan_usage_adapter.py: pinned official HTTPS Responses endpoint, stdlib SSE framing, completion-only acceptance, bounded stream, no automatic retries, no credential persistence or secret logging.
- factory.py: only explicitly selected adapters siwc / chatgpt_plan_usage / siwc_plan_usage_adapter choose this channel. The existing ChatGPT host bridge, Ollama, MCP, and separate paid OpenAI API are unchanged.
- tests/test_siwc_plan_usage_adapter.py: deterministic negative and positive stream cases, preview wire fields, opt-in/scopes/network gates, rejection of tools and previous_response_id.

No automatic OAuth authorization flow is implemented by this patch. Environment values supplied by an operator are **configuration assertions**, NOT cryptographic OAuth proof. Therefore readiness is not marked live until an actual authorized request succeeds, and even a completed response does not replace Jaźń finalization.

### Explicit operator integration AFTER verified SIWC OAuth

In a private operator-managed process environment set:

    JAZN_MODEL_ADAPTER=siwc
    JAZN_SIWC_OPERATOR_OPT_IN=1
    JAZN_SIWC_MODEL=<slug from this user's model catalog>
    JAZN_SIWC_GRANTED_SCOPES=openid profile email offline_access resource.invoke chatgpt.tokens.use.direct
    JAZN_SIWC_ACCESS_TOKEN=<short-lived authorized OAuth access token>

Do NOT put tokens in source code, committed environment files, shell history, screenshots, CI output, chat messages or issue comments. Use trusted, protected token injection and refresh. The adapter does not read OPENAI_API_KEY, does not install plugins, does not initiate a paid API fallback, and is not selected automatically.

## Host integration acceptance

| Scenario | Outcome |
| --- | --- |
| Missing opt-in/token/granted scope/catalog model | No network call |
| No current Jaźń MCP tool exposure | Existing bounded local fallback applies when host process execution exists |
| Fresh ready MCP toolset | Existing persistent remote runtime wins |
| Host pre-spawn failure | No fake Jaźń activation or package-missing claim |
| SSE failed/incomplete or missing response.completed | No model candidate output |
| SSE completed with text | Model-language result only; Jaźń still authorizes/finalizes |
| No verified native MEMORY | No autobiographical memory claim |
| Host does not preserve process | Session and accepted turn state remain with canonical Jaźń runtime, not SIWC HTTP |

## Required validation

    python -X utf8 -m pytest -q tests/test_siwc_plan_usage_adapter.py
    python -X utf8 -m compileall -q latka_jazn tests main.py run.py
    python -X utf8 -m pytest -q -m "not live_model and not live_mcp"
    python -X utf8 run.py doctor --json
    python -X utf8 run.py package-smoke --profile system --json
    python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --write --json

Release metadata is always generated by the canonical synchronization tool, not handwritten. E2E OAuth consent, current model catalog selection, token refresh, real SSE call and the second/third ChatGPT-hosted Jaźń turns remain live-host acceptance tasks; deterministic mocks are not evidence of these capabilities.

## Deferred (NOT implemented)

A full SIWC OAuth registration/PKCE/JWKS authentication manager, safe persistence and token refresh, model catalog picker, verified integration into per-turn language policy and tested end-to-end finalization. Keep production SIWC disabled until these are independently verified.
