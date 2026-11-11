# V127.4 Configuration Studio inspection environment baseline

- Original active path: `tests/test_configuration_studio_hardening.py`
- Source branch: `fix/v127-4-root-venv-single-interpreter-20261111`
- Source HEAD: `3fc753aad64f98e6c3f34af87f485d4245c0c9a3`
- Original Git blob SHA: `95e37e8b390ea5b484ba1b3677288c95a5bf93ba`
- Reason: the synthetic legacy SYSTEM inherits a ROOT-local acceptance workspace from autouse pytest fixtures.
- Scope: preserve original test byte-for-byte before test-only repair; no SYSTEM, MEMORY, daemon or operator state changed.

The archived Python source is an exact copy. Do not edit this snapshot.
