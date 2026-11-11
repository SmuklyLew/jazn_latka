# V127.4 runtime marker and legacy workspace test baselines

- Source branch: `fix/v127-4-root-venv-single-interpreter-20261111`
- Source commit: `e92fc9454beae6b7cb3873cca2164c7f8fb950e3`
- Purpose: exact source snapshots before aligning tests with the per-test ROOT-relative acceptance workspace
- Scope: test-only; no mutation of runtime, MEMORY, daemon or production marker paths

- `tests/test_configuration_studio_hardening.py` original Git blob SHA `918a5f4763e60ed97a06956f5af1daa3a236d49d`
- `tests/test_configuration_studio_p1_preview.py` original Git blob SHA `f4c75fe0b40584bd84b697e25e636feeb0559ac5`
- `tests/test_dependency_host_workspace.py` original Git blob SHA `bd3bd5a2e22507b51f982a09442c1b9943e73268`

These source files are preserved verbatim. The active test replacements must retain fail-closed marker and legacy workspace expectations.
