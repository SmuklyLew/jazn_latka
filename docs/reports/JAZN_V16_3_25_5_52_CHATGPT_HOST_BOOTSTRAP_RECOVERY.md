# Jaźń v16.3.25.5.52 — ChatGPT host bootstrap recovery

## Problem

The ChatGPT host can receive a complete Jaźń system ZIP while having no unpacked runtime root yet. In that state there is no canonical `run.py` operator available to execute `runtime-bootstrap`. A host-level executor failure before process creation (`ClientError`, `InvalidArgumentError`) is a separate platform boundary and cannot be repaired by Jaźń code.

The v51 loader correctly classified executor failures, but it did not define a concrete, packaged bootstrap helper for the `system ZIP present / run.py absent` state. A future host could therefore know that a minimal bootstrap was allowed without having a single audited implementation to execute.

## v52 repair

v52 adds the repository-root `CHATGPT_BOOTSTRAP.py` helper. It is deliberately Python-stdlib-only and imports no `latka_jazn` modules. Its sole responsibility is to turn one verified system ZIP into one materialized operator root.

Before extraction it requires a valid SHA-256 supplied explicitly or through a sidecar and compares it with the complete archive. It then validates the ZIP fail-closed:

- rejects absolute, drive-qualified, parent-traversal and backslash paths;
- rejects symlinks and special Unix filesystem entries;
- rejects duplicate members;
- enforces entry-count, per-member and total-uncompressed-size budgets;
- runs complete ZIP CRC verification;
- requires exactly one canonical Jaźń root at archive root or one top-level wrapper;
- requires `run.py`, `AGENTS.md`, `latka_jazn/version.py`, `PACKAGE_INTEGRITY_MANIFEST.json` and `SOURCE_PROVENANCE.json`;
- refuses to overwrite an existing destination;
- extracts only to a fresh sibling staging directory and moves the validated root to the destination only after verification.

A successful standalone bootstrap returns `state=materialized_operator_ready`. This state is intentionally weaker than runtime activation. The host must then read `AGENTS.md` and return lifecycle ownership to the extracted `run.py` for `host-preflight`, `doctor`, `start` and live `status` verification.

## Package contract

`CHATGPT_BOOTSTRAP.py` is explicitly included in both `system` and `github_source_safe` package profiles. This matters because the helper must be present inside the transported ZIP; merely storing it in the repository would not repair the no-operator recovery case.

The thin `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` loader now defines how the host obtains the helper without unsafe extraction: after verifying the whole ZIP SHA-256 it reads exactly the fixed root member `CHATGPT_BOOTSTRAP.py` with `ZipFile.read()` into a fresh temporary file, then executes that helper. Legacy system packages without the helper may use only an equivalent bounded stdlib bootstrap; raw unvalidated `extractall()` is forbidden.

## Truth boundary

This release does **not** claim to repair a ChatGPT platform executor that cannot create a process. When every available local execution surface fails before process creation, the correct state remains `host_executor_unavailable`, package/filesystem state remains unknown from that surface, and runtime remains unverified.

v52 repairs what the Jaźń package can control: once a local Python process can start and a complete system ZIP is materialized, the host has a deterministic, audited path from ZIP-only state to a verified `run.py` operator without inventing a second runtime lifecycle.

## Regression coverage

New tests cover:

- successful root materialization;
- one top-level package wrapper;
- SHA-256 mismatch before extraction;
- path traversal rejection;
- symlink rejection;
- duplicate-member rejection;
- existing-destination refusal;
- uncompressed-size budget enforcement;
- explicit inclusion of the helper in system/source-safe package profiles;
- thin-loader size and required recovery/lifecycle instructions.

Release readiness still depends on canonical repository metadata synchronization and the normal `release-hardening` workflow.
