from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core import bridge_discovery
from latka_jazn.core.host_media_resources import detect_media_lookup, media_resource_catalog
from latka_jazn.core.host_tool_capabilities import (
    build_host_tool_capability_snapshot,
    resolve_policy_tool_availability,
)
from latka_jazn.core.host_tool_turn_policy import (
    build_host_tool_turn_policy,
    validate_tool_evidence_against_policy,
)
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


def test_v65_missing_host_manifest_does_not_claim_tool_verification() -> None:
    snapshot = build_host_tool_capability_snapshot(env={})

    assert snapshot["status"] == "host_manifest_missing"
    assert snapshot["manifest_present"] is False
    assert snapshot["verified_tools"] == []
    assert "web.run" in snapshot["unknown_tools"]
    assert "GitHub" in snapshot["unknown_tools"]
    assert "image_gen" in snapshot["unknown_tools"]
    assert snapshot["discovery_contract"]["runtime_local_module_introspection_is_not_host_tool_discovery"] is True
    assert snapshot["discovery_contract"]["mutating_or_private_data_probe_for_capability_only"] is False


def test_v65_explicit_host_manifest_filters_turn_tools_fail_closed() -> None:
    snapshot = build_host_tool_capability_snapshot(
        {
            "schema_version": "host_tool_capability_manifest/v1",
            "tools": [
                {"name": "web.run", "available": True, "operations": ["search", "open"]},
                {"name": "GitHub", "available": False},
                {"name": "image_gen", "available": True},
            ],
        },
        env={},
    )
    resolved = resolve_policy_tool_availability(
        ["web.run", "GitHub", "image_gen"],
        snapshot=snapshot,
    )

    assert snapshot["strict_availability"] is True
    assert snapshot["advertised_tools"] == ["image_gen", "web.run"]
    assert snapshot["unavailable_tools"] == ["GitHub"]
    assert resolved["allowed_tools"] == ["web.run", "image_gen"]
    assert resolved["unavailable_requested_tools"] == ["GitHub"]


def test_v65_successful_real_tool_evidence_upgrades_advertised_to_verified() -> None:
    snapshot = build_host_tool_capability_snapshot(
        {"tools": [{"name": "web.run", "available": True}]},
        env={},
        observations=[
            {
                "tool": "web.run",
                "operation": "public_search",
                "ok": True,
                "source": "host_tool_result",
            }
        ],
    )

    assert snapshot["status"] == "verified"
    assert snapshot["verified_tools"] == ["web.run"]
    assert snapshot["capability_confirmation_required_for_tools"] == []


def test_v65_mutating_and_private_tools_are_never_auto_probed_for_discovery() -> None:
    snapshot = build_host_tool_capability_snapshot(
        {
            "tools": [
                {"name": "GitHub", "available": True},
                {"name": "image_gen", "available": True},
                {"name": "file_search", "available": True},
                {"name": "automations", "available": True},
            ]
        },
        env={},
    )
    probes = {item["tool"]: item for item in snapshot["probe_plan"]}

    assert probes["GitHub"]["probe_mode"] == "read_only_suboperation_only"
    assert probes["GitHub"]["automatic_probe_allowed"] is True
    assert probes["image_gen"]["automatic_probe_allowed"] is False
    assert probes["file_search"]["automatic_probe_allowed"] is False
    assert probes["automations"]["automatic_probe_allowed"] is False


def test_v65_unknown_host_extension_defaults_to_no_automatic_probe() -> None:
    snapshot = build_host_tool_capability_snapshot(
        {"tools": [{"name": "custom.weather.lookup", "available": True}]},
        env={},
    )
    custom = next(item for item in snapshot["tools"] if item["name"] == "custom.weather.lookup")
    probe = next(item for item in snapshot["probe_plan"] if item["tool"] == "custom.weather.lookup")

    assert custom["catalog_known"] is False
    assert custom["destructive_hint"] is True
    assert custom["reported_annotations_trusted_for_authorization"] is False
    assert probe["automatic_probe_allowed"] is False


def test_v65_media_resource_catalog_expands_lookup_beyond_original_tokens() -> None:
    deezer = detect_media_lookup("Sprawdź https://www.deezer.com/track/3135556 i ten remiks.")
    tidal = detect_media_lookup("Posłuchaj proszę wersji live na https://tidal.com/browse/track/123")
    metadata = detect_media_lookup("Znajdź wydanie w MusicBrainz albo Discogs.")
    resources = {item["name"] for item in media_resource_catalog()}

    assert deezer["media_lookup"] is True
    assert "deezer" in deezer["matched_resources"]
    assert tidal["media_lookup"] is True
    assert "tidal" in tidal["matched_resources"]
    assert metadata["media_lookup"] is True
    assert {"musicbrainz", "discogs", "spotify", "youtube"}.issubset(resources)
    assert deezer["playback_or_hearing_claim_allowed"] is False


def test_v65_required_web_tool_unavailable_is_explicit_policy_violation() -> None:
    snapshot = build_host_tool_capability_snapshot(
        {"tools": [{"name": "web.run", "available": False}]},
        env={},
    )
    policy = build_host_tool_turn_policy(
        user_text="Sprawdź https://example.com i opisz źródło.",
        detected_intent="external_research_request",
        route="external_research",
        nlg_plan={"source_policy": "requires_external_web"},
        host_tool_capabilities=snapshot,
    )
    violations = validate_tool_evidence_against_policy([], policy)

    assert policy["requested_tools"] == ["web.run"]
    assert policy["allowed_tools"] == []
    assert policy["required_tools_unavailable"] == ["web.run"]
    assert "required_host_tool_unavailable:web.run" in violations


def test_v65_bridge_discovery_exposes_host_tool_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        bridge_discovery,
        "status_daemon",
        lambda *_args, **_kwargs: {"active_state": "inactive"},
    )
    monkeypatch.setenv(
        "JAZN_HOST_TOOL_CAPABILITIES_JSON",
        '{"tools":[{"name":"web.run","available":true},{"name":"GitHub","available":true}]}',
    )

    payload = bridge_discovery.discover_runtime_bridges(JaznConfig(root=tmp_path))

    capabilities = payload["host_tool_capabilities"]
    assert capabilities["manifest_present"] is True
    assert capabilities["manifest_source"] == "env:JAZN_HOST_TOOL_CAPABILITIES_JSON"
    assert capabilities["advertised_tools"] == ["GitHub", "web.run"]
    assert payload["chatgpt_bridge"]["host_tool_capability_discovery"]["probe_policy"].startswith(
        "automatic_probe_read_only_only"
    )


def test_v65_release_identity() -> None:
    assert PACKAGE_VERSION == "16.3.25.5.65"
    assert PACKAGE_RELEASE_NAME == "host-tool-capability-discovery-convergence"
