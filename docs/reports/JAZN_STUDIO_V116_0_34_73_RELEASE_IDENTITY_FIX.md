# Studio Jaźni .73 — release identity consistency (2026-10-24)

## Source-bound failure and diagnosis

The previous .72 source commit `eda9fb036ba3a57396526929e91a065043ce589c`
passed six Windows/Ubuntu Studio matrix configurations and the frozen
PyInstaller packaging job (Actions run 40074595711). Its
`release-hardening` run 40074595730 failed only in the Ubuntu full
deterministic pytest job (3076 PASS / 1 FAIL / 16 SKIPPED).

The exact failing assertion in
`tests/test_single_canonical_workspace_contract.py::test_release_identity_and_release_metadata_accept_unprefixed_version`
required `DISTRIBUTION_VERSION == PACKAGE_VERSION`. Source in
`latka_jazn/version.py` instead held .71 and .72 respectively.
Setuptools derives its distribution version via
`pyproject.toml [tool.setuptools.dynamic]` from
`latka_jazn.version.DISTRIBUTION_VERSION`, so this is a real
package/runtime identity mismatch, not a flaky UI test.

## Correction

The .73 patch sets both identities to `16.3.25.5.116.0.34.73`,
sets `PACKAGE_RELEASE_NAME` to
`studio-part2-release-identity-consistency`, and aligns
`latka_jazn/resources/startup_contract.json` and
`deploy/chatgpt_mcp/deployment.contract.json`. No assertion,
dependency floor, runtime lifecycle, memory or finalization behavior
is weakened. The existing failing test is retained unchanged.

Do not edit `SOURCE_PROVENANCE.json` or `PACKAGE_INTEGRITY_MANIFEST.json`
by hand: the canonical `release-hardening/manifest_sync` owns those
artifacts. After the .73 source is pushed, verify it has synchronized
metadata and full final-source tests have passed. This report documents
the source correction, **not** a claimed green .73 release.

## Merge / user-machine boundaries

PR #416 is stacked above still-draft PR #415. GitHub merge-readiness requires
the lower PR and stack checks/reviews to pass. Neither PR authorizes
production merge solely from automated CI.

The original Studio acceptance gaps remain: full parity of all twelve
legacy studios, native end-to-end Ollama and ChatGPT final acceptance,
host-local MCP framing, real Windows machine acceptance, Qt accessibility,
Linux offline distribution, and Avast vendor security clearance.

Official source for setuptools dynamic metadata:
https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html
