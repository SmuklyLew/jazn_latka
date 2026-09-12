from __future__ import annotations

from latka_jazn.core.host_tool_capabilities import (
    build_host_tool_capability_snapshot,
    resolve_policy_tool_availability,
)


def test_unsupported_manifest_schema_fails_closed_for_policy_candidates() -> None:
    snapshot = build_host_tool_capability_snapshot(
        {
            "schema_version": "host_tool_capability_manifest/v999",
            "tools": [{"name": "web.run", "available": True}],
        },
        env={},
    )
    resolved = resolve_policy_tool_availability(["web.run"], snapshot=snapshot)

    assert snapshot["status"] == "manifest_or_observation_invalid"
    assert snapshot["policy_candidate_tools"] == []
    assert "unsupported_host_tool_manifest_schema:host_tool_capability_manifest/v999" in snapshot["errors"]
    assert resolved["allowed_tools"] == []
    assert resolved["unavailable_requested_tools"] == ["web.run"]


def test_duplicate_manifest_tool_fails_closed_instead_of_partially_authorizing() -> None:
    snapshot = build_host_tool_capability_snapshot(
        {
            "schema_version": "host_tool_capability_manifest/v1",
            "tools": [
                {"name": "web.run", "available": True},
                {"name": "web.run", "available": True},
            ],
        },
        env={},
    )

    assert snapshot["status"] == "manifest_or_observation_invalid"
    assert snapshot["policy_candidate_tools"] == []
    assert "duplicate_host_tool:web.run" in snapshot["errors"]


def test_invalid_manifest_tool_name_is_rejected_fail_closed() -> None:
    snapshot = build_host_tool_capability_snapshot(
        {
            "schema_version": "host_tool_capability_manifest/v1",
            "tools": [{"name": "web/run", "available": True}],
        },
        env={},
    )

    assert snapshot["status"] == "manifest_or_observation_invalid"
    assert snapshot["policy_candidate_tools"] == []
    assert any(error.startswith("invalid_host_tool_name:") for error in snapshot["errors"])
