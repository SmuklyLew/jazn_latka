from __future__ import annotations

import ast
import importlib.metadata
from pathlib import Path
import sys
import time
from typing import Any, Iterable

from .common import (
    activation_profile_names, canonicalize_distribution_name, dedupe_requirements,
    current_platform_alias, default_wheelhouse_root, distribution_name_from_requirement,
    environment_marker_path, load_profile_registry, project_dependency_groups, runtime_version,
)
from .environment import dependency_activation_status
from .wheelhouse import discover_bundles


def _iter_python_files(root: Path) -> Iterable[Path]:
    candidates: list[Path] = []
    for directory in (root / "latka_jazn", root / "tools"):
        if directory.is_dir():
            candidates.extend(directory.rglob("*.py"))
    candidates.extend(path for path in (root / "main.py", root / "run.py") if path.is_file())
    for path in sorted(set(candidates)):
        parts = set(path.relative_to(root).parts)
        if "local_resources" not in parts and "__pycache__" not in parts and ".archives" not in parts:
            yield path


def scan_external_imports(root: Path | str) -> dict[str, Any]:
    project_root = Path(root).resolve()
    imports: dict[str, list[str]] = {}
    parse_errors: list[dict[str, str]] = []
    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    for path in _iter_python_files(project_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            parse_errors.append({"path": str(path.relative_to(project_root)), "error": f"{type(exc).__name__}:{exc}"})
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".", 1)[0]]
            for name in names:
                if not name or name in stdlib or name in {"latka_jazn", "main", "run", "__future__"}:
                    continue
                imports.setdefault(name, [])
                relative = path.relative_to(project_root).as_posix()
                if relative not in imports[name]:
                    imports[name].append(relative)
    return {"imports": {key: sorted(value) for key, value in sorted(imports.items())}, "parse_errors": parse_errors, "file_count": sum(1 for _ in _iter_python_files(project_root))}


def audit_project_dependencies(root: Path | str) -> dict[str, Any]:
    project_root = Path(root).resolve()
    base, optional = project_dependency_groups(project_root)
    requirements = dedupe_requirements([*base, *(item for values in optional.values() for item in values)])
    declared = {distribution_name_from_requirement(item): item for item in requirements}
    report = scan_external_imports(project_root)
    overrides = load_profile_registry(project_root).get("import_name_overrides") or {}
    import_to_dist = {str(import_name): canonicalize_distribution_name(str(dist)) for dist, import_name in overrides.items()}
    try:
        installed_mapping = importlib.metadata.packages_distributions()
    except Exception:
        installed_mapping = {}
    mapped: dict[str, Any] = {}
    unresolved: dict[str, list[str]] = {}
    for import_name, locations in report["imports"].items():
        distribution = import_to_dist.get(import_name)
        if distribution is None:
            candidates = installed_mapping.get(import_name) or []
            if candidates:
                distribution = canonicalize_distribution_name(str(candidates[0]))
        if distribution is None:
            guess = canonicalize_distribution_name(import_name)
            distribution = guess if guess in declared else None
        if distribution is None or distribution not in declared:
            unresolved[import_name] = locations
        else:
            mapped[import_name] = {"distribution": distribution, "requirement": declared[distribution], "locations": locations}
    return {
        "schema_version": "jazn_dependency_audit/v1", "ok": not report["parse_errors"],
        "runtime_version": runtime_version(), "project_root": str(project_root),
        "declared_base_requirements": base, "declared_optional_groups": optional,
        "declared_distribution_count": len(declared), "external_import_count": len(report["imports"]),
        "mapped_external_imports": mapped, "undeclared_or_unmapped_external_imports": unresolved,
        "source_parse_errors": report["parse_errors"], "activation": dependency_activation_status(project_root),
        "wheelhouse_root": str(default_wheelhouse_root(project_root)), "environment_marker": str(environment_marker_path(project_root)),
        "truth_boundary": "AST audit compares candidate external imports with declarations. Dynamic imports/plugins may need explicit mappings and are not guessed.",
    }


def benchmark_dependency_layer(root: Path | str, *, wheelhouse_root: Path | str | None = None) -> dict[str, Any]:
    project_root = Path(root).resolve()
    started = time.perf_counter(); activation = dependency_activation_status(project_root); activation_seconds = time.perf_counter() - started
    verify_started = time.perf_counter()
    bundles = discover_bundles(project_root, wheelhouse_root=wheelhouse_root, required_profiles=activation_profile_names(project_root), python_version=f"{sys.version_info.major}.{sys.version_info.minor}", platform_alias=current_platform_alias(), verify=True)
    verify_seconds = time.perf_counter() - verify_started
    verified = [item for item in bundles if (item.get("verification") or {}).get("ok") is True]
    total_bytes = sum(int((item.get("manifest") or {}).get("total_size_bytes") or 0) for item in verified)
    return {"schema_version": "jazn_dependency_benchmark/v1", "ok": True, "activation_probe_seconds": round(activation_seconds, 6), "wheelhouse_verify_seconds": round(verify_seconds, 6), "matching_bundle_count": len(bundles), "verified_bundle_count": len(verified), "verified_bundle_total_bytes": total_bytes, "activation": activation, "truth_boundary": "Benchmark measures local inspection and wheelhouse verification only; it performs no network download."}
