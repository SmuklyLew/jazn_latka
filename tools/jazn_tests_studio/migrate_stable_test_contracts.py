#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

BASE_VERSION = "16.3.25.5.66"
BASE_SHA = "9a714a53c6e358904ac2e42cffc34f0e510445c9"
TARGET_VERSION = "16.3.25.5.67"
TARGET_RELEASE = "stable-test-contracts"
ARCHIVE_NAME = f"{BASE_VERSION}__{BASE_SHA[:12]}"
TEXT_SUFFIXES = {".py", ".md", ".toml", ".json", ".yml", ".yaml", ".ps1", ".sh", ".cmd", ".txt"}
SYSTEM_RELEASE_TOKEN = re.compile(r"v16(?:_\d+){2,}|v163\d{3,}", re.I)
HIGH_RELEASE_TOKEN = re.compile(r"(?:(?<=_)|^)v(?:[3-9]\d|[1-9]\d{2,})(?=_|$)", re.I)
FUNCTION_RE = re.compile(r"(?m)^(\s*(?:async\s+)?def\s+)(test_[A-Za-z0-9_]+)(\s*\()")


@dataclass(frozen=True)
class Candidate:
    source: Path
    target_name: str
    text: str
    rank: tuple[int, ...]
    functions: frozenset[str]


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "tests").is_dir():
            return candidate
    raise SystemExit("repository root not found")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def version_rank(name: str) -> tuple[int, ...]:
    values: list[int] = []
    for match in re.finditer(r"v(\d+(?:_\d+)*)", name, re.I):
        raw = match.group(1)
        if "_" in raw:
            values.extend(int(part) for part in raw.split("_") if part)
        elif len(raw) >= 4:
            values.append(int(raw))
        elif int(raw) >= 30:
            values.append(int(raw))
    return tuple(values) or (0,)


def _strip_release_tokens(value: str) -> str:
    previous = None
    current = value
    while previous != current:
        previous = current
        current = re.sub(r"__pre_v(?:[3-9]\d|[1-9]\d{2,})$", "", current, flags=re.I)
        current = re.sub(r"_source_v(?:16(?:_\d+){2,}|163\d+|[3-9]\d|[1-9]\d{2,})$", "", current, flags=re.I)
        current = re.sub(r"_v16(?:_\d+){2,}$", "", current, flags=re.I)
        current = re.sub(r"_v163\d{3,}$", "", current, flags=re.I)
        current = re.sub(r"_v(?:[3-9]\d|[1-9]\d{2,})$", "", current, flags=re.I)
        current = re.sub(r"^(test_)v16(?:_?\d+){2,}_?", r"\1", current, flags=re.I)
        current = re.sub(r"^(test_)v163\d{3,}_?", r"\1", current, flags=re.I)
        current = re.sub(r"^(test_)v(?:[3-9]\d|[1-9]\d{2,})_", r"\1", current, flags=re.I)
        current = SYSTEM_RELEASE_TOKEN.sub("", current)
        current = HIGH_RELEASE_TOKEN.sub("", current)
    current = re.sub(r"_{2,}", "_", current).rstrip("_")
    return current


def stable_filename(name: str) -> str:
    stem = Path(name).stem
    stable = _strip_release_tokens(stem)
    if not stable.startswith("test_"):
        stable = "test_" + stable.removeprefix("test")
    return stable.rstrip("_") + ".py"


def stable_function(name: str) -> str:
    return _strip_release_tokens(name)


def remove_function_blocks(text: str, predicate) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            if predicate(node.name):
                start = node.lineno
                # Include immediately attached decorators.
                if node.decorator_list:
                    start = min(start, *(d.lineno for d in node.decorator_list))
                ranges.append((start, int(getattr(node, "end_lineno", node.lineno))))
    if not ranges:
        return text
    lines = text.splitlines(keepends=True)
    for start, end in sorted(ranges, reverse=True):
        del lines[start - 1 : end]
    return "".join(lines)


