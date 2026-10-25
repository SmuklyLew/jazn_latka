# Jaźń CI fix v16.3.25.5.116.0.34.75

Base: fix/jazn-studio-local-acceptance-20261024 (PR #415).
Head: fix/jazn-studio-part2-verified-ui-20261024 (PR #416).

## Fixes

- Version Rebuild normalizes CRLF/CR before a multiline regular-expression
  scan, then restores the prior LF/CRLF convention and BOM on output.
- Canonical-version tests use dynamically derived historical fixture values
  rather than old literal current-line identities in active tests.
- Exact pre-change version of the edited active test is archived at
  `tests/archive/test_single_canonical_version_alias_v16_3_25_5_116_0_34_74.py` (append-only, not in active pytest collection).
- Package version bumped to .75; startup and public MCP deployment contracts
  synchronized with release name `studio-version-ci-regression`.
- Existing current-line anti-stale scanners and pytest assertions are intact.

## Acceptance checkpoint

Await CI for latest source and synchronized metadata-only HEAD. Validate
release-hardening, jazn-run-studio Windows/Linux matrix and frozen EXE,
Test Studio governance, Pyright, MCP and other required checks. Never
interpret mergeable=true as successful acceptance. The other part-2
live host model/MCP/Avast/accessibility/legacy parity gates remain open.

Official references:
https://docs.python.org/3/library/re.html
https://docs.python.org/3/library/codecs.html
https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
