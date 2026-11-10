# ROOT/local_resources — operator-owned installation assets

This directory belongs directly to the verified Jaźń SYSTEM root, next to
`run.py`, `main.py` and `.venv/`. It is not MEMORY and not a daemon workspace.

An explicit JSS first-run action creates the following directories locally:

- `python/` — Python runtime/installer selection and temporary materialization;
- `wheelhouse/` — SHA-256-verified binary wheels, locks and manifests;
- `ollama/` — optional local installation resources for Ollama;
- `models/` — optional Ollama model location, never presumed installed;
- `nlp/` — optional language resources;
- `manifests/` — local provenance and installation receipts.

Only this README belongs to the source repository. Binary wheels, installers,
local environment files, language-model weights, user secrets and MEMORY must
never be committed to Git or included in a SYSTEM ZIP without an explicit
verified release-sidecar contract. The release pipeline must materialize
platform-specific offline dependency sidecars rather than guessing from a
developer machine's installed Python.

`ROOT/.venv/` is created **on the target machine** with Python 3.14. Copying
another machine's ready-made venv is forbidden by the CPython venv contract.

Installation is an explicit operator action. JSS does not download packages or
models inside a conversation turn and does not stop/start the Jaźń daemon.
Existing host-level workspace, MEMORY, PID and checkpoints remain separate.
A prepared .venv or running Ollama backend never proves accepted Jaźń turns.

Sources:
- https://docs.python.org/3.14/library/venv.html
- https://pip.pypa.io/en/stable/cli/pip_install/
- https://docs.ollama.com/
