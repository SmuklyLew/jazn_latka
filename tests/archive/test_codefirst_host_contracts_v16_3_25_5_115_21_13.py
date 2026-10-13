from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from latka_jazn.mcp.finalization_input import MAX_HOST_FINAL_TEXT_BYTES, validated_final_text_digest
from latka_jazn.mcp.host_guidance import MCP_HOST_TURN_INSTRUCTIONS
from tools.docs_truth_audit import ACTIVE_DOCUMENT_MARKERS, audit

ROOT = Path(__file__).resolve().parents[1]


def test_adapter_computes_utf8_bytes_not_codepoints():
    text = "Zażółć 🐾"
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert validated_final_text_digest(text) == expected
    assert validated_final_text_digest(text, expected.upper()) == expected


def test_adapter_rejects_mismatched_or_malformed_sha_fail_closed():
    for invalid in ("f" * 64, "not-a-hash", "", 5):
        with pytest.raises(ValueError):
            validated_final_text_digest("Łatka", invalid)


def test_adapter_rejects_empty_invalid_and_byte_oversize():
    with pytest.raises(ValueError):
        validated_final_text_digest("")
    with pytest.raises(ValueError):
        validated_final_text_digest(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        validated_final_text_digest("🦊" * (MAX_HOST_FINAL_TEXT_BYTES // 4 + 1))


def test_host_guidance_is_shared_and_not_a_runtime_claim():
    assert "jazn_status" in MCP_HOST_TURN_INSTRUCTIONS
    assert "jazn_finalize_reply" in MCP_HOST_TURN_INSTRUCTIONS
    assert "never submit" in MCP_HOST_TURN_INSTRUCTIONS
    assert "not live runtime evidence" in MCP_HOST_TURN_INSTRUCTIONS
    assert "MCP_HOST_TURN_INSTRUCTIONS" in (ROOT / 'latka_jazn/mcp/server.py').read_text()
    assert "instructions=MCP_HOST_TURN_INSTRUCTIONS" in (ROOT / 'latka_jazn/mcp/http_gateway.py').read_text()


def test_public_adapter_validates_before_canonical_finalize_dispatch():
    source = (ROOT / 'latka_jazn/mcp/http_gateway.py').read_text()
    assert "final_visible_text_sha256: Sha256Hex | None = None" in source
    assert "computed_sha256 = validated_final_text_digest" in source
    assert '"final_text_sha256": computed_sha256' in source


def test_active_docs_metadata_and_deployment_are_consistent():
    result = audit(ROOT)
    assert result["ok"], result["errors"]


def test_doc_audit_detects_both_stale_doc_and_runtime_identity(tmp_path: Path):
    for name in ACTIVE_DOCUMENT_MARKERS:
        dst = tmp_path / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dst)
    for name in ('latka_jazn/version.py', 'latka_jazn/mcp/chatgpt_toolset.py',
                 'latka_jazn/resources/chatgpt_startup_evidence_contract.json',
                 'deploy/chatgpt_mcp/deployment.contract.json'):
        dst=tmp_path / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name,dst)
    doc=tmp_path/'docs/README.md'
    doc.write_text(doc.read_text().replace('**Wersja bieżąca:** dynamiczna', '**Wersja bieżąca:** 2025'))
    dep=tmp_path/'deploy/chatgpt_mcp/deployment.contract.json'
    j=json.loads(dep.read_text());j['runtime_version']='old-version';dep.write_text(json.dumps(j))
    result=audit(tmp_path)
    assert not result['ok']
    assert 'deployment_runtime_version_mismatch' in result['errors']
    assert 'missing_dynamic_or_historical_marker:docs/README.md' in result['errors']
