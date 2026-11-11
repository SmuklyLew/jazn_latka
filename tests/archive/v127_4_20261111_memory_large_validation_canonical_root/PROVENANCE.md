# V127.4 large MEMORY validation test fixture baseline

- Original active path: `tests/test_memory_large_validation.py`
- Source branch: `fix/v127-4-root-venv-single-interpreter-20261111`
- Source HEAD: `fcffeb1a4aff1a816381017ee01ebfb2054c2ab3`
- Original Git blob SHA: `ad2b4315800c8e8a314b34b75c3f6a37970e3bcd`
- Archived source: `test_memory_large_validation.py`
- Reason: the test used a previous sibling workspace MEMORY path, incompatible with ROOT-relative per-test workspace overrides.
- Scope: synthetic pytest fixture only; the runtime resolver and private MEMORY are not changed.

The archived Python file is a verbatim copy of the original.
