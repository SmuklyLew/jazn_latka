from types import SimpleNamespace
import pytest

from latka_jazn.core.conversation_runner import ConversationRunner
from latka_jazn.core.runtime_session import JaznRuntimeSession
from latka_jazn.core.conversation_turn_api import TurnRequest, TurnHandle, ResumeRequest, TurnStateMachine
from latka_jazn.runtime.turn_runtime import TurnPhase, TurnProtocolViolation, ProfessionalTurnRuntime


class Gateway:
    def __init__(self):
        self.submissions = []
        self.polls = []
        self.disconnected = False

    def chat(self, message, *, session_id=None, request_id=None):
        self.submissions.append((message, session_id, request_id))
        if self.disconnected:
            raise TimeoutError("response lost after durable submission")
        return {"request_id": request_id, "accepted": True, "done": False, "job_status": "queued"}

    def result(self, request_id):
        self.polls.append(request_id)
        return {"request_id": request_id, "host_finalization_pending": True}


def test_alias_and_transport_view_do_not_create_second_runtime_owner():
    assert JaznRuntimeSession is ConversationRunner
    runner = ConversationRunner.for_transport(Gateway())
    assert not hasattr(runner, "engine")
    assert not hasattr(runner, "composition")
    assert not hasattr(runner, "state_store")


def test_submit_snapshot_resume_and_restart_keep_exact_identity_without_post_replay():
    gateway = Gateway()
    runner = ConversationRunner.for_transport(gateway)
    handle = runner.submit_turn(TurnRequest("  exact user text\n", "request-1", "session-1"))
    assert gateway.submissions == [("  exact user text\n", "session-1", "request-1")]
    assert runner.submitted_snapshot(handle).phase is TurnPhase.POLLING
    assert gateway.polls == []
    with pytest.raises(TurnProtocolViolation, match="already_submitted"):
        runner.submit_turn(TurnRequest("different text", "request-1", "session-1"))
    assert runner.resume_turn(ResumeRequest(handle)).phase is TurnPhase.AWAITING_HOST_FINALIZATION
    restarted = ConversationRunner.for_transport(gateway)
    assert restarted.resume_turn(ResumeRequest(handle)).phase is TurnPhase.AWAITING_HOST_FINALIZATION
    assert gateway.polls == ["request-1", "request-1"]
    assert len(gateway.submissions) == 1


def test_transport_loss_allows_resume_only_and_never_resubmits():
    gateway = Gateway()
    gateway.disconnected = True
    runner = ConversationRunner.for_transport(gateway)
    request = TurnRequest("one turn", "ambiguous", "session")
    with pytest.raises(TimeoutError):
        runner.submit_turn(request)
    with pytest.raises(TurnProtocolViolation, match="already_submitted"):
        runner.submit_turn(request)
    gateway.disconnected = False
    assert runner.resume_turn(ResumeRequest(TurnHandle("ambiguous", "session"))).phase is TurnPhase.AWAITING_HOST_FINALIZATION
    assert len(gateway.submissions) == 1


@pytest.mark.parametrize("status", ["cancelled", "expired", "failed", "rejected"])
def test_terminal_job_states_cannot_become_visible(status):
    machine = TurnStateMachine(TurnHandle("terminal"), TurnPhase.SUBMITTED)
    assert machine.observe({"request_id": "terminal", "job_status": status}).phase is TurnPhase.FAILED
    with pytest.raises(TurnProtocolViolation, match="illegal_turn_transition"):
        machine.transition(TurnPhase.ACCEPTED_VISIBLE)


def test_claimed_acceptance_without_exact_envelope_and_gates_is_not_success():
    machine = TurnStateMachine(TurnHandle("forged"), TurnPhase.SUBMITTED)
    snapshot = machine.observe({"request_id": "forged", "answer_ok": True,
                                "accepted_visible_turn_ready": True, "final_visible_text": "fake"})
    assert snapshot.phase is TurnPhase.POLLING
    with pytest.raises(TurnProtocolViolation, match="request_id_mismatch"):
        machine.observe({"request_id": "other"})


def test_two_session_handles_cannot_alias_and_worker_rejects_foreign_session_before_execution():
    runner = ConversationRunner.for_transport(Gateway())
    handle = runner.submit_turn(TurnRequest("one", "shared-id", "session-1"))
    with pytest.raises(TurnProtocolViolation, match="session_mismatch"):
        runner.poll_turn(TurnHandle(handle.request_id, "session-2"))
    worker = object.__new__(ConversationRunner)
    setattr(worker, "state", SimpleNamespace(session_id="owned"))
    with pytest.raises(TurnProtocolViolation, match="owner_mismatch"):
        worker.execute_turn(TurnRequest("two", "r2", "foreign"))


def test_state_machine_uses_the_existing_transition_policy():
    for current in TurnPhase:
        for target in TurnPhase:
            if current is target and current is not TurnPhase.POLLING:
                continue
            machine = TurnStateMachine(TurnHandle("policy"), current)
            if ProfessionalTurnRuntime.transition_allowed(current, target):
                machine.transition(target)
                assert machine.phase is target
            else:
                with pytest.raises(TurnProtocolViolation):
                    machine.transition(target)
