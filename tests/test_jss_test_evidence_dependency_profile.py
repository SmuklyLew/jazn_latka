"""Evidence execution is optional, declared and visible to the real import audit."""
from pathlib import Path
import shutil

from latka_jazn.dependencies.audit import audit_project_dependencies
from latka_jazn.dependencies.common import (
    activation_profile_names, release_profile_names, resolve_profile_requirements,
)

ROOT = Path(__file__).resolve().parents[1]


def test_pytest_evidence_profile_is_resolvable_without_entering_core_or_release():
    selected = resolve_profile_requirements(ROOT, ["test-evidence"])
    assert selected == ["pytest>=8.3,<10"]
    assert not any(item.startswith("pytest") for item in resolve_profile_requirements(ROOT, activation_profile_names(ROOT)))
    assert not any(item.startswith("pytest") for item in resolve_profile_requirements(ROOT, release_profile_names(ROOT)))


def test_real_import_audit_resolves_the_evidence_adapter_dependency(tmp_path):
    # Audit only a tracked-source projection; do not scan local build venvs or
    # private neighboring files. The actual declarations/adapter are copied.
    fixture = tmp_path / "SYSTEM"
    (fixture / "latka_jazn/resources/dependencies").mkdir(parents=True)
    (fixture / "tools/jazn_run_studio").mkdir(parents=True)
    for relative in ("pyproject.toml", "latka_jazn/resources/dependencies/profiles.json",
                     "tools/jazn_run_studio/test_evidence_plugin.py"):
        shutil.copyfile(ROOT / relative, fixture / relative)
    report = audit_project_dependencies(fixture)
    assert report["source_parse_errors"] == []
    assert report["undeclared_or_unmapped_external_imports"] == {}
    assert report["mapped_external_imports"]["pytest"]["distribution"] == "pytest"
    assert report["mapped_external_imports"]["pytest"]["requirement"] == "pytest>=8.3,<10"
