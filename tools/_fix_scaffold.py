from pathlib import Path
p = Path('tools/_apply_distribution_convergence.py')
s = p.read_text(encoding='utf-8')
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
p.write_text(s, encoding='utf-8', newline='\n')
