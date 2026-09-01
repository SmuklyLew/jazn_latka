from pathlib import Path

p = Path('tools/_apply_distribution_convergence.py')
s = p.read_text(encoding='utf-8')

# Keep the generated builder template syntactically stable.
old_start = "            return f'''{BEGIN}\\n_CANONICAL_PACKAGE_BUNDLE_MANIFEST"
new_start = '            return f"""{BEGIN}\\n_CANONICAL_PACKAGE_BUNDLE_MANIFEST'
old_end = "{END}\\n'''\n\n\n        def render(original: str) -> str:"
new_end = '{END}\\n"""\n\n\n        def render(original: str) -> str:'
if s.count(old_start) != 1 or s.count(old_end) != 1:
    raise SystemExit('scaffold quote markers not found uniquely')
s = s.replace(old_start, new_start, 1).replace(old_end, new_end, 1)

redundant = '''    # Fix a cosmetic constructor expression immediately; keeping the generated source simple\n    # makes the portable bundle byte-for-byte deterministic.\n    replace_once(\n        "latka_jazn/packaging/package_plan.py",\n        "                        relative if False else relative,\\n",\n        "                        relative,\\n",\n    )\n\n'''
if s.count(redundant) != 1:
    raise SystemExit('redundant constructor cleanup block not found uniquely')
s = s.replace(redundant, '', 1)

fragile = '''    insert_after_import(\n        "latka_jazn/packaging/memory_package_attach.py",\n        "from latka_jazn.memory.session_continuity import SessionContinuityManager\\n" if "from latka_jazn.memory.session_continuity import SessionContinuityManager\\n" in read("latka_jazn/packaging/memory_package_attach.py") else "import zipfile\\n",\n        "from latka_jazn.packaging.memory_transaction import promote_memory_tree\\n",\n    )\n'''
stable = '''    insert_after_import(\n        "latka_jazn/packaging/memory_package_attach.py",\n        "from latka_jazn.memory.runtime_memory_install import initialize_transactional_memory_store\\n",\n        "from latka_jazn.packaging.memory_transaction import promote_memory_tree\\n",\n    )\n'''
if s.count(fragile) != 1:
    raise SystemExit('fragile memory attach insertion block not found uniquely')
s = s.replace(fragile, stable, 1)

# Rendering must be idempotent: replacing the generated block cannot add a blank
# separator on every --write/--check cycle.
old_bundle_insert = r'''            text = text.replace(marker, marker + "\n" + overlay(), 1)'''
new_bundle_insert = r'''            text = text.replace(marker, marker + overlay(), 1)'''
if s.count(old_bundle_insert) != 1:
    raise SystemExit('bundle idempotence insertion marker not found uniquely')
s = s.replace(old_bundle_insert, new_bundle_insert, 1)

# The canonical source map must be a complete closure for every module loaded by
# the portable two-file generator. The first convergence draft replaced the
# historical _BUNDLED_MODULES map but accidentally omitted the archive layer.
source_anchor = '''            "latka_jazn.packaging.package_set_contract": "latka_jazn/packaging/package_set_contract.py",\n'''
source_additions = '''            "latka_jazn.archive.resource_policy": "latka_jazn/archive/resource_policy.py",\n            "latka_jazn.archive.service": "latka_jazn/archive/service.py",\n            "latka_jazn.archive.hardened_service": "latka_jazn/archive/hardened_service.py",\n            "latka_jazn.version": "latka_jazn/version.py",\n            "latka_jazn.archive.capabilities": "latka_jazn/archive/capabilities.py",\n            "latka_jazn.archive": "latka_jazn/archive/__init__.py",\n'''
if s.count(source_anchor) != 1:
    raise SystemExit('canonical bundle SOURCES anchor not found uniquely')
s = s.replace(source_anchor, source_anchor + source_additions, 1)

# --check must reject a semantically incomplete generated bundle, not only a
# byte-stale one. This permanently catches the regression that produced
# KeyError: latka_jazn.archive.service.
execute_anchor = '''        def execute(*, check: bool) -> int:\n            current = GENERATOR.read_text(encoding="utf-8")\n            wanted = render(current)\n            if check:\n'''
execute_replacement = '''        def execute(*, check: bool) -> int:\n            current = GENERATOR.read_text(encoding="utf-8")\n            wanted = render(current)\n            load_targets = set(re.findall(r'_load_bundled_module\\("([^\"]+)"(?:,\\s*package=True)?\\)', wanted))\n            missing_targets = sorted(load_targets - set(SOURCES))\n            if missing_targets:\n                print("Pack Generator bundle is semantically incomplete; missing canonical sources: " + ", ".join(missing_targets))\n                return 1\n            if check:\n'''
if s.count(execute_anchor) != 1:
    raise SystemExit('bundle execute() anchor not found uniquely')
s = s.replace(execute_anchor, execute_replacement, 1)

