"""Dead acceptance markers permit diagnostics and guarded canonical start only."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from latka_jazn.core import acceptance_layout as a
from tools.jazn_run_studio import app


@pytest.fixture
def stopped(tmp_path, monkeypatch):
    root = tmp_path / 'system'
    root.mkdir()
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    marker = runtime / 'JAZN_ACTIVE_RUNTIME.json'
    marker.write_text('{}', encoding='utf-8')
    layout = a.AcceptanceLayout(root, runtime, tmp_path / 'op', runtime / 'memory')
    monkeypatch.setenv('JAZN_RUNTIME_WORKSPACE_DIR', str(runtime))
    state = dict(active_state='inactive', active_state_reason='daemon_process_not_confirmed',
                 marker_valid=True, active_root=str(root), pid=12345,
                 pid_alive=False, pid_alive_os_probe=False, process_state='dead',
                 endpoint_reachable=False, package_integrity_verified=True,
                 source_provenance_verified=True)
    from latka_jazn.core import runtime_daemon
    monkeypatch.setattr(runtime_daemon, 'status_daemon', lambda *args, **kwargs: state)
    return layout, state, marker


def test_resume_refusal_identifies_dead_process_and_preserves_marker(stopped):
    layout, state, marker = stopped
    before = marker.read_bytes()
    with pytest.raises(ValueError, match='daemon_process_not_confirmed') as caught:
        a.validate_resumed_daemon(layout, 'http://127.0.0.1:8796')
    assert 'process=dead' in str(caught.value)
    assert '--run status' in str(caught.value)
    assert marker.read_bytes() == before


def test_dead_owned_marker_can_enter_canonical_start_without_deleting_state(stopped):
    layout, state, marker = stopped
    pending = layout.runtime / 'pending-request.json'
    pending.write_text('{"request_id":"same-request"}', encoding='utf-8')
    a.validate_isolated_daemon_start(layout, 'http://127.0.0.1:8796')
    assert marker.read_text() == '{}'
    assert pending.read_text() == '{"request_id":"same-request"}'


@pytest.mark.parametrize('field,value', [
    ('active_root', '/foreign/root'), ('marker_valid', False),
    ('pid_alive_os_probe', True), ('pid_alive_os_probe', None),
    ('pid_alive', True), ('endpoint_reachable', True),
    ('process_state', 'pid_reused'), ('process_state', 'not_observed'),
    ('package_integrity_verified', False), ('source_provenance_verified', False),
    ('pid', None), ('pid', True), ('pid', 0),
])
def test_start_refuses_foreign_live_unknown_or_unverified_state(stopped, field, value):
    layout, state, marker = stopped
    state[field] = value
    with pytest.raises(ValueError):
        a.validate_isolated_daemon_start(layout, 'http://127.0.0.1:8796')
    assert marker.read_text() == '{}'


def test_start_refuses_different_workspace_before_probe(stopped, monkeypatch):
    layout, state, marker = stopped
    monkeypatch.setenv('JAZN_RUNTIME_WORKSPACE_DIR', str(layout.runtime.parent / 'foreign'))
    with pytest.raises(ValueError, match='workspace'):
        a.validate_isolated_daemon_start(layout, 'http://127.0.0.1:8796')


def test_verified_existing_instance_can_be_reused_without_state_changes(stopped):
    layout, state, marker = stopped
    state.update(active_state='active_trusted', process_identity_confirmed=True,
                 endpoint_identity_matches=True, endpoint_heartbeat_fresh=True,
                 pid_alive=True, pid_alive_os_probe=True, endpoint_reachable=True,
                 process_state='active')
    a.validate_isolated_daemon_start(layout, 'http://127.0.0.1:8796')
    a.validate_resumed_daemon(layout, 'http://127.0.0.1:8796')
    assert marker.read_text() == '{}'


@pytest.mark.parametrize('action', ['status', 'doctor', 'supervisor', 'version', 'preflight', 'model', 'memory'])
def test_read_only_cli_diagnostics_do_not_adopt_untrusted_daemon(stopped, monkeypatch, action):
    layout, state, marker = stopped
    from contextlib import nullcontext
    monkeypatch.setattr(app, 'acceptance_environment', lambda root: nullcontext(layout))
    monkeypatch.setattr(app, 'apply_system_config', lambda *args: None)
    seen = []
    job = SimpleNamespace(done=SimpleNamespace(wait=lambda: None), key=action, state='succeeded')
    controller = SimpleNamespace(settings=SimpleNamespace(daemon_url='http://127.0.0.1:8796'),
                                 logs={}, start_action=lambda key: seen.append(key) or job)
    monkeypatch.setattr(app, 'Controller', lambda root: controller)
    monkeypatch.setattr(app, 'validate_resumed_daemon', lambda *args: pytest.fail('adoption gate called'))
    assert app.main(['--root', str(layout.system), '--isolated-acceptance', '--run', action]) == 0
    assert seen == [action]


def test_explicit_start_calls_guard_then_existing_control_plane(stopped, monkeypatch):
    layout, state, marker = stopped
    from contextlib import nullcontext
    monkeypatch.setattr(app, 'acceptance_environment', lambda root: nullcontext(layout))
    monkeypatch.setattr(app, 'apply_system_config', lambda *args: None)
    seen = []
    job = SimpleNamespace(done=SimpleNamespace(wait=lambda: None), key='start', state='succeeded')
    controller = SimpleNamespace(settings=SimpleNamespace(daemon_url='http://127.0.0.1:8796'),
                                 logs={}, start_action=lambda key: seen.append(key) or job)
    monkeypatch.setattr(app, 'Controller', lambda root: controller)
    monkeypatch.setattr(app, 'validate_isolated_daemon_start', lambda *args: seen.append('guard'))
    assert app.main(['--root', str(layout.system), '--isolated-acceptance', '--run', 'start']) == 0
    assert seen == ['guard', 'start']


@pytest.mark.parametrize('action', [None, 'stop', 'restart', 'package'])
def test_gui_and_other_mutations_still_require_full_resume_trust(stopped, monkeypatch, action):
    layout, state, marker = stopped
    from contextlib import nullcontext
    monkeypatch.setattr(app, 'acceptance_environment', lambda root: nullcontext(layout))
    monkeypatch.setattr(app, 'apply_system_config', lambda *args: None)
    monkeypatch.setattr(app, 'Controller', lambda root: SimpleNamespace(
        settings=SimpleNamespace(daemon_url='http://127.0.0.1:8796')))
    def refuse(*args):
        raise ValueError('Odmowa wznowienia')
    monkeypatch.setattr(app, 'validate_resumed_daemon', refuse)
    argv = ['--root', str(layout.system), '--isolated-acceptance']
    if action:
        argv += ['--run', action]
    assert app.main(argv) == 2
