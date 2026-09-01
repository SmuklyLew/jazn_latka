# Polish reasoning resource bootstrap

Language models and downloaded dictionaries are persistent local data, not session state. The explicit installer stores them by default under:

```text
<project>/latka_jazn/local_resources/nlp
```

That directory stays next to the Jaźń code but is excluded from Git and release manifests. It is not placed in `workspace_runtime`, because `workspace_runtime` may be recreated for a session. `LATKA_NLP_DATA_DIR`, `-DataDir`, or `--data-dir` may override the default.

The runtime never downloads models during a conversation turn. Installation is explicit:

```powershell
.\tools\Install-JaznPolishReasoningResources.ps1 -Profile core
```

`core` installs the Morfeusz2 wheel from PyPI. `recommended` additionally downloads and validates the Polish Stanza models for `tokenize,pos,lemma,depparse`.

Dry run:

```powershell
.\tools\Install-JaznPolishReasoningResources.ps1 -Profile recommended -DryRun
```

The bootstrap writes `install_manifest.json` only after a real installation. The manifest records providers, versions, local paths and SHA-256 values. Installed providers can then be enabled automatically; missing resources remain a non-blocking, truthfully reported optional capability.

The installer deliberately does not bulk-download WSJP, NKJP, PoliMorf, Walenty or plWordNet. Those resources need separate license/format review and a working adapter before runtime may claim that it uses them.

## Planned convergence after the current hotfix

The next resource lifecycle work is specified in:

- `NLP_RESOURCE_CONVERGENCE_RESEARCH.md` — external-source research baseline;
- `../plans/16.4-to-16.6-cognitive-hardening/NLP_RESOURCE_CONVERGENCE.md` — implementation and acceptance plan.

The canonical target is the already-reserved v16.4.0–v16.4.2 Polish-NLP line. The current `16.3.25.3.8-readable-health-check-wake-routing` hotfix must become green first.

The planned Studio extends this bootstrap rather than bypassing it. It will add explicit resource status/verify/update/benchmark/activation/rollback, exact resource identity/provenance, safe staging and a verified plWordNet importer/indexer. Ordinary Jaźń turns will remain download-free.

A known convergence gap is that the current plWordNet runtime adapter uses `resources/plwordnet/index.sqlite3`, while this bootstrap defines the persistent NLP data root above. The v16.4 resource-identity step must unify path resolution before plWordNet activation is considered canonical.
