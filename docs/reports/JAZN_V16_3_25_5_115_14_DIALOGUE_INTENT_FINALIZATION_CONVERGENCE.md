# Jaźń v16.3.25.5.115.14 — dialogue-intent and finalization convergence

## Verified failure and scope

On 2026-10-09 the declarative report “Jaźń nie działa!” was classified as a diagnostic requiring a technical implementation plan. The host exhausted its bounded regeneration budget. A separate read-only question (“Sprawdź teraz, co możemy wiarygodnie naprawić…”) was promoted to a mutating system-update request. The patch separates speech acts and preserves explicit write consent.

## Implemented changes

1. **NLP**: exact imperative “napraw” is an execution signal; infinitive “naprawić” is not. Explicit “Przygotuj aktualizację…” remains executable. Prefix “praw” inside “naprawić” is not a rights query.
2. **Classifier and route registry**: short declarative failures use runtime_failure_report and ordinary dialogue without invented plan requirements. A focused diagnostic question uses just problem and source_origin; full repair plans and behavior diagnostics keep detailed requirements.
3. **Response policy**: technical required components are derived from RouteRegistry, matching the source used by RuntimeAnswerValidator, rather than a divergent separate list.
4. **Finalization**: one bounded regeneration gets a sanitized list of missing component identifiers from the trusted runtime validator, tied to the existing turn; no candidate prose or personal data and no weakening of rejection on exhaustion.
5. **Regression tests**: cover read-only question, negation, legitimate update directives, failure-report acceptance, component agreement, and regeneration guidance.
6. **Version consistency**: startup/deployment contracts, tests and test studio catalog updated to 16.3.25.5.115.14. Five existing active test files have byte-for-byte historical snapshots under tests/archive.

## Non-goals and truth boundary

A local daemon, ZIP validation or installed MCP server are not proof that the ChatGPT host exposes all four canonical tools on this message. Live app binding, authentication and successful accepted display_exact finalization remain separate checks. MEMORY must be independently attached and proven; the patch does not create autobiographical recall. No secret or private memory data was committed.

## Validation and release gates

Run: compileall on active modules; pytest excluding tests/archive and live_model/live_mcp; doctor; package-smoke; release_metadata_sync. CI must check latest commit SHA and any manifest_sync-generated follow-up commit. Do not merge with red or unknown required checks. Tests/archive historical files may contain invalid legacy source; they are not the active suite and must remain immutable.

## Primary external references

- Python regular-expression word boundaries: https://docs.python.org/3/library/re.html
- pytest parametrization: https://docs.pytest.org/en/stable/how-to/parametrize.html
- MCP tools and server/client boundary: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- GitHub latest-commit status checks: https://docs.github.com/en/pull-requests/reference/status-checks
- GitHub Git trees: https://docs.github.com/en/rest/git/trees
