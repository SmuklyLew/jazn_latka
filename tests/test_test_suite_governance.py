from __future__ import annotations

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