def normalize_test_source(text: str) -> str:
    text = remove_function_blocks(
        text,
        lambda name: name == "test_git_diff_has_no_whitespace_errors"
        or "release_identity_floor" in name
        or ("release" in name and ("regression_floor" in name or "release_line_is_at_least" in name or "release_line_preserves" in name))
        or bool(re.fullmatch(r"test_v\d+_release_identity", name)),
    )

    def repl(match: re.Match[str]) -> str:
        return match.group(1) + stable_function(match.group(2)) + match.group(3)

    text = FUNCTION_RE.sub(repl, text)

    # Optional archive backends are capabilities, not mandatory base dependencies.
    if re.search(r"(?m)^\s*import\s+py7zr\s*$", text):
        if not re.search(r"(?m)^\s*import\s+pytest\b", text):
            insertion = "import pytest\n"
            future = re.search(r"(?m)^from __future__ import .+\n", text)
            pos = future.end() if future else 0
            text = text[:pos] + insertion + text[pos:]
        text = re.sub(
            r"(?m)^\s*import\s+py7zr\s*$",
            'py7zr = pytest.importorskip("py7zr", reason="optional archive backend is not installed")',
            text,
        )
    return text


def test_functions(text: str) -> frozenset[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return frozenset()
    return frozenset(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    )


def snapshot_active_tests(root: Path) -> Path:
    tests = root / "tests"
    archive = tests / "archive" / "branches" / ARCHIVE_NAME
    archive.mkdir(parents=True, exist_ok=True)
    sources = [tests / "conftest.py", *sorted(tests.glob("test_*.py"))]
    manifest_entries: list[dict[str, object]] = []
    for source in sources:
        if not source.is_file():
            continue
        dest = archive / source.name
        if dest.exists():
            if sha256(dest) != sha256(source):
                raise SystemExit(f"archive mismatch: {dest}")
        else:
            shutil.copy2(source, dest)
        manifest_entries.append(
            {
                "path": source.name,
                "size": source.stat().st_size,
                "sha256": sha256(source),
            }
        )
    manifest = {
        "schema": "jazn_test_branch_snapshot/v1",
        "base_version": BASE_VERSION,
        "base_commit": BASE_SHA,
        "active_test_file_count": len([x for x in sources if x.is_file()]),
        "files": manifest_entries,
    }
    (archive / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return archive


def migrate_active_tests(root: Path) -> dict[str, str]:
    tests = root / "tests"
    originals = sorted(tests.glob("test_*.py"))
    candidates: dict[str, list[Candidate]] = {}
    old_to_target: dict[str, str] = {}

    obsolete_files = {"test_jazn_pack_generator_v82_contract.py"}
    for source in originals:
        if source.name in obsolete_files:
            old_to_target[f"tests/{source.name}"] = "tests/archive/branches/" + ARCHIVE_NAME + "/" + source.name
            continue
        text = normalize_test_source(source.read_text(encoding="utf-8"))
        funcs = test_functions(text)
        if not funcs:
            old_to_target[f"tests/{source.name}"] = "tests/archive/branches/" + ARCHIVE_NAME + "/" + source.name
            continue
        target_name = stable_filename(source.name)
        candidate = Candidate(source, target_name, text, version_rank(source.stem), funcs)
        candidates.setdefault(target_name, []).append(candidate)

    # Remove the old active generation first. Snapshot above is the byte-exact rollback point.
    for source in originals:
        source.unlink()

    for target_name, group in sorted(candidates.items()):
        group = sorted(group, key=lambda c: (c.rank, c.source.name), reverse=True)
        primary = group[0]
        target = tests / target_name
        target.write_text(primary.text, encoding="utf-8")
        old_to_target[f"tests/{primary.source.name}"] = f"tests/{target_name}"
        primary_funcs = set(primary.functions)
        supplemental_index = 0
        for extra in group[1:]:
            old_key = f"tests/{extra.source.name}"
            if set(extra.functions).issubset(primary_funcs):
                old_to_target[old_key] = f"tests/{target_name}"
                continue
            supplemental_index += 1
            supplement_name = f"{Path(target_name).stem}_supplemental{'' if supplemental_index == 1 else '_' + str(supplemental_index)}.py"
            (tests / supplement_name).write_text(extra.text, encoding="utf-8")
            old_to_target[old_key] = f"tests/{supplement_name}"
    return old_to_target


def update_operational_references(root: Path, mapping: dict[str, str]) -> None:
    skip_prefixes = ("tests/archive/branches/", ".git/")
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(skip_prefixes):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = text
        for old, new in mapping.items():
            if old == new or new.startswith("tests/archive/branches/"):
                continue
            updated = updated.replace(old, new)
            updated = updated.replace(Path(old).name, Path(new).name)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def category_for(path: str, name: str, source: str) -> tuple[str, list[str]]:
    haystack = f"{path} {name}".lower()
    tags: list[str] = []
    if any(k in haystack for k in ("security", "gateway", "redaction", "traversal", "sandbox", "secret")):
        category = "security"
    elif any(k in haystack for k in ("end_to_end", "e2e", "smoke", "bootstrap")):
        category = "e2e"
    elif any(k in haystack for k in ("integration", "runtime", "daemon", "bridge", "orchestration", "lifecycle")):
        category = "integration"
    elif any(k in haystack for k in ("contract", "schema", "manifest", "version", "policy", "governance")):
        category = "contract"
    else:
        category = "unit"
    for token in ("windows", "mcp", "network", "archive", "memory", "repository", "runtime", "host", "package"):
        if token in haystack:
            tags.append(token)
    if "subprocess" in source or "git " in source:
        tags.append("repository")
    return category, sorted(set(tags))


def humanize(name: str) -> str:
    value = name.removeprefix("test_").replace("__", "_").replace("_", " ").strip()
    return value[:1].upper() + value[1:] if value else "Verify current contract"


def marker_names(node: ast.AST) -> list[str]:
    result: list[str] = []
    for deco in getattr(node, "decorator_list", []):
        value = deco.func if isinstance(deco, ast.Call) else deco
        parts: list[str] = []
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        dotted = ".".join(reversed(parts))
        if dotted.startswith("pytest.mark."):
            result.append(dotted.split(".")[-1])
    return sorted(set(result))


def build_contract_catalog(root: Path) -> dict[str, object]:
    records: dict[str, dict[str, object]] = {}
    active_files = sorted(p for p in (root / "tests").rglob("test_*.py") if "archive" not in p.parts)
    for path in active_files:
        rel = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            records[f"{rel}::<parse_error>"] = {
                "path": rel,
                "name": "<parse_error>",
                "purpose": "Source must parse as valid Python.",
                "expected": f"AST parsing succeeds; current error: {exc}",
                "category": "contract",
                "tags": ["syntax"],
                "status": "incompatible",
            }
            continue
        imports: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imports.update(alias.name for alias in n.names if alias.name.startswith("latka_jazn"))
            elif isinstance(n, ast.ImportFrom) and (n.module or "").startswith("latka_jazn"):
                imports.add(n.module or "")

        def add_node(node: ast.AST, prefix: str = "") -> None:
            name = getattr(node, "name", "")
            if not name.startswith("test_"):
                return
            doc = ast.get_docstring(node, clean=True) or ""
            purpose = doc.splitlines()[0].strip() if doc else humanize(name)
            category, tags = category_for(rel, name, source)
            assertions = sum(isinstance(x, ast.Assert) for x in ast.walk(node))
            raises: list[str] = []
            for x in ast.walk(node):
                if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "raises" and x.args:
                    arg = x.args[0]
                    if isinstance(arg, ast.Name):
                        raises.append(arg.id)
                    elif isinstance(arg, ast.Attribute):
                        raises.append(arg.attr)
            nodeid = f"{rel}::{prefix}{name}"
            records[nodeid] = {
                "path": rel,
                "name": name,
                "purpose": purpose,
                "expected": f"Pytest completes this contract cleanly and all {assertions} explicit assertion(s) plus declared expected exceptions hold.",
                "category": category,
                "tags": tags,
                "markers": marker_names(node),
                "assertion_count": assertions,
                "expected_exceptions": sorted(set(raises)),
                "targets": sorted(imports),
                "status": "current",
                "description_source": "native_docstring" if doc else "source_identity",
                "line": getattr(node, "lineno", None),
            }

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_node(node)
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        add_node(child, prefix=f"{node.name}::")
    return {
        "schema": "jazn_tests_studio_contract_catalog/v2",
        "system_version": TARGET_VERSION,
        "active_definition_count": len(records),
        "contracts": records,
    }


def write_studio_support(root: Path, catalog: dict[str, object]) -> None:
    studio = root / "tools" / "jazn_tests_studio"
    studio.mkdir(parents=True, exist_ok=True)
    (studio / "__init__.py").write_text('"""Support files for Jaźń - Studio testów."""\n', encoding="utf-8")
    settings = {
        "schema": "jazn_tests_studio_settings/v2",
        "app_name": "Jaźń - Studio testów",
        "active_tests": "tests",
        "archive_branches": "tests/archive/branches",
        "contract_catalog": "tools/jazn_tests_studio/test_contracts.json",
        "reviews": "tools/jazn_tests_studio/reviews.json",
        "exclude_from_run_all": ["tests/archive"],
        "default_timeout_seconds": 1800,
    }
    (studio / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (studio / "test_contracts.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (studio / ".gitignore").write_text("reviews.json\n*.tmp\nruntime/\n", encoding="utf-8")
    (studio / "README.md").write_text(
        "# Jaźń - Studio testów\n\n"
        "Centralne metadane narzędzia testowego. `test_contracts.json` opisuje aktywne kontrakty testowe; "
        "`settings.json` definiuje ścieżki i politykę uruchamiania. `reviews.json` jest lokalnym stanem operatora i nie jest commitowany.\n",
        encoding="utf-8",
    )


def write_policy(root: Path) -> None:
    policy = """# Polityka testów Jaźni\n\n## Tożsamość testu\n\nTest nazywamy według trwałego przeznaczenia, nie według numeru wydania systemu. Nowa wersja Jaźni nie tworzy nowej nazwy tego samego testu. Numer wersji może pozostać wyłącznie wtedy, gdy jest częścią badanego formatu, schematu, protokołu albo ścieżki migracji.\n\n## Aktualizacja\n\nPrzed zmianą aktywnych testów tworzony jest byte-exact snapshot w `tests/archive/branches/<wersja>__<commit>/` z `MANIFEST.json`. Stary test nie pozostaje w aktywnym drzewie tylko po to, by zachować historię — historię zapewniają Git i snapshot.\n\n## Kontrakt\n\nKażda aktywna definicja testowa ma rekord w `tools/jazn_tests_studio/test_contracts.json`: cel, oczekiwane zachowanie, kategorię, tagi, liczbę asercji i powiązane moduły. Status `current` oznacza technicznie aktywny kontrakt; semantyczna recenzja może oznaczyć go jako `review_required`, `obsolete` albo `incompatible`.\n\n## Zasady\n\n- test ma potwierdzać obserwowalne zachowanie lub kontrakt, nie numer bieżącego release;\n- zależności opcjonalne powodują kontrolowany skip, gdy capability nie jest zainstalowana;\n- kontrole repozytorium/formatowania należą do CI lub kategorii `repository`, a nie do runtime produktu;\n- archiwum nie jest zbierane przez zwykły `pytest`;\n- poprawa istniejącego celu aktualizuje istniejący test pod stałą nazwą.\n"""
    (root / "tests" / "TESTING_POLICY.md").write_text(policy, encoding="utf-8")


def write_governance_tests(root: Path) -> None:
    source = r'''from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
STUDIO = ROOT / "tools" / "jazn_tests_studio"
RELEASE_TOKEN = re.compile(r"v16(?:_\d+){2,}|v163\d{3,}|(?:(?<=_)|^)v(?:[3-9]\d|[1-9]\d{2,})(?=_|$)", re.I)


def _active_files():
    return sorted(p for p in TESTS.rglob("test_*.py") if "archive" not in p.parts)


def _definitions():
    result = set()
    for path in _active_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT).as_posix()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                result.add(f"{rel}::{node.name}")
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_"):
                        result.add(f"{rel}::{node.name}::{child.name}")
    return result


def test_active_test_files_use_stable_purpose_names():
    bad = [p.name for p in _active_files() if RELEASE_TOKEN.search(p.stem)]
    assert not bad, f"release-coupled active test filenames: {bad}"


def test_active_test_functions_use_stable_purpose_names():
    bad = []
    for path in _active_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_") and RELEASE_TOKEN.search(node.name):
                bad.append(f"{path.name}::{node.name}")
    assert not bad, f"release-coupled active test functions: {bad}"


def test_contract_catalog_covers_every_active_definition():
    payload = json.loads((STUDIO / "test_contracts.json").read_text(encoding="utf-8"))
    contracts = payload["contracts"]
    assert set(contracts) == _definitions()
    missing_text = [nodeid for nodeid, item in contracts.items() if not item.get("purpose") or not item.get("expected")]
    assert not missing_text, f"contracts without Purpose/Expected: {missing_text}"


def test_snapshot_manifest_is_byte_exact():
    snapshots = sorted((TESTS / "archive" / "branches").glob("*/MANIFEST.json"))
    assert snapshots, "expected at least one test branch snapshot"
    manifest_path = snapshots[-1]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    for item in manifest["files"]:
        data = (base / item["path"]).read_bytes()
        assert len(data) == item["size"]
        assert hashlib.sha256(data).hexdigest() == item["sha256"]


def test_studio_settings_keep_runtime_state_out_of_source_contracts():
    settings = json.loads((STUDIO / "settings.json").read_text(encoding="utf-8"))
    assert settings["archive_branches"] == "tests/archive/branches"
    assert settings["contract_catalog"].endswith("test_contracts.json")
    assert settings["reviews"].endswith("reviews.json")
    assert (STUDIO / ".gitignore").is_file()
'''
    (root / "tests" / "test_test_suite_governance.py").write_text(source, encoding="utf-8")


def bump_version(root: Path) -> None:
    path = root / "latka_jazn" / "version.py"
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r"# v16\.3\.25\.5\.66.*?DISTRIBUTION_VERSION = \"16\.3\.25\.5\.66\"",
        '# v16.3.25.5.67 converges tests on stable purpose-based identities, branch snapshots,\n# explicit Test Studio contracts, and governance that prevents release-coupled test duplication.\nDISTRIBUTION_VERSION = "16.3.25.5.67"',
        text,
        count=1,
        flags=re.S,
    )
    text = text.replace('PACKAGE_VERSION = "16.3.25.5.66"', 'PACKAGE_VERSION = "16.3.25.5.67"')
    text = text.replace('PACKAGE_RELEASE_NAME = "chatgpt-loader-pylance-static-gate-convergence"', 'PACKAGE_RELEASE_NAME = "stable-test-contracts"')
    path.write_text(text, encoding="utf-8")


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    active = sorted(p for p in (root / "tests").rglob("test_*.py") if "archive" not in p.parts)
    for path in active:
        if SYSTEM_RELEASE_TOKEN.search(path.stem) or HIGH_RELEASE_TOKEN.search(path.stem):
            errors.append(f"release-coupled filename: {path.relative_to(root)}")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            errors.append(f"syntax error: {path.relative_to(root)}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                if SYSTEM_RELEASE_TOKEN.search(node.name) or HIGH_RELEASE_TOKEN.search(node.name):
                    errors.append(f"release-coupled function: {path.name}::{node.name}")
    catalog_path = root / "tools" / "jazn_tests_studio" / "test_contracts.json"
    if not catalog_path.is_file():
        errors.append("missing test contract catalog")
    return errors


def apply(root: Path) -> None:
    snapshot_active_tests(root)
    mapping = migrate_active_tests(root)
    update_operational_references(root, mapping)
    write_policy(root)
    write_governance_tests(root)
    catalog = build_contract_catalog(root)
    write_studio_support(root, catalog)
    bump_version(root)
    migration = {
        "schema": "jazn_test_contract_migration/v1",
        "base_version": BASE_VERSION,
        "base_commit": BASE_SHA,
        "target_version": TARGET_VERSION,
        "target_release": TARGET_RELEASE,
        "renamed_or_retired": mapping,
        "active_definition_count": catalog["active_definition_count"],
    }
    archive = root / "tests" / "archive" / "branches" / ARCHIVE_NAME
    (archive / "MIGRATION.json").write_text(json.dumps(migration, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    errors = validate(root)
    if errors:
        raise SystemExit("migration validation failed:\n- " + "\n- ".join(errors))
    print(json.dumps({"ok": True, "active_definition_count": catalog["active_definition_count"], "mapping_count": len(mapping)}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Jaźń tests to stable purpose-based contracts")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = repo_root()
    if args.apply:
        apply(root)
        return 0
    errors = validate(root)
    if errors:
        print("\n".join(errors))
        return 1
    print("stable test contract checks: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
