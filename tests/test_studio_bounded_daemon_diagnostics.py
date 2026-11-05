"""Large negative status reports retain their cause in the bounded CLI log."""
import json
from pathlib import Path
import sys
import pytest

from tools.jazn_run_studio import app
from tools.jazn_run_studio.core import Controller, Settings


@pytest.mark.parametrize('secret', [None, 'root', 'process_events_log', 'SYSTEM',
                                    'daemon_process_not_confirmed', 'JSS_DAEMON_DIAGNOSTIC'])
def test_negative_status_cause_survives_log_rotation(tmp_path, monkeypatch, capsys, secret):
    if secret is not None:
        monkeypatch.setenv('JAZN_TEST_DIAGNOSTIC_TOKEN', secret)
    root = tmp_path / 'SYSTEM'
    for name in ('main.py', 'run.py', 'latka_jazn/version.py'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('PACKAGE_VERSION = "1.0.0"\nPACKAGE_RELEASE_NAME = "test"\n', encoding='utf-8')
    monkeypatch.setenv('JAZN_RUNTIME_WORKSPACE_DIR', str(tmp_path / 'runtime'))
    monkeypatch.setenv('JAZN_MEMORY_MODE', 'off')
    payload = dict(root=str(root), runtime_version_full='1.0.0-test',
                   daemon=dict(active_state='inactive', active_state_reason='daemon_process_not_confirmed',
                               process_state='dead', identity_state='unknown', heartbeat_state='stale', pid=12345,
                               endpoint_reachable=False, process_identity_confirmed=False,
                               endpoint_identity_matches=False, endpoint_heartbeat_fresh=None),
                   padding=list(range(3000)))
    core = Controller(root, Settings(daemon_url='http://127.0.0.1:8796'))
    script = 'import json; print(json.dumps(' + repr(payload) + ', indent=2)); raise SystemExit(1)'
    monkeypatch.setattr(core, 'command', lambda key: [sys.executable, '-X', 'utf8', '-c', script])
    monkeypatch.setattr(app, 'Controller', lambda selected: core)
    try:
        assert app.main(['--root', str(root), '--run', 'status']) == 1
        output = capsys.readouterr().out
        assert len(core.logs['status']) == 2500
        summary = next(line for line in output.splitlines() if line.startswith('JSS_DAEMON_DIAGNOSTIC '))
        data = json.loads(summary.removeprefix('JSS_DAEMON_DIAGNOSTIC '))
        assert data['active_state_reason'] == core.redactor.text('daemon_process_not_confirmed')
        assert data['process_state'] == 'dead'
        assert data['active_state'] == 'inactive'
        assert data['pid'] == 12345
        assert data['endpoint_reachable'] is False
        assert data['root'] == core.redactor.text(str(root.resolve()))
        assert data['process_events_log'] == core.redactor.text(str(tmp_path / 'runtime' / 'daemon' / 'process_events.jsonl'))
        assert 'padding' not in data
        assert data['accepted_visible_turn'] is False
        assert isinstance(data['root_matches'], bool)
        assert any(kind == 'log' and value == summary
                   for _, kind, value in list(core.events.queue))
        if secret == 'SYSTEM':
            assert 'SYSTEM' not in data['root']
            assert '[UKRYTO]' in data['root']
        # A child cannot forge the trusted internal event by printing its prefix.
        forged = 'JSS_DAEMON_DIAGNOSTIC {"root": "SYSTEM"}'
        core.emit('untrusted-child', 'log', forged)
        assert core.logs['untrusted-child'][-1] == core.redactor.text(forged)
        # Export must also retain keys and apply secrets loaded after capture.
        late_secret = str(tmp_path.resolve())
        core.redactor.values.insert(0, late_secret)
        exported = tmp_path / 'export.json'
        core.export_report(exported)
        report = json.loads(exported.read_text(encoding='utf-8'))
        exported_line = report['logs']['status'][-1]
        exported_data = json.loads(exported_line.removeprefix('JSS_DAEMON_DIAGNOSTIC '))
        assert exported_data['root'] == core.redactor.text(data['root'])
        assert '[UKRYTO]' in exported_data['root']
        assert exported_data['pid'] == 12345
        assert str(root.resolve()) not in exported.read_text(encoding='utf-8')
        assert late_secret not in exported.read_text(encoding='utf-8')
    finally:
        core.close()
