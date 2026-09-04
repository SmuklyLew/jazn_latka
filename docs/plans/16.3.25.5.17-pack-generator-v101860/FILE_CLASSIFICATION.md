# Jaźń Pack Generator 10.1.86.0 — file classification

## Audit boundary

This inventory was made before the rewrite from the tracked `master` tree at
`635e9674abe8163a943b922a84b4fe4fb258143f`. It covers files selected by all of
these evidence paths:

- tracked names containing `pack_generator`, `package_distribution`,
  `dependency`, `wheelhouse`, `package_set`, `python_runtime` or
  `memory_package`;
- imports and subprocess entry points used by the active generator sources;
- workflows that build, verify, transport or consume generated packages;
- active tests and immutable archived test snapshots for those contracts.

The three classes are exclusive for maintenance ownership. “Integration” means
that a file is a boundary used by both the generator and the running/distributed
system; it does not mean that the generator owns the system implementation.

Ignored local settings, wheelhouses, environments, caches, SQLite files,
`workspace_runtime` and private memory were inspected only as path classes.
They were not copied, moved or added to Git.

## A. Generator-only

These files implement the operator-facing generator and can be maintained
without changing the runtime package contract:

- `tools/jazn_pack_generator.py` — deterministic public bundled launcher;
- `tools/build_jazn_pack_generator_bundle.py` — canonical launcher builder and
  byte-for-byte freshness check;
- `tools/pack_generator_sources/__init__.py` — active source-set identity;
- `tools/pack_generator_sources/jazn_pack_generator_core.py` — request model,
  CLI and orchestration;
- `tools/pack_generator_sources/jazn_pack_generator_compat.py` — retained
  archive/settings compatibility surface;
- `tools/pack_generator_sources/jazn_pack_generator_runtime.py` — generator-side
  adapter to the system distribution entry point;
- `tools/pack_generator_sources/jazn_pack_generator_ui.py` — Studio UI;
- `tools/pack_generator_sources/archive/pre-v10.1.86.0/README.md` and the exact
  retired `v88`, `v89`, `v89_ui`, `v1001`, `v1001_compat`, `v1001_runtime` and
  `v1001_ui` sources — historical, never imported;
- `docs/runtime/JAZN_PACK_GENERATOR_V87_STUDIO_PORTABILITY.md` and
  `docs/runtime/JAZN_PACK_GENERATOR_V89_CROSS_PLATFORM_STUDIO.md` — historical
  generator designs;
- `tests/test_jazn_pack_generator_two_file_bundle_v88.py`;
- `tests/test_jazn_pack_generator_v1001_public_api_contract.py`;
- `tests/test_jazn_pack_generator_v16311_profiles.py`;
- `tests/test_jazn_pack_generator_v82_contract.py`;
- `tests/test_jazn_pack_generator_v82_dashboard.py`;
- `tests/test_jazn_pack_generator_v84_contract.py`;
- `tests/test_jazn_pack_generator_v88_import_isolation.py`;
- `tests/test_jazn_pack_generator_v88_studio_portability.py`;
- `tests/test_jazn_pack_generator_v89_distribution.py`;
- `tests/test_pack_generator_archive_io_v1638.py`;
- `tests/test_package_generator_release_version.py`;
- every `tests/archive/**/test_jazn_pack_generator*.py` snapshot — immutable
  historical test evidence, not active collection.

`tools/jazn_pack_generator_settings.json` is intentionally not in this list of
tracked files. When present, it is operator-owned ignored state. A transported
two-file setup may place an explicit settings file next to the launcher, but no
local settings file may be archived or committed by this change.

## B. System-only

These files belong to Jaźń runtime behavior. The generator may cause their
public commands to run, but must not duplicate or redefine their policy:

- `latka_jazn/dependencies/audit.py`;
- `latka_jazn/dependencies/environment.py`;
- `latka_jazn/dependencies/process_handoff.py`;
- `latka_jazn/dependencies/release_artifact.py`;
- `latka_jazn/dependencies/runtime.py`;
- `latka_jazn/tools/dependency_studio.py`;
- `tools/Start-JaznDependencyStudio.ps1`;
- `latka_jazn/python_runtime/catalog.py`;
- `latka_jazn/python_runtime/launcher.py`;
- `latka_jazn/python_runtime/vendor.py`;
- `latka_jazn/packaging/memory_package_attach.py`;
- `latka_jazn/packaging/memory_package_contract.py`;
- `latka_jazn/packaging/memory_package_legacy_repack.py`;
- `latka_jazn/packaging/memory_package_manifest.py`;
- `latka_jazn/packaging/memory_package_source.py`;
- `latka_jazn/packaging/memory_package_types.py`;
- `latka_jazn/packaging/package_profiles.py`;
- `latka_jazn/packaging/split_zip_package.py`;
- `latka_jazn/packaging/zip_resource_limits.py`;
- the active dependency/runtime/package tests not listed in sections A or C.

