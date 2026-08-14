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
