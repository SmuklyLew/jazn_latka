# Jaźń .91 — release security, profile CAS and Windows cleanroom gates

Status: **working fix branch, not accepted for release**.
Base: `master` at `86b51597a1d5992b011e45e208bd0755fb040453`.
No force-push, history rewrite, production merge or private-memory materialization was attempted.

## Confirmed changes

- Untrack all 741 generated `build/` entries from the branch tree (the canonical
  `latka_jazn/` source tree is retained). Ignore `/build/` in future commits.
- Reject generated `build/` content and **any** `local_private_canon_extension.py`
  from source export plans, integrity manifests, and the canonical release staging.
  Staging fails closed even if a generated copy was committed to Git.
- Bind operator profile migration to the previously approved SHA-256; verify the
  profile again at the final `write_system_config` commit boundary while holding
  the shared cooperating-writer lock. This addresses the previously failing
  `test_canonical_migrator_checks_digest_again_before_write` without deleting
  or relaxing that test.
- Add tests for forbidden artifact paths and private-source aliases; preserve
  separate existing profile concurrency regressions.
- Preserve startup `start.json` and daemon stdout/stderr/event diagnostics from
  ephemeral Windows cleanroom CI on failure. This is evidence capture **not** a
  claim that `daemon_startup_not_ready` is fixed; keep its gate blocking until
  it passes on the actual final SHA.

## P0 history and data containment

The original `ffaab623` commit with the private-named copy remains reachable
in existing Git history. A deletion commit alone does not purge historical
objects, PR refs, forks or clones. **Do not put the old private source content
in issue bodies, CI output, code review comments or public reports**.
Operator must determine whether it contained private information and rotate
any exposed credentials. History rewriting requires separate coordinated
approval, safe backups, `git-filter-repo`, inspection of open PR/clone impact,
and potentially GitHub Support for cached PR refs:
https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository

## Release acceptance still required

- `release-hardening` full deterministic test suite must pass, not merely Pyright.
- `package-distribution-cleanroom` especially Windows x64 Python 3.12 must
  pass without increasing timeout to hide a defect.
- Verify `release_metadata_sync --check` idempotence on latest commit.
- Verify the generated SYSTEM ZIP excludes `build/` and private canon aliases.
- Operator TPA on Windows remains separate for 12 studio pages, local daemon,
  Ollama, MEMORY and actual ChatGPT MCP round-trip.

This branch is a hardening proposal, not proof of total system readiness.
