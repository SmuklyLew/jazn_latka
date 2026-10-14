from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

import pytest

from latka_jazn.core.host_stdout_delivery import HostStdoutDeliveryError, write_complete_stdout
from latka_jazn.core.chatgpt_host_recovery import recover_committed_host_presentation
from latka_jazn.core.chatgpt_host_pending_store import HostRequestStoreError, read_committed_host_request
from latka_jazn.mcp.tools import jazn_resume_visible_reply
from latka_jazn.memory.availability import build_memory_availability_status, runtime_memory_storage_root
from test_finalization_crash_atomicity import _request, _finalize


class PartialTextStream:
    def __init__(self):
        self.chunks: list[str] = []

    def write(self, text: str) -> int:
        n = min(3, len(text))
        self.chunks.append(text[:n])
        return n

    def flush(self) -> None:
        pass


def test_host_stdout_delivers_utf8_exactly_over_short_writes():
    stream = PartialTextStream()
    write_complete_stdout(stream, '🫸🐾 Łatka\n')
    assert ''.join(stream.chunks) == '🫸🐾 Łatka\n'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX pipe injection fixture')
def test_host_stdout_nonblocking_pipe_slow_reader():
    read_fd, write_fd = os.pipe()
    original = os.get_blocking(write_fd)
    collected = bytearray()
    message = '🐾witaj' * 25000

    def consume():
        while True:
            chunk = os.read(read_fd, 4096)
            if not chunk:
                break
            collected.extend(chunk)

    worker = threading.Thread(target=consume)
    worker.start()
    try:
        with os.fdopen(write_fd, 'w', encoding='utf-8', closefd=False) as stream:
            write_complete_stdout(stream, message, timeout_seconds=5.0)
            assert os.get_blocking(write_fd) == original
    finally:
        os.close(write_fd)
        worker.join(timeout=5)
        os.close(read_fd)
    assert bytes(collected) == message.encode('utf-8')


@pytest.mark.skipif(os.name == 'nt', reason='POSIX pipe injection fixture')
def test_host_stdout_timeout_preserves_descriptor_mode():
    read_fd, write_fd = os.pipe()
    try:
        os.set_blocking(write_fd, False)
        with os.fdopen(write_fd, 'w', encoding='utf-8', closefd=False) as stream:
            with pytest.raises(HostStdoutDeliveryError, match='host_stdout_delivery_timeout'):
                write_complete_stdout(stream, 'X' * 1000000, timeout_seconds=0.08)
            assert os.get_blocking(write_fd) is False
    finally:
        os.close(read_fd)
        os.close(write_fd)


def _accepted(root: Path):
    reply = _request(root)
    result, errors = _finalize(root, reply)
    assert not errors and result is not None
    record = read_committed_host_request(root, turn_id=reply['turn_id'])
    daemon_id = str(
        record['binding'].get('daemon_request_id')
        or record['generation_context'].get('daemon_request_id')
        or reply['turn_id']
    )
    return reply, result, record, daemon_id


def test_committed_delivery_recovers_without_daemon_or_side_effects(tmp_path: Path):
    reply, result, record, daemon_id = _accepted(tmp_path)
    expected = result['final_visible_text']
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in tmp_path.rglob('*.json')}
    recovered = recover_committed_host_presentation(
        tmp_path, daemon_request_id=daemon_id, turn_id=reply['turn_id'],
        request_contract_hash=record['request_contract_hash'],
    )
    assert recovered and recovered['action'] == 'display_exact'
    assert recovered['final_visible_text'] == expected
    assert recovered['final_text_sha256'] == hashlib.sha256(expected.encode()).hexdigest()

    class DeadGateway:
        def result(self, request_id):
            raise AssertionError('accepted result must not be polled again')

    visible = jazn_resume_visible_reply.run(
        root=tmp_path, gateway=DeadGateway(), daemon_request_id=daemon_id,
        turn_id=reply['turn_id'], host_request_contract_hash=record['request_contract_hash'],
    )
    assert not visible['isError']
    assert visible['structuredContent']['action'] == 'display_exact'
    assert visible['structuredContent']['final_visible_text'] == expected
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in tmp_path.rglob('*.json')}
    assert before == after
    replay, replay_errors = _finalize(tmp_path, reply)
    assert replay is None and replay_errors == ['host_request:host_request_replay_detected']


def test_committed_delivery_refuses_wrong_hash_or_tamper(tmp_path: Path):
    reply, result, record, daemon_id = _accepted(tmp_path)
    assert recover_committed_host_presentation(tmp_path, daemon_request_id=daemon_id) is None
    with pytest.raises(HostRequestStoreError, match='contract_hash_mismatch'):
        recover_committed_host_presentation(
            tmp_path, daemon_request_id=daemon_id, request_contract_hash='0'*64)
    with pytest.raises(HostRequestStoreError, match='turn_mismatch'):
        recover_committed_host_presentation(
            tmp_path, daemon_request_id=daemon_id, turn_id='alien',
            request_contract_hash=record['request_contract_hash'])
    path = next(tmp_path.rglob('consumed/*.json'))
    data = json.loads(path.read_text(encoding='utf-8'))
    data['final_visible_capture']['final_visible_text'] += 'forgery'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(HostRequestStoreError, match='capture_binding_mismatch'):
        recover_committed_host_presentation(
            tmp_path, daemon_request_id=daemon_id,
            request_contract_hash=record['request_contract_hash'])


def test_core_generated_memory_directories_do_not_switch_sqlite_root(
    tmp_path: Path, monkeypatch
):
    root = tmp_path / 'system'
    root.mkdir()
    monkeypatch.delenv('JAZN_MEMORY_ROOT', raising=False)
    monkeypatch.setenv('JAZN_RUNTIME_WORKSPACE_DIR', str(tmp_path / 'workspace'))
    initial = runtime_memory_storage_root(root)
    memory_root = root / 'memory'
    (memory_root / 'sqlite' / 'runtime_write_v1').mkdir(parents=True)
    (memory_root / 'sqlite' / 'runtime_write_v1' / 'runtime_memory.sqlite3').write_bytes(b'operational')
    (memory_root / 'raw' / 'runtime_events').mkdir(parents=True)
    (memory_root / 'raw' / 'runtime_events' / 'events.jsonl').write_text('{}\n')
    (memory_root / 'layered').mkdir(parents=True)
    (memory_root / 'layered' / 'continuity.jsonl').write_text('{}\n')
    assert runtime_memory_storage_root(root) == initial
    assert not build_memory_availability_status(root).persistent_memory_enabled
    (memory_root / 'raw' / 'chat.html').write_text('authenticated legacy recall')
    assert build_memory_availability_status(root).persistent_memory_enabled
