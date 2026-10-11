from __future__ import annotations

import json
import os
from pathlib import Path
import hashlib
import subprocess
import sys
import zipfile

import pytest

from latka_jazn.version import PACKAGE_VERSION, PACKAGE_VERSION_FULL
from tools.jazn_pack_generator_app.constants import SYSTEM_BOOTSTRAP_REQUIRED_FILES
from tools.jazn_pack_generator_app.manifest import build_host_bootstrap_contract
from tools.jazn_pack_generator_app.models import ContentMode, PackPlan, PackRequest, SourceEntry

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "latka_jazn/resources/chatgpt_startup_evidence_contract.json"


def test_startup_instructions_and_manifests_have_one_exact_file_identity_policy() -> None:
    manifest = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    startup = json.loads((ROOT / "latka_jazn/resources/startup_contract.json").read_text(encoding="utf-8"))
    loader = (ROOT / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")
    host = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")
    assert len(loader) <= 5000
    assert startup["version"] == PACKAGE_VERSION
    assert manifest["file_discovery"]["file_id_guessing_allowed"] is False
    assert manifest["materialization"]["missing_or_empty_artifacts_result"] == "failed"
    assert manifest["materialization"]["callable_interface_is_success"] is False
    assert startup["chatgpt_startup_evidence_manifest"] in SYSTEM_BOOTSTRAP_REQUIRED_FILES
    assert startup["chatgpt_materialization_requires_exact_discovered_file_id"] is True
    assert startup["chatgpt_materialization_empty_artifacts_is_failure"] is True
    assert startup["chatgpt_tool_citations_require_observed_invocation"] is True
    for source in (loader, host):
        assert "file_id" in source
        assert "artifacts" in source
        assert "SHA-256" in source
    assert "Nie cytuj wyniku narzędzia" in loader
    assert "library_materialize_available=true" in host
    assert manifest["diagnostics"]["no_fabricated_tool_citations"] is True


def test_packager_requires_startup_evidence_contract(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    items = [SourceEntry(source=source_root / item, archive_path=item, size_bytes=1, is_dir=False) for item in SYSTEM_BOOTSTRAP_REQUIRED_FILES]
    plan = PackPlan(request=PackRequest(source_root=source_root, output_root=tmp_path / "out", content=ContentMode.SYSTEM), package_version=PACKAGE_VERSION_FULL, package_basename="test.system.zip", entries=tuple(items), excluded=(), source_total_size_bytes=len(items))
    contract = build_host_bootstrap_contract(plan)
    assert contract["active_system_root_eligible"] is True
    assert contract["startup_evidence_contract_member"] == startup_path()
    assert contract["materialization_interface_callable_proves_success"] is False
    assert contract["tool_citations_require_actual_invocation"] is True


def startup_path() -> str:
    return "latka_jazn/resources/chatgpt_startup_evidence_contract.json"


def test_host_report_hej_failure_not_misclassified_as_success(tmp_path: Path) -> None:
    # Replays the *observed facts* of the 2026-10-09 incident; no invented remote status.
    from latka_jazn.bootstrap.chatgpt_host_preflight import HostDiscoveryEvidence, plan_chatgpt_host_preflight
    from latka_jazn.core.chatgpt_host_executor_contract import HostExecutorObservation
    decision = plan_chatgpt_host_preflight(
        [], discovery_evidence=HostDiscoveryEvidence(
            library_search_available=True, library_materialize_available=True,
            system_search_attempted=True, system_candidate_found=True
        )
    )
    assert decision.executor_available is None
    assert decision.remote_runtime_available is None
    assert decision.bootstrap_allowed is False
    assert decision.library_materialize_available is True  # Interface, not file materialization.


@pytest.mark.skipif(not os.environ.get("JAZN_HOST_SYSTEM_ZIP"), reason="Optional real host ZIP E2E requires JAZN_HOST_SYSTEM_ZIP")
def test_real_host_system_zip_bootstrap_e2e(tmp_path: Path) -> None:
    archive = Path(os.environ["JAZN_HOST_SYSTEM_ZIP"])
    sidecar = Path(os.environ["JAZN_HOST_SYSTEM_SHA256_FILE"])
    assert archive.is_file() and sidecar.is_file()
    expected = sidecar.read_text(encoding="utf-8").split()[0]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        assert set(SYSTEM_BOOTSTRAP_REQUIRED_FILES).issubset(zf.namelist())
        helper = tmp_path / "CHATGPT_BOOTSTRAP.py"
        helper.write_bytes(zf.read("CHATGPT_BOOTSTRAP.py"))
    result = subprocess.run([sys.executable, str(helper), "--zip", str(archive), "--sha256-file", str(sidecar), "--destination", str(tmp_path / "operator"), "--post-materialization-preflight", "--json"],capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload.get("state") == "materialized_operator_ready"
    assert (tmp_path / "operator" / startup_path()).is_file()
