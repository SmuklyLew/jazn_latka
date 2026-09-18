# Jaźń v16.3.25.5.79.2 — prepared-memory validation fixture convergence

## Problem

The large-memory validation fixture called `JaznConfig` while persistent MEMORY was absent,
created the runtime source in operational core state, and only afterwards materialized the
normalization sidecar and tier database under the canonical memory root. The memory
availability detector then correctly observed a non-empty persistent memory tree, so later
config resolution could switch roots inside one fixture.

## Fix

The fixture now materializes an explicit `MEMORY_PACKAGE_MANIFEST.json` marker before
constructing `JaznConfig`. The test therefore models what its name promises: a prepared,
attached persistent-memory installation. Production optional-MEMORY routing is unchanged.

The pre-change active test is preserved byte-for-byte under
`tests/archive/v16.3.25.5.79.1-host-executor-epoch-recovery-ci-convergence/`.

## Truth boundary

This change does not make an empty directory count as memory and does not treat
`workspace_runtime/core_state` as autobiographical memory. It only removes an internally
inconsistent test setup.
