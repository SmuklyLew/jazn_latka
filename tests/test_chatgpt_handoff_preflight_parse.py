from __future__ import annotations

from latka_jazn.bootstrap.chatgpt_host_preflight_parse import executor_observation_from_mapping
from latka_jazn.core.chatgpt_host_handoff_state import HostHandoffState


def test_json_boundary_normalizes_declined_handoff_state() -> None:
    observation = executor_observation_from_mapping({
        "surface": "chat",
        "process_created": False,
        "error_class": "ExecutionUnavailable",
        "execution_handoff_available": True,
        "execution_handoff_state": "declined",
    })
    assert observation.execution_handoff_available is True
    assert observation.execution_handoff_state is HostHandoffState.DECLINED


def test_boolean_only_legacy_payload_maps_to_available() -> None:
    observation = executor_observation_from_mapping({
        "surface": "chat",
        "process_created": False,
        "error_class": "ExecutionUnavailable",
        "execution_handoff_available": True,
    })
    assert observation.execution_handoff_state is HostHandoffState.AVAILABLE
