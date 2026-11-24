from __future__ import annotations

from pathlib import Path

import pytest

from tools.jazn_pack_generator_app.constants import (
    HOST_BOOTSTRAP_CONTRACT_SCHEMA,
    SYSTEM_BOOTSTRAP_REQUIRED_FILES,
)
from tools.jazn_pack_generator_app.errors import PackValidationError
from tools.jazn_pack_generator_app.manifest import (
    build_host_bootstrap_contract,
    validate_system_bootstrap_contract,
)
from tools.jazn_pack_generator_app.models import ContentMode, PackPlan, PackRequest, SourceEntry


def _plan(tmp_path: Path, *, content: ContentMode, members: tuple[str, ...]) -> PackPlan:
    source_root = tmp_path / "source"
    source_root.mkdir(exist_ok=True)
    entries = tuple(
        SourceEntry(
            source=source_root / name,
            archive_path=name,
            size_bytes=1,
            is_dir=False,
        )
        for name in members
    )
    return PackPlan(
        request=PackRequest(
            source_root=source_root,
            output_root=tmp_path / "out",
            content=content,
        ),
        package_version="16.3.25.5.72-test",
        package_basename="jazn_latka_v16.3.25.5.72-test.system.zip",
        entries=entries,
        excluded=(),
        source_total_size_bytes=len(entries),
    )


def test_system_manifest_declares_host_bootstrap_truth_boundary(tmp_path: Path) -> None:
    plan = _plan(
        tmp_path,
        content=ContentMode.SYSTEM,
        members=tuple(SYSTEM_BOOTSTRAP_REQUIRED_FILES),
    )

    contract = validate_system_bootstrap_contract(plan)

    assert contract["schema_version"] == HOST_BOOTSTRAP_CONTRACT_SCHEMA
    assert contract["applicable"] is True
    assert contract["active_system_root_eligible"] is True
    assert contract["missing_required_members"] == []
    assert contract["bootstrap_member"] == "CHATGPT_BOOTSTRAP.py"
    assert contract["entrypoint"] == "run.py"
    assert contract["control_plane"] == "main.py"
    assert contract["local_bootstrap_requires_process_creation"] is True
    assert contract["package_can_create_host_executor"] is False
    assert contract["remote_runtime_transport_bundled"] is False
    assert contract["host_capability_negotiation_required"] is True
    assert contract["supported_execution_routes"] == [
        "local_executor",
        "remote_runtime_external",
        "host_handoff",
    ]


def test_incomplete_system_package_fails_before_publication(tmp_path: Path) -> None:
    plan = _plan(
        tmp_path,
        content=ContentMode.SYSTEM,
        members=("run.py", "latka_jazn/version.py"),
    )

    with pytest.raises(PackValidationError, match="bootstrap-complete") as exc_info:
        validate_system_bootstrap_contract(plan)

    assert "CHATGPT_BOOTSTRAP.py" in str(exc_info.value)
    assert "main.py" in str(exc_info.value)


def test_memory_package_is_data_only_and_never_execution_capability(tmp_path: Path) -> None:
    plan = _plan(
        tmp_path,
        content=ContentMode.MEMORY,
        members=("memory/example.json",),
    )

    contract = build_host_bootstrap_contract(plan)

    assert contract["schema_version"] == HOST_BOOTSTRAP_CONTRACT_SCHEMA
    assert contract["applicable"] is False
    assert contract["content_role"] == "memory_data_only"
    assert contract["active_system_root_eligible"] is False
    assert contract["package_can_create_host_executor"] is False