No system-only implementation was moved into the generator bundle. That is the
important boundary preserved from the v8.6 comparison: the launcher carries its
own generator modules, while the selected Jaźń source root remains the authority
for runtime, dependency, archive, memory and release behavior.

## C. Generator ↔ system integration

These files define or verify a contract crossed by generated packages:

- `latka_jazn/version.py` — single Jaźń package/release identity imported by the
  generator;
- `latka_jazn/core/runtime_root.py` — canonical host-level
  `workspace_runtime/local_resources` placement;
- `latka_jazn/dependencies/__init__.py`;
- `latka_jazn/dependencies/common.py` — target descriptor, profile resolution,
  contract schemas and canonical wheelhouse root;
- `latka_jazn/dependencies/wheelhouse.py` — verified native resolution and
  hash-locked cross-target replay;
- `latka_jazn/dependencies/wheelhouse_bootstrap.py` — stdlib-first validation
  handoff;
- `latka_jazn/resources/dependencies/profiles.json` and
  `latka_jazn/resources/dependencies/locks/README.md`;
- the six canonical `latka_jazn/resources/dependencies/locks/core+archive/`
  target locks for Windows/Linux x64 and Python 3.12/3.13/3.14 (native CI is
  their only author);
- `latka_jazn/archive/__init__.py`, `capabilities.py`, `hardened_service.py`,
  `rar_backend.py`, `resource_policy.py` and `service.py` — canonical archive
  creation/security implementation used by the compatibility adapter;
- `latka_jazn/packaging/memory_raw_segmentation.py` — canonical memory split
  policy used by the compatibility adapter;
- `latka_jazn/packaging/package_plan.py`;
- `latka_jazn/packaging/package_set_contract.py`;
- `latka_jazn/packaging/dependency_package_contract.py` — immutable dependency
  sidecar and target-identity boundary;
- `latka_jazn/tools/package_distribution.py` — canonical system/memory/package
  set producer invoked by the generator;
- `latka_jazn/python_runtime/__init__.py`, `bundle.py` and `contract.py` —
  portable interpreter verification and target mapping used by the generator;
- `latka_jazn/tools/python_runtime_studio.py` — canonical runtime bundle
  producer paired with that contract;
- `.github/workflows/dependency-artifacts.yml` — native lock and package
  evidence producer;
- `.github/workflows/package-distribution-cleanroom.yml` — native producer,
  opposite-OS lock replay, clean-room consumer and release-lock persistence;
- `.github/workflows/release-hardening.yml` — deterministic bundle, compile,
  type, test and release gates;
- `docs/tools/JAZN_DEPENDENCY_STUDIO.md`;
- `docs/tools/JAZN_PYTHON_RUNTIME_BUNDLE.md`;
- `docs/runtime/JAZN_PACKAGE_DISTRIBUTION_CONVERGENCE_V163255.md` — historical
  predecessor contract;
- `docs/runtime/JAZN_PACK_GENERATOR_V101860_CROSS_TARGET.md` — current contract;
- `tests/test_dependency_cross_target_materialization_v16325517.py`;
- `tests/test_dependency_host_workspace_v1632555.py`;
- `tests/test_dependency_inventory_name_normalization_v1632551.py`;
- `tests/test_dependency_sidecar_absence_classification_v1632555.py`;
- `tests/test_dependency_studio_repeated_profiles_v1632554.py`;
- `tests/test_dependency_studio_v1632539.py`;
- `tests/test_dependency_unpacked_wheel_bootstrap_v1632555.py`;
- `tests/test_dependency_wheelhouse_override_v1632555.py`;
- `tests/test_independent_memory_package_contract_v2.py`;
- `tests/test_package_distribution_cleanroom_activation_observability_v1632555.py`;
- `tests/test_package_distribution_cleanroom_doctor_semantics_v1632555.py`;
- `tests/test_package_distribution_cleanroom_prestart_contract_v1632553.py`;
- `tests/test_package_distribution_v163255.py`;
- `tests/test_python_runtime_bundle_v16325515.py`;
- `tests/test_single_source_version_manifest_contract.py` and the canonical
  release-metadata checks that prevent generator work from drifting package
  identity.

## Disposition

- Active maintenance names are version-neutral; the version belongs to the
  generated contract, not to Python filenames.
- Retired tracked source modules are moved, unchanged, under
  `archive/pre-v10.1.86.0/`. Deletion is not used.
- Active tests changed by this release have byte-for-byte pre-change copies
  under
  `tests/archive/v16.3.25.5.16-python-runtime-bundle-ci-hardening/`.
- The v8.6 file supplied for comparison remains external read-only evidence; it
  is not copied into the repository. Its useful two-file/in-memory design is
  represented by the new deterministic builder and portability test.