# release-build already performed canonical manifest verification. Replace the
# literal escaped-newline fragment inside the driver's insertion string so the
# resulting implementation consumes that verified inventory instead of opening
# the promoted output a second time.
release_insert_old = (
    '        with zipfile.ZipFile(output, "r") as final_archive:\\n'
    '            integrity_payload = json.loads(final_archive.read("PACKAGE_INTEGRITY_MANIFEST.json").decode("utf-8-sig"))\\n'
    '        integrity_entries = [dict(item) for item in integrity_payload.get("files") or [] if isinstance(item, dict)]\\n'
    '        package_sidecar = build_single_zip_sidecar(\\n'
)
release_insert_new = (
    '        integrity_entries = list(verified_manifest_entries)\\n'
    '        package_sidecar = build_single_zip_sidecar(\\n'
)
if s.count(release_insert_old) != 1:
    raise SystemExit('release sidecar manifest re-open block not found uniquely')
s = s.replace(release_insert_old, release_insert_new, 1)

p.write_text(s, encoding='utf-8', newline='\n')

# Patch the current generator bootstrap before the convergence driver rebuilds
# its compressed map. Current archive/service sources have canonical imports of
# safe_paths, package_set_contract and resource_policy, while archive.__init__
# imports capabilities, which in turn imports version. Load that dependency
# closure in topological order into sys.modules.
g = Path('tools/jazn_pack_generator.py')
gs = g.read_text(encoding='utf-8')
old_bootstrap = '''_ensure_package("latka_jazn")\n_ensure_package("latka_jazn.memory")\n_ensure_package("latka_jazn.packaging")\n_ensure_package("latka_jazn.archive")\n_load_bundled_module("latka_jazn.memory.storage_limits")\n_load_bundled_module("latka_jazn.packaging.memory_raw_segmentation")\n_load_bundled_module("latka_jazn.archive.service")\n_load_bundled_module("latka_jazn.archive.hardened_service")\n_load_bundled_module("latka_jazn.archive", package=True)\n'''
new_bootstrap = '''_ensure_package("latka_jazn")\n_ensure_package("latka_jazn.memory")\n_ensure_package("latka_jazn.packaging")\n_ensure_package("latka_jazn.archive")\n_ensure_package("latka_jazn.tools")\n_load_bundled_module("latka_jazn.tools.safe_paths")\n_load_bundled_module("latka_jazn.memory.storage_limits")\n_load_bundled_module("latka_jazn.packaging.memory_raw_segmentation")\n_load_bundled_module("latka_jazn.packaging.package_set_contract")\n_load_bundled_module("latka_jazn.archive.resource_policy")\n_load_bundled_module("latka_jazn.archive.service")\n_load_bundled_module("latka_jazn.archive.hardened_service")\n_load_bundled_module("latka_jazn.version")\n_load_bundled_module("latka_jazn.archive.capabilities")\n_load_bundled_module("latka_jazn.archive", package=True)\n'''
if gs.count(old_bootstrap) != 1:
    raise SystemExit('generator archive bootstrap block not found uniquely')
g.write_text(gs.replace(old_bootstrap, new_bootstrap, 1), encoding='utf-8', newline='\n')

# Keep the release verification boundary single-pass. Carry the already parsed
# integrity entries as an internal value and remove it from the public report as
# soon as build_release_bundle receives it.
r = Path('latka_jazn/tools/release_bundle.py')
rs = r.read_text(encoding='utf-8')
return_anchor = '''        "manifest_runtime_version": manifest.get("runtime_version") or manifest.get("version"),\n        "checked_file_count": checked,\n        "errors": errors,\n'''
return_replacement = '''        "manifest_runtime_version": manifest.get("runtime_version") or manifest.get("version"),\n        "checked_file_count": checked,\n        "_verified_manifest_entries": [\n            dict(item) for item in manifest.get("files") or [] if isinstance(item, dict)\n        ],\n        "errors": errors,\n'''
if rs.count(return_anchor) != 1:
    raise SystemExit('release verifier return anchor not found uniquely')
rs = rs.replace(return_anchor, return_replacement, 1)
verify_anchor = '''                zip_verification = verify_release_zip_manifest(candidate)\n                candidate_digest = _sha256_file(candidate)\n'''
verify_replacement = '''                zip_verification = verify_release_zip_manifest(candidate)\n                verified_manifest_entries = tuple(\n                    dict(item)\n                    for item in zip_verification.pop("_verified_manifest_entries", [])\n                    if isinstance(item, dict)\n                )\n                candidate_digest = _sha256_file(candidate)\n'''
if rs.count(verify_anchor) != 1:
    raise SystemExit('release verifier consumption anchor not found uniquely')
rs = rs.replace(verify_anchor, verify_replacement, 1)
r.write_text(rs, encoding='utf-8', newline='\n')
