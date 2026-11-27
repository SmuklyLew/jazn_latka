# Dedicated private-context scope (.27)

Status: implemented first isolation boundary, **not approved for multi-tenant deployment**. The .26 public owner gate is unchanged and remains mandatory. This release adds an opt-in acceptance profile, not a way to authorize additional public principals on a shared installation.

## Decision and scope

Use one independently verified SYSTEM ROOT, independently protected data directories, and one process/service identity per principal. Reuse canonical stores, shard management, runtime state and LivingMemoryGateway; no second memory schema or alternative runtime lifecycle. No first-use owner assignment, no historical memory migration, no automatic provisioning. Existing installations without the explicit profile retain .26 behavior. Never change a live process's owner or scope.

For isolated acceptance only, set process-local JAZN_PRIVATE_CONTEXT_ISOLATION=dedicated_root and JAZN_PRIVATE_CONTEXT_OWNER_SHA256 to the reviewed principal digest already used by the .26 operator binding. The SYSTEM root must have local_resources and the existing valid .settings_local/public_private_context_owner.json. No real owner identity or private data is included. This environment is trusted operator configuration, not tool arguments or a substitute for authorization. Do not copy the same owner's existing data to another user's root; independent OS ACLs/service accounts and storage are required. The normal .26 gate still applies.

- Canonical MEMORY = ROOT/memory; workspace = ROOT/workspace_runtime. No historical host-root fallback. Explicit conflicting overrides and non-off memory sync are refused, not silently redirected.
- Existing runtime-state and memory path resolvers, operational storage and SQLite shard path selection enforce lexical containment, reject symlinks/reparse points, special files and hardlinked files, including standard SQLite sidecars at audited DB boundaries. Missing children may be created by existing canonical writers. No data copied or modified by scope discovery.
- Canonical LivingMemoryGateway selects only the local scoped SQLite directory and local transactional tier. Nonempty external source environment is rejected; historical source registry is not opened. Validate database paths before structural probes, verify returned source paths before delivery to callers.
- The canonical engine memory-context builder uses only gateway hits in this profile. It does not open legacy episodes/messages, source-file scanner, separate conversation archive reader or raw HTML fallback even on zero hits. Existing presenter and memory recall contract consume the scoped hits with original provenance. Do not infer autobiographical readiness from transactional tier availability.

## Evidence and limits

New deterministic tests use two synthetic roots, the real canonical MemoryStore and MemoryTierStore writes and reopen, real LivingMemoryGateway and engine memory-context/presenter/recall contract. Negative cases cover cross-owner resolution, inherited roots, overrides, external registry and env, hardlinks/reparse/symlinks and sidecars, writer alias and MEMORY off. The test switches the synthetic environment sequentially; this does not prove two live processes, full model execution, authorization of every prompt source or operating-system isolation. Tests never read private MEMORY. No relaxation of .26 gate.

The path checks assume trusted operators and stable filesystem permissions. They are not a race-proof OS sandbox or a defense against a privileged administrator replacing directories/files, bind mounts, copying data or reassigning the owner marker. Independent process identities/ACLs, review of source provenance, and storage isolation are prerequisites. Do not enable multiple principals in one ROOT. Some modules still consume root-relative state directly: wake-state, rest/replay, learning, audit, external model state, additional prompt compilers, raw ingestion, cloud sync and child-process environment propagation need further inventory and live tests. The dedicated profile is not yet a production readiness claim.

Next: validate all remaining path and model-context consumers, explicitly enforce dedicated process identity and separate service permissions, test two independent real daemons and real Ollama with synthetic canaries, restart, failure, finalization and no replay. Keep the .26 public gate until acceptance evidence is complete. Rollback through canonical release process only; never disable public authorization as a workaround.

References: https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html and https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html .
