from __future__ import annotations

from latka_jazn.bootstrap.chatgpt_host_preflight import plan_chatgpt_host_preflight
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostEnvironmentState,
    HostExecutorObservation,
    HostRecoveryAction,
)


def test_started_failed_command_blocks_bootstrap_even_when_another_bridge_failed() -> None:
    decision = plan_chatgpt_host_preflight(
        [
            HostExecutorObservation(
                process_created=False,
                error_class="ClientError",
                alternative_surface_available=False,
                surface="python_tool",
            ),
            HostExecutorObservation(
                process_created=True,
                command_completed=True,
                returncode=2,
                error_class="CalledProcessError",
                filesystem_probe_succeeded=False,
                surface="terminal",
            ),
        ],
        package_required=False,
    )

    assert decision.environment_state is HostEnvironmentState.DEGRADED
    assert decision.bootstrap_allowed is False
    assert decision.next_action is HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND
    assert decision.reason_code == "executor_command_requires_diagnosis"
    assert decision.canonical_resume_entrypoint is None
