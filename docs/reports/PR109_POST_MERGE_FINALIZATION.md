# PR #109 post-merge finalization

PR #109 was merged before its one-shot finalization workflow committed the validated generator v8.5 changes and removed its temporary workflow files.

This follow-up branch contains the already validated final state:

- package generator v8.5 identity and settings schema;
- provenance schema derived from the packaged root's `version.py`;
- version rebuild v0.2 identity;
- updated v8.2/v8.4 migration guards;
- removal of the temporary patch, trigger, and workflow introduced solely to apply the large-file update.

Validation performed by GitHub Actions before the final commit:

- generator self-test: `ok: true`, generator version `8.5`;
- full non-live test suite: `579 passed`, `1 skipped`;
- Python compilation checks passed.
