# SIWC OAuth foundation — separate from MCP

This patch adds \`latka_jazn/model_adapters/siwc_oauth_flow.py\` as a standalone, opt-in security boundary. It **does not** change the existing \`SiwcPlanUsageAdapter\`, automatically sign in, persist credentials, or select a model. External user consent, a real loopback listener, a durable Windows-protected credential vault and serialized refresh-token rotation are still needed before operator activation.

Features: dynamic-agent registration parameters, host-owned stable UUID4 requirement, fresh state/nonce/S256 PKCE values, exact loopback callback and one-time attempt processing, issued vs returning client ID checks, resource-scoped code-exchange form, verified ID token signature via a maintained PyJWT JWKS client, exact issuer/client audience and nonce, and explicit plan-usage scope. Tokens are returned only as in-process credential objects with non-printing repr. NO MCP token is reused as an SIWC access token.

Operator setup must supply and persist \`ext_agent_host_id\` safely, run a loopback listener bound to \`127.0.0.1\`, invoke the OAuth URL only after explicit user request, POST the code to the documented \`TOKEN_URL\`, and pass the token response to \`verify_token_response\`. Optional \`PyJWT[crypto]\` is needed for signed ID token verification; without it, verification fails closed. Do not write tokens to logs, shell history or GitHub. An external OS-secured credential vault must rotate refresh tokens atomically.

Only then may an operator inject the resulting access token and verified scopes into the existing explicit SIWC model adapter. Ollama remains an independent model route; do not switch automatically on ambiguous provider failures or replay a submitted Jaźń turn.

Formal acceptance still outstanding: callback listener, real OpenAI consent, refresh/revocation, Windows credential vault, account-specific model selection and external live E2E. This is not an assertion of running Jaźń or a tested ChatGPT account.

Sources:
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions
- https://developers.openai.com/siwc/token-sharing-open-source/token-reference
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
- https://developers.openai.com/siwc/website
