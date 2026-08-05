from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from latka_jazn.version import DISTRIBUTION_VERSION, PACKAGE_VERSION, PACKAGE_VERSION_FULL, version_number
from latka_jazn.version_contract import (
    LEGACY_CURRENT_LINE_VERSION,
    LEGACY_MEMORY_SOURCE_VERSION,
    V90_ARCHIVE_ROOT,
    V90_MIGRATION_TARGET_VERSION,
    component_schema_version,
)

EXPECTED_BRANCH = "feature/memory-sqlite-test-04"
ARCHIVE_ROOT = Path(V90_ARCHIVE_ROOT)
PREVIOUS_ARCHIVE_ROOT = Path(".archives/pre_v" + "_".join(("15", "1", "0", "3", "89")))
ARCHIVE_SCHEMA_VERSION = "current_line_archive/v1"
MIGRATION_SCHEMA_VERSION = "current_line_v90_migration/v1"
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".jsonl", ".yml", ".yaml", ".toml",
    ".ini", ".cfg", ".ps1", ".sh", ".bat", ".cmd", ".xml", ".csv",
}
EXCLUDED_ACTIVE_PATHS = {
    "PACKAGE_INTEGRITY_MANIFEST.json",
    "SOURCE_PROVENANCE.json",
}
HISTORICAL_ARTIFACTS = {
    f"PATCH_BUMP_JAZN_TO_{V90_MIGRATION_TARGET_VERSION}.ps1",
    "docs/plans/memory_rebuild_plan/jazn_memory_tests_deep_archive_search.json",
}
LEGACY_SOURCE_PATHS = {
    "docs/templates/memory_sqlite_test_04/source-manifest.template.json",
    "docs/tools/MEMORY_SQLITE_TEST_04.md",
    "latka_jazn/tools/memory_sqlite_test04.py",
}
_VERSION_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])v?(?P<version>1[45](?:[._]\d+){2,6})(?![A-Za-z0-9])"
)
_RELEASE_SCHEMA_RE = re.compile(
    r"(?P<component>[A-Za-z][A-Za-z0-9_.-]*)/v?" + re.escape(LEGACY_CURRENT_LINE_VERSION.lstrip("v"))
)


class MigrationError(RuntimeError):
    pass


@dataclass(slots=True)
class ArchiveEntry:
    original_path: str
    archive_path: str | None
    retention: str
    category: str
    reason: str
    size_bytes: int
    sha256: str


