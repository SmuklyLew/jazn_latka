# ChatGPT host finalization verification matrix

| Boundary | Expected behavior | Automated evidence |
|---|---|---|
| Daemon authentication | Every gateway request carries `X-JAZN-Daemon-Token`; missing capability fails closed | `test_gateway_sends_private_daemon_capability_token` |
| Phase-one action | `generate_then_finalize` is a valid intermediate action, not a visible reply or tool error | `test_generation_tool_returns_intermediate_action_not_visible_reply` |
| Continuation secrecy | Token is opaque; plaintext token is not persisted | `test_continuation_token_is_opaque_expiring_and_one_shot` |
| Token lifetime | Expired pending requests move to `expired` and cannot be finalized | `test_expired_continuation_is_quarantined` |
| Replay protection | Consumed token cannot be resolved or reused | `test_continuation_token_is_opaque_expiring_and_one_shot` |
| Immutable binding | Host cannot supply turn, trace, timestamp, author, affect, or contract hash | `test_finalizer_loads_all_immutable_fields_from_pending_store`, `test_mcp_finalizer_schema_rejects_host_supplied_identity_fields` |
| Atomic finalization | Existing `persist_chatgpt_host_visible_reply` path claims, validates, persists, and consumes the pending request | finalizer integration test plus existing host-contract hardening suite |
| Runtime state | Complete phase one is `awaiting_host_finalization`, not a failed or displayable answer | `test_complete_host_contract_is_valid_intermediate_runtime_state` |
| Status truth | Live write readiness may be sourced from authenticated `ping`; missing top-level alias is not false failure | `test_status_reads_runtime_write_readiness_from_live_ping` |
| Runbook | Offline snapshot is non-authoritative; MCP continuation flow is canonical | `AGENTS.chatgpt.md` review and repository instruction checks |

## Required repository checks

- Python compilation of `latka_jazn`, `tests`, `main.py`, and `run.py`.
- Pytest excluding explicitly live model/MCP markers.
- Doctor and system package smoke checks.
- Diff whitespace validation.
- Canonical manifest/provenance synchronization through `release-hardening`; never by manual hash editing.
