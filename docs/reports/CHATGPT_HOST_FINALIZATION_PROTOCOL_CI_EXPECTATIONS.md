# CI expectations

The branch is expected to trigger `release-hardening` because it uses the allowed `fix/*` prefix. The workflow should regenerate package metadata through the canonical tool, then run compile, pytest, doctor, and package-smoke gates. Any failing check blocks readiness and must be investigated from its actual job logs.
