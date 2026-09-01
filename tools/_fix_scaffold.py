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
p.write_text(s, encoding='utf-8', newline='\n')