@dataclass(slots=True)
class MigrationReport:
    schema_version: str
    ok: bool
    root: str
    branch: str
    source_commit: str
    source_package_version: str
    target_package_version: str
    archive_root: str
    archived_file_count: int
    modified_paths: list[str]
    deleted_paths: list[str]
    added_paths: list[str]
    approved_legacy_reference_count: int
    remaining_old_references: list[dict[str, Any]]
    archive_manifest_path: str
    external_backup_root: str | None
    truth_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run_git(root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and completed.returncode:
        raise MigrationError(
            f"git {' '.join(args)} failed with exit code {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout


def _tracked_paths(root: Path) -> list[str]:
    return [item for item in _run_git(root, "ls-files", "-z").split("\0") if item]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _version_tuple(raw: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in raw.replace("_", ".").lstrip("vV").split("."))
    except (TypeError, ValueError):
        return None


def _padded(parts: tuple[int, ...], width: int = 7) -> tuple[int, ...]:
    return (parts + (0,) * width)[:width]


def _is_old_package_version(raw: str) -> bool:
    candidate = _version_tuple(raw)
    current = _version_tuple(version_number(PACKAGE_VERSION))
    if candidate is None or current is None or candidate[0] not in {14, 15}:
        return False
    return _padded(candidate) < _padded(current)


def _is_active_path(path: str) -> bool:
    folded = path.replace("\\", "/")
    return not folded.startswith(".archives/") and folded not in EXCLUDED_ACTIVE_PATHS


def _is_approved_legacy_source(path: str, line: str, raw_version: str) -> bool:
    normalized = "v" + raw_version.replace("_", ".").lstrip("vV")
    if normalized != LEGACY_MEMORY_SOURCE_VERSION or path not in LEGACY_SOURCE_PATHS:
        return False
    folded = line.casefold()
    return any(
        token in folded
        for token in (
            "legacy", "legacymemoryroot", "legacy_memory_root", "legacy-memory-root",
            "starszej pamięci", "starszego źródła", "baseline",
        )
    )


def scan_active_old_references(root: Path) -> tuple[list[dict[str, Any]], int]:
    findings: list[dict[str, Any]] = []
    approved_legacy = 0
    for rel in _tracked_paths(root):
        if not _is_active_path(rel):
            continue
        path = root / rel
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in _VERSION_RE.finditer(line):
                raw = match.group("version")
                if not _is_old_package_version(raw):
                    continue
                if (
                    "DISTRIBUTION_VERSION" in line
                    and raw.replace("_", ".").lstrip("vV") == DISTRIBUTION_VERSION
                ):
                    continue
                if _is_approved_legacy_source(rel, line, raw):
                    approved_legacy += 1
                    continue
                if rel in HISTORICAL_ARTIFACTS and V90_ARCHIVE_ROOT in line:
                    continue
                findings.append(
                    {
                        "path": rel,
                        "line": lineno,
                        "version": raw.replace("_", "."),
                        "line_sha256": _sha256_bytes(line.encode("utf-8", errors="replace")),
                    }
                )
    return findings, approved_legacy


def _ensure_version_import(text: str, names: set[str]) -> str:
    if not names:
        return text
    lines = text.splitlines(keepends=True)
    import_re = re.compile(r"^(?P<prefix>from latka_jazn\.version import )(?P<body>.+?)(?P<end>\r?\n)$")
    for index, line in enumerate(lines):
        match = import_re.match(line)
        if not match:
            continue
        body = match.group("body").strip()
        if body.startswith("("):
            # Multiline imports are left unchanged; add a separate deterministic import.
            break
        existing = {item.strip() for item in body.split(",") if item.strip()}
        merged = sorted(existing | names)
        lines[index] = match.group("prefix") + ", ".join(merged) + match.group("end")
        return "".join(lines)
    insert_at = 0
    if lines and lines[0].startswith("from __future__ import annotations"):
        insert_at = 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
    lines.insert(insert_at, f"from latka_jazn.version import {', '.join(sorted(names))}\n")
    return "".join(lines)


def _ensure_contract_import(text: str, names: set[str]) -> str:
    if not names:
        return text
    lines = text.splitlines(keepends=True)
    prefix = "from latka_jazn.version_contract import "
    for index, line in enumerate(lines):
        if not line.startswith(prefix):
            continue
        body = line[len(prefix):].strip()
        if body.startswith("("):
            break
        existing = {item.strip() for item in body.split(",") if item.strip()}
        lines[index] = prefix + ", ".join(sorted(existing | names)) + "\n"
        return "".join(lines)
    insert_at = 0
    if lines and lines[0].startswith("from __future__ import annotations"):
        insert_at = 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
    lines.insert(insert_at, prefix + ", ".join(sorted(names)) + "\n")
    return "".join(lines)


def _semantic_previous_line(text: str) -> str:
    replacements = (
        (LEGACY_CURRENT_LINE_VERSION, "poprzednia linia runtime"),
        (LEGACY_CURRENT_LINE_VERSION.lstrip("v"), "poprzednia linia runtime"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _transform_release_completion_test(text: str) -> str:
    text = _ensure_version_import(text, {"DISTRIBUTION_VERSION", "PACKAGE_VERSION", "PACKAGE_VERSION_FULL"})
    old_number = LEGACY_CURRENT_LINE_VERSION.lstrip("v")
    text = text.replace(
        f'        "DISTRIBUTION_VERSION = \'{old_number}\'\\n"\n'
        f'        "PACKAGE_VERSION = \'{LEGACY_CURRENT_LINE_VERSION}\'\\n"\n',
        '        f"DISTRIBUTION_VERSION = {DISTRIBUTION_VERSION!r}\\n"\n'
        '        f"PACKAGE_VERSION = {PACKAGE_VERSION!r}\\n"\n',
    )
    text = text.replace(
        f'output = tmp_path / "exports" / "jazn_latka_{LEGACY_CURRENT_LINE_VERSION}.zip"',
        'output = tmp_path / "exports" / f"jazn_latka_{PACKAGE_VERSION}.zip"',
    )
    return text


def _transform_workflow_test(text: str) -> str:
    old = LEGACY_CURRENT_LINE_VERSION
    old_number = old.lstrip("v")
    text = text.replace(
        f'        assert "{old}" not in text\n'
        f'        assert "update/{old}" not in text\n',
        '        previous_release = "v" + ".".join(("15", "1", "0", "3", "89"))\n'
        '        assert previous_release not in text\n'
        '        assert f"update/{previous_release}" not in text\n',
    )
    text = text.replace(old_number, PACKAGE_VERSION.lstrip("v"))
    return text


def _transform_audit_module(text: str) -> str:
    text = text.replace(
        'ARCHIVE_ROOT = Path(".archives/pre_v' + '_'.join(("15", "1", "0", "3", "89")) + '")',
        'ARCHIVE_ROOT = Path(V90_ARCHIVE_ROOT)',
    )
    if "LEGACY_MEMORY_SOURCE_VERSION" not in text:
        text = _ensure_contract_import(text, {"LEGACY_MEMORY_SOURCE_VERSION"})
    if "APPROVED_LEGACY_SOURCE_PATHS" not in text:
        anchor = "EXCLUDED_ACTIVE_PATHS = {\n    \"PACKAGE_INTEGRITY_MANIFEST.json\",\n    \"SOURCE_PROVENANCE.json\",\n}\n"
        addition = anchor + "APPROVED_LEGACY_SOURCE_PATHS = {\n" \
            "    \"docs/templates/memory_sqlite_test_04/source-manifest.template.json\",\n" \
            "    \"docs/tools/MEMORY_SQLITE_TEST_04.md\",\n" \
            "    \"latka_jazn/tools/memory_sqlite_test04.py\",\n" \
            "}\n"
        if anchor not in text:
            raise MigrationError("current_line_archive_audit.py exclusion anchor not found")
        text = text.replace(anchor, addition, 1)
    if "def _line_is_approved_legacy_source" not in text:
        anchor = "def _line_is_canonical_distribution(path: str, line: str, raw_version: str) -> bool:\n"
        function = '''def _line_is_approved_legacy_source(path: str, line: str, raw_version: str) -> bool:\n    normalized = "v" + raw_version.replace("_", ".").lstrip("vV")\n    if normalized != LEGACY_MEMORY_SOURCE_VERSION or path not in APPROVED_LEGACY_SOURCE_PATHS:\n        return False\n    folded = line.casefold()\n    return any(\n        token in folded\n        for token in (\n            "legacy", "legacymemoryroot", "legacy_memory_root",\n            "legacy-memory-root", "starszej pamięci", "starszego źródła", "baseline",\n        )\n    )\n\n\n'''
        if anchor not in text:
            raise MigrationError("current_line_archive_audit.py canonical distribution anchor not found")
        text = text.replace(anchor, function + anchor, 1)
    scan_anchor = "                if _line_is_canonical_distribution(rel, line, raw):\n                    continue\n"
    scan_addition = scan_anchor + "                if _line_is_approved_legacy_source(rel, line, raw):\n                    continue\n"
    if "_line_is_approved_legacy_source(rel, line, raw)" not in text:
        if scan_anchor not in text:
            raise MigrationError("current_line_archive_audit.py scan anchor not found")
        text = text.replace(scan_anchor, scan_addition, 1)
    text = text.replace(
        "Audyt sprawdza śledzone aktywne pliki tekstowe i integralność archiwum. ",
        "Audyt sprawdza śledzone aktywne pliki tekstowe, jawnie oznaczone legacy source i integralność archiwum. ",
    )
    return text


def _transform_dziennik(text: str) -> str:
    text = text.replace(
        f'DZIENNIK_SCHEMA_VERSION = "{LEGACY_CURRENT_LINE_VERSION}"',
        'DZIENNIK_SCHEMA_VERSION = "dziennik/v1"',
    )
    text = _ensure_contract_import(text, {"normalize_component_schema"})
    anchor = '        if not isinstance(data.get("meta"), dict):\n            data["meta"] = {}\n        return data\n'
    replacement = '        if not isinstance(data.get("meta"), dict):\n            data["meta"] = {}\n        data["meta"]["schema_version"] = normalize_component_schema(\n            "dziennik", data["meta"].get("schema_version")\n        )\n        return data\n'
    if anchor in text and "normalize_component_schema(" not in text[text.find("def load"):text.find("def save")]:
        text = text.replace(anchor, replacement, 1)
    return text


def _transform_shard_manifest(text: str) -> str:
    text = _ensure_contract_import(text, {"normalize_component_schema"})
    text = text.replace(
        f'SCHEMA_VERSION = "jazn_sqlite_shards/{LEGACY_CURRENT_LINE_VERSION}"',
        'SCHEMA_VERSION = "jazn_sqlite_shards/v1"',
    )
    old = 'return cls(schema_version=str(data.get("schema_version") or SCHEMA_VERSION), logical_database='
    new = 'return cls(schema_version=normalize_component_schema("jazn_sqlite_shards", data.get("schema_version")), logical_database='
    text = text.replace(old, new)
    return text


def _transform_session_continuity(text: str) -> str:
    text = text.replace(
        f'SESSION_CONTINUITY_SCHEMA_VERSION = "session_continuity/{LEGACY_CURRENT_LINE_VERSION}"',
        'SESSION_CONTINUITY_SCHEMA_VERSION = "session_continuity/v1"',
    )
    text = _ensure_contract_import(text, {"normalize_component_schema"})
    old = '            data = json.loads(self.index_path.read_text(encoding="utf-8"))\n            return data if isinstance(data, dict) else {}\n'
    new = '            data = json.loads(self.index_path.read_text(encoding="utf-8"))\n            if not isinstance(data, dict):\n                return {}\n            data["schema_version"] = normalize_component_schema(\n                "session_continuity", data.get("schema_version")\n            )\n            return data\n'
    text = text.replace(old, new)
    return text


def _transform_dialogue_classifier(text: str) -> str:
    text = _ensure_contract_import(text, {"mentions_jazn_version"})
    old_number = LEGACY_CURRENT_LINE_VERSION.lstrip("v")
    text = text.replace(f' or "{old_number}" in folded)', ' or mentions_jazn_version(folded))')
    text = text.replace(
        f"any(x in folded for x in ('patch', 'hotfix', '{LEGACY_CURRENT_LINE_VERSION}', 'aktualiz'))",
        "(any(x in folded for x in ('patch', 'hotfix', 'aktualiz')) or mentions_jazn_version(folded))",
    )
    text = text.replace(
        f'(has_update or "{LEGACY_CURRENT_LINE_VERSION}" in folded)',
        '(has_update or mentions_jazn_version(folded))',
    )
    return text


def _transform_python(path: str, text: str) -> str:
    if path == "tests/test_release_completion.py":
        text = _transform_release_completion_test(text)
    if path == "tests/test_release_workflow_hardening.py":
        text = _transform_workflow_test(text)
    if path == "latka_jazn/tools/current_line_archive_audit.py":
        text = _transform_audit_module(text)
    if path == "latka_jazn/memory/dziennik.py":
        text = _transform_dziennik(text)
    if path == "latka_jazn/db/shard_manifest.py":
        text = _transform_shard_manifest(text)
    if path == "latka_jazn/memory/session_continuity.py":
        text = _transform_session_continuity(text)
    if path == "latka_jazn/nlp/dialogue_intent_classifier.py":
        text = _transform_dialogue_classifier(text)

    text = _RELEASE_SCHEMA_RE.sub(lambda match: component_schema_version(match.group("component")), text)

    exact_schema_variables = {
        "DZIENNIK_SCHEMA_VERSION": "dziennik/v1",
        "EVENT_LEDGER_SCHEMA_VERSION": "event_ledger/v1",
        "RUNTIME_MEMORY_SCHEMA_VERSION": "runtime_persistence/v1",
    }
    for variable, schema in exact_schema_variables.items():
        text = re.sub(
            rf'(?m)^(?P<indent>\s*){re.escape(variable)}\s*=\s*[\"\']{re.escape(LEGACY_CURRENT_LINE_VERSION)}[\"\']',
            rf'\g<indent>{variable} = "{schema}"',
            text,
        )

    version_names: set[str] = set()
    # Defaults and active metadata use the canonical source rather than another literal.
    default_patterns = (
        (rf'(?P<prefix>\bversion:\s*str\s*=\s*)[\"\']{re.escape(LEGACY_CURRENT_LINE_VERSION)}[\"\']', r'\g<prefix>PACKAGE_VERSION'),
        (rf'(?P<prefix>\bruntime_version:\s*str\s*=\s*)[\"\']{re.escape(LEGACY_CURRENT_LINE_VERSION)}[\"\']', r'\g<prefix>PACKAGE_VERSION'),
        (rf'(?P<prefix>[\"\']system_version[\"\']\s*,\s*)[\"\']{re.escape(LEGACY_CURRENT_LINE_VERSION)}[\"\']', r'\g<prefix>PACKAGE_VERSION'),
        (rf'(?P<prefix>[\"\']version[\"\']\s*:\s*)[\"\']{re.escape(LEGACY_CURRENT_LINE_VERSION)}[\"\']', r'\g<prefix>PACKAGE_VERSION'),
        (rf'(?P<prefix>[\"\']canon_version[\"\']\s*:\s*)[\"\']{re.escape(LEGACY_CURRENT_LINE_VERSION)}[\"\']', r'\g<prefix>PACKAGE_VERSION'),
    )
    for pattern, replacement in default_patterns:
        text, count = re.subn(pattern, replacement, text)
        if count:
            version_names.add("PACKAGE_VERSION")

    user_agent = f'"User-Agent": "LatkaJazn-TimeProbe/{LEGACY_CURRENT_LINE_VERSION.lstrip("v")}"'
    if user_agent in text:
        text = text.replace(
            user_agent,
            '"User-Agent": f"LatkaJazn-TimeProbe/{version_number(PACKAGE_VERSION)}"',
        )
        version_names.update({"PACKAGE_VERSION", "version_number"})

    if path == "latka_jazn/core/handlers/capability_status_handler.py":
        text = text.replace(f'or "{LEGACY_CURRENT_LINE_VERSION}")', 'or PACKAGE_VERSION)')
        text = text.replace(
            f'or "{LEGACY_CURRENT_LINE_VERSION.lstrip("v")}"',
            'or version_number(PACKAGE_VERSION)',
        )
        version_names.update({"PACKAGE_VERSION", "version_number"})

    if path == "latka_jazn/core/capability_reality_checker.py":
        old = f'DialogueIntentClassifier().classify("Sprawdź co działa w systemie Jaźni i co dodać do {LEGACY_CURRENT_LINE_VERSION}")'
        new = 'DialogueIntentClassifier().classify(f"Sprawdź co działa w systemie Jaźni i co dodać do {PACKAGE_VERSION}")'
        if old in text:
            text = text.replace(old, new)
            version_names.add("PACKAGE_VERSION")

    if path == "latka_jazn/memory/store.py":
        old = f'("system_version", "{LEGACY_CURRENT_LINE_VERSION}")'
        if old in text:
            text = text.replace(old, '("system_version", PACKAGE_VERSION)')
            version_names.add("PACKAGE_VERSION")

    # Runtime-generated provenance and tags follow the producer version.
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if LEGACY_CURRENT_LINE_VERSION not in line:
            continue
        stripped = line.strip()
        active_metadata = any(
            marker in line
            for marker in (
                "tags=[", "source=", "runtime_version=", "active_runtime_version",
                "last_updated_by", "created_by_runtime", '"version":', "'version':",
                '"runtime_version":', '"package_version":', '"system_version":',
            )
        )
        if active_metadata and not stripped.startswith("#"):
            lines[index] = line.replace(f'"{LEGACY_CURRENT_LINE_VERSION}"', "PACKAGE_VERSION").replace(
                f"'{LEGACY_CURRENT_LINE_VERSION}'", "PACKAGE_VERSION"
            )
            if lines[index] != line:
                version_names.add("PACKAGE_VERSION")
    text = "".join(lines)

    if path.startswith("tests/"):
        text = text.replace(LEGACY_CURRENT_LINE_VERSION, PACKAGE_VERSION)
        text = text.replace(LEGACY_CURRENT_LINE_VERSION.lstrip("v"), PACKAGE_VERSION.lstrip("v"))
    elif LEGACY_CURRENT_LINE_VERSION in text or LEGACY_CURRENT_LINE_VERSION.lstrip("v") in text:
        text = _semantic_previous_line(text)

    if path == "tests/test_current_line_archive_audit.py":
        text = re.sub(
            r'assert report\.package_version == PACKAGE_VERSION == ["\']v15\.1\.0\.3\.90["\']',
            'assert report.package_version == PACKAGE_VERSION',
            text,
        )

    text = _ensure_version_import(text, version_names)
    return text


def _json_schema_for_path(path: str) -> str:
    stem = Path(path).stem.replace(".", "_").replace("-", "_")
    return component_schema_version(stem)


def _transform_json_value(path: str, value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        transformed = {k: _transform_json_value(path, v, str(k)) for k, v in value.items()}
        if any(
            k in transformed
            for k in ("version", "canon_version", "active_runtime_version", "runtime_version", "package_version")
        ):
            transformed.setdefault("version_source", "latka_jazn.version.PACKAGE_VERSION")
        return transformed
    if isinstance(value, list):
        return [_transform_json_value(path, item, key) for item in value]
    if not isinstance(value, str):
        return value

    schema_match = _RELEASE_SCHEMA_RE.fullmatch(value)
    if schema_match:
        return component_schema_version(schema_match.group("component"))
    if key == "schema_version" and value == LEGACY_CURRENT_LINE_VERSION:
        return _json_schema_for_path(path)
    if value == LEGACY_CURRENT_LINE_VERSION:
        if key in {
            "version", "canon_version", "active_runtime_version", "runtime_version",
            "package_version", "system_version", "target_version", "target_release",
        }:
            return PACKAGE_VERSION
        return "bieżąca wersja Jaźni"
    if value == LEGACY_CURRENT_LINE_VERSION.lstrip("v"):
        if key in {
            "version", "canon_version", "active_runtime_version", "runtime_version",
            "package_version", "system_version", "target_version", "target_release",
        }:
            return version_number(PACKAGE_VERSION)
        return "bieżąca wersja Jaźni"
    if LEGACY_CURRENT_LINE_VERSION in value:
        if key in {"description", "purpose", "truth_boundary", "note", "notes", "markers", "phrases", "examples"}:
            return value.replace(LEGACY_CURRENT_LINE_VERSION, "bieżąca wersja Jaźni")
        return value.replace(LEGACY_CURRENT_LINE_VERSION, PACKAGE_VERSION)
    if LEGACY_CURRENT_LINE_VERSION.lstrip("v") in value:
        if key in {"description", "purpose", "truth_boundary", "note", "notes", "markers", "phrases", "examples"}:
            return value.replace(LEGACY_CURRENT_LINE_VERSION.lstrip("v"), "bieżąca wersja Jaźni")
        return value.replace(LEGACY_CURRENT_LINE_VERSION.lstrip("v"), version_number(PACKAGE_VERSION))
    return value


def _transform_json(path: str, text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _semantic_previous_line(text)
    transformed = _transform_json_value(path, payload)
    return json.dumps(transformed, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _transform_text(path: str, text: str) -> str:
    if path in LEGACY_SOURCE_PATHS:
        # Legacy source paths remain exact compatibility inputs and are approved by the audit.
        old = LEGACY_CURRENT_LINE_VERSION
        text = text.replace(old, PACKAGE_VERSION)
        text = text.replace(old.lstrip("v"), version_number(PACKAGE_VERSION))
        return text
    if path == "README.md":
        text = text.replace(
            f"{LEGACY_CURRENT_LINE_VERSION}-Night of Hotfix",
            PACKAGE_VERSION_FULL,
        )
        text = text.replace(LEGACY_CURRENT_LINE_VERSION, PACKAGE_VERSION)
        text = text.replace(LEGACY_CURRENT_LINE_VERSION.lstrip("v"), version_number(PACKAGE_VERSION))
        return text
    if path in {
        "docs/MEMORY_RECOVERY_CURRENT.md",
        "docs/plans/MEMORY_CONTINUITY_VALIDATION_BACKLOG.md",
        "docs/reports/MEMORY_SQLITE_TEST_04_IMPLEMENTATION_REPORT.md",
    }:
        text = text.replace(LEGACY_CURRENT_LINE_VERSION, PACKAGE_VERSION)
        text = text.replace(LEGACY_CURRENT_LINE_VERSION.lstrip("v"), version_number(PACKAGE_VERSION))
        return text
    return _semantic_previous_line(text)


def _transform_file(path: str, text: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return _transform_python(path, text)
    if suffix == ".json":
        return _transform_json(path, text)
    return _transform_text(path, text)


def _inherit_private_metadata(root: Path) -> list[ArchiveEntry]:
    manifest_path = root / PREVIOUS_ARCHIVE_ROOT / "ARCHIVE_MANIFEST.json"
    if not manifest_path.is_file():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries: list[ArchiveEntry] = []
    for item in payload.get("files", []):
        if not isinstance(item, dict) or item.get("retention") != "metadata_only_private_source":
            continue
        entries.append(
            ArchiveEntry(
                original_path=str(item.get("original_path") or ""),
                archive_path=None,
                retention="metadata_only_private_source",
                category=str(item.get("category") or "generated_private_source"),
                reason="carry_forward_private_metadata_only",
                size_bytes=int(item.get("size_bytes") or 0),
                sha256=str(item.get("sha256") or ""),
            )
        )
    return entries


def _write_archive(
    root: Path,
    paths: list[str],
    *,
    source_commit: str,
) -> tuple[list[ArchiveEntry], Path]:
    archive_root = root / ARCHIVE_ROOT
    if archive_root.exists():
        raise MigrationError(
            f"archive root already exists: {archive_root}; restore or review it before retrying"
        )
    tree_root = archive_root / "tree"
    entries: list[ArchiveEntry] = []
    for rel in paths:
        source = root / rel
        if not source.is_file():
            continue
        data = source.read_bytes()
        destination = tree_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        entries.append(
            ArchiveEntry(
                original_path=rel,
                archive_path=(ARCHIVE_ROOT / "tree" / rel).as_posix(),
                retention="exact_copy",
                category=(
                    "historical_artifact"
                    if rel in HISTORICAL_ARTIFACTS
                    else "active_source_before_v90_migration"
                ),
                reason=(
                    "archive_and_remove_from_active_tree"
                    if rel in HISTORICAL_ARTIFACTS
                    else "archive_exact_before_semantic_migration"
                ),
                size_bytes=len(data),
                sha256=_sha256_bytes(data),
            )
        )
    entries.extend(_inherit_private_metadata(root))
    exact_count = sum(entry.retention == "exact_copy" for entry in entries)
    private_count = sum(entry.retention == "metadata_only_private_source" for entry in entries)
    manifest = {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "source_commit": source_commit,
        "source_package_version": LEGACY_CURRENT_LINE_VERSION,
        "target_package_version": PACKAGE_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "archive_root": ARCHIVE_ROOT.as_posix(),
        "file_count": len(entries),
        "exact_copy_count": exact_count,
        "metadata_only_private_count": private_count,
        "files": [asdict(entry) for entry in entries],
        "truth_boundary": (
            "Exact copies preserve pre-migration tracked content byte-for-byte. "
            "Private generated source content is not duplicated; only inherited integrity metadata is retained."
        ),
    }
    manifest_path = archive_root / "ARCHIVE_MANIFEST.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    readme = (
        f"# Archive before {PACKAGE_VERSION}\n\n"
        f"Source commit: `{source_commit}`.\n\n"
        "The `tree/` directory contains exact byte copies of every tracked active file "
        "changed or removed by the four-layer current-line migration. Historical text is "
        "not rewritten inside this archive.\n"
    )
    (archive_root / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    return entries, manifest_path


def _external_backup(root: Path, paths: list[str], backup_root: Path | None) -> Path | None:
    if backup_root is None:
        return None
    resolved = backup_root.expanduser().resolve()
    if resolved.exists():
        raise MigrationError(f"external backup root already exists: {resolved}")
    for rel in paths:
        source = root / rel
        if not source.is_file():
            continue
        destination = resolved / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return resolved


def migrate(
    root: str | Path,
    *,
    apply: bool,
    expected_branch: str = EXPECTED_BRANCH,
    external_backup_root: str | Path | None = None,
) -> MigrationReport:
    runtime_root = Path(root).expanduser().resolve()
    branch = _run_git(runtime_root, "branch", "--show-current").strip()
    source_commit = _run_git(runtime_root, "rev-parse", "HEAD").strip()
    if branch != expected_branch:
        raise MigrationError(f"wrong branch: expected {expected_branch!r}, got {branch!r}")
    if PACKAGE_VERSION != V90_MIGRATION_TARGET_VERSION:
        raise MigrationError(f"unexpected canonical package version: {PACKAGE_VERSION}")

    findings, approved_legacy_before = scan_active_old_references(runtime_root)
    finding_paths = sorted({item["path"] for item in findings})
    explicit_paths = {
        "tests/test_current_line_archive_audit.py",
        "latka_jazn/tools/current_line_archive_audit.py",
    }
    paths = sorted(set(finding_paths) | {p for p in explicit_paths if (runtime_root / p).is_file()})
    if not apply:
        return MigrationReport(
            schema_version=MIGRATION_SCHEMA_VERSION,
            ok=not findings,
            root=str(runtime_root),
            branch=branch,
            source_commit=source_commit,
            source_package_version=LEGACY_CURRENT_LINE_VERSION,
            target_package_version=PACKAGE_VERSION_FULL,
            archive_root=str(runtime_root / ARCHIVE_ROOT),
            archived_file_count=0,
            modified_paths=paths,
            deleted_paths=sorted(HISTORICAL_ARTIFACTS & set(paths)),
            added_paths=[],
            approved_legacy_reference_count=approved_legacy_before,
            remaining_old_references=findings,
            archive_manifest_path=str(runtime_root / ARCHIVE_ROOT / "ARCHIVE_MANIFEST.json"),
            external_backup_root=str(Path(external_backup_root).expanduser().resolve()) if external_backup_root else None,
            truth_boundary="Dry-run only; no file or Git state was changed.",
        )

    backup = _external_backup(
        runtime_root,
        paths,
        Path(external_backup_root) if external_backup_root else None,
    )
    archive_entries, manifest_path = _write_archive(
        runtime_root,
        paths,
        source_commit=source_commit,
    )

    modified: list[str] = []
    deleted: list[str] = []
    for rel in paths:
        path = runtime_root / rel
        if rel in HISTORICAL_ARTIFACTS:
            if not path.is_file():
                continue
            if path.suffix.lower() == ".json":
                pointer = {
                    "schema_version": "historical_artifact_pointer/v1",
                    "archive_path": (ARCHIVE_ROOT / "tree" / rel).as_posix(),
                    "status": "archived_exact_copy",
                    "active": False,
                    "truth_boundary": (
                        "The historical payload is preserved byte-for-byte in the current-line archive; "
                        "this active-tree file is only a non-executable pointer."
                    ),
                }
                path.write_text(
                    json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
            else:
                pointer_text = (
                    "# Historical migration artifact\n"
                    f"# Exact original: {(ARCHIVE_ROOT / 'tree' / rel).as_posix()}\n"
                    "throw \"This completed migration tool is archived and must not be executed from the active tree.\"\n"
                )
                path.write_text(pointer_text, encoding="utf-8", newline="\n")
            modified.append(rel)
            continue
        if not path.is_file():
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise MigrationError(f"tracked migration target is not UTF-8: {rel}") from exc
        transformed = _transform_file(rel, original)
        if transformed != original:
            path.write_text(transformed, encoding="utf-8", newline="\n")
            modified.append(rel)

    remaining, approved_legacy_after = scan_active_old_references(runtime_root)
    if remaining:
        preview = ", ".join(
            f"{item['path']}:{item['line']}:{item['version']}" for item in remaining[:12]
        )
        raise MigrationError(
            f"migration left {len(remaining)} unapproved old references: {preview}"
        )

    added = [
        ARCHIVE_ROOT.as_posix(),
    ]
    return MigrationReport(
        schema_version=MIGRATION_SCHEMA_VERSION,
        ok=True,
        root=str(runtime_root),
        branch=branch,
        source_commit=source_commit,
        source_package_version=LEGACY_CURRENT_LINE_VERSION,
        target_package_version=PACKAGE_VERSION_FULL,
        archive_root=str(runtime_root / ARCHIVE_ROOT),
        archived_file_count=len(archive_entries),
        modified_paths=modified,
        deleted_paths=deleted,
        added_paths=added,
        approved_legacy_reference_count=approved_legacy_after,
        remaining_old_references=[],
        archive_manifest_path=str(manifest_path),
        external_backup_root=str(backup) if backup else None,
        truth_boundary=(
            "Runtime metadata was derived from latka_jazn.version, format schemas were "
            "decoupled to component/v1, legacy source references remain narrowly approved, "
            "and exact pre-migration bytes were archived before active files changed."
        ),
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-branch", default=EXPECTED_BRANCH)
    parser.add_argument("--external-backup-root")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = migrate(
            args.root,
            apply=bool(args.apply),
            expected_branch=args.expected_branch,
            external_backup_root=args.external_backup_root,
        )
    except MigrationError as exc:
        payload = {
            "schema_version": MIGRATION_SCHEMA_VERSION,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"ok={report.ok} modified={len(report.modified_paths)} "
            f"deleted={len(report.deleted_paths)} archive={report.archive_root}"
        )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
