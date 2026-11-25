"""Recovery after a writer exits abruptly and historical projection ordering."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

from latka_jazn.core.conversation_state_store import ConversationStateStore


def test_terminated_writer_releases_os_lock_and_allows_exact_projection(tmp_path: Path) -> None:
    store = ConversationStateStore(tmp_path)
    path = store._turn_path("s", "t")
    ready = tmp_path / "ready"
    code = (
        "import sys,time\n"
        "from pathlib import Path\n"
        "from latka_jazn.db.runtime_sqlite import runtime_sqlite_write_guard\n"
        "with runtime_sqlite_write_guard(Path(sys.argv[1])):\n"
        " Path(sys.argv[2]).write_text('ready',encoding='utf-8')\n"
        " time.sleep(30)\n"
    )
    child = subprocess.Popen([sys.executable, "-X", "utf8", "-c", code, str(path), str(ready)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    kwargs = {"session_id": "s", "turn_id": "t", "trace_id": "x",
              "user_text": "synthetic", "assistant_text": "synthetic response", "source": "test"}
    try:
        deadline = time.monotonic() + 8
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.is_file()
        assert store.append_finalized_turn(**kwargs, lock_timeout_seconds=0.1)["status"] == "turn_commit_lock_timeout"
    finally:
        if child.poll() is None:
            child.kill()  # Test-owned synthetic process, never an operator daemon.
        child.wait(timeout=5)
    assert store.append_finalized_turn(**kwargs)["status"] == "committed"
    assert store.append_finalized_turn(**kwargs)["status"] == "already_committed"
    assert len(list(path.parent.glob("*.json"))) == 1


def test_legacy_orphan_sentinel_cannot_block_recovery_or_be_deleted(tmp_path: Path) -> None:
    store = ConversationStateStore(tmp_path)
    old_lock = store._lock_path("s", "t")
    old_lock.parent.mkdir(parents=True)
    old_lock.write_text("legacy-stale-sentinel", encoding="utf-8")
    result = store.append_finalized_turn(session_id="s", turn_id="t", trace_id="x",
                                         user_text="synthetic", assistant_text="final", source="test")
    assert result["ok"] is True
    assert old_lock.read_text(encoding="utf-8") == "legacy-stale-sentinel"


def test_historical_projection_retains_acceptance_order_not_recovery_time(tmp_path: Path) -> None:
    store = ConversationStateStore(tmp_path)
    for turn, accepted in (("newer", "2026-11-25T12:01:00+00:00"),
                           ("older", "2026-11-25T12:00:00+00:00")):
        result = store.append_finalized_turn(session_id="s", turn_id=turn, trace_id=turn,
            user_text=turn, assistant_text=turn, source="test", accepted_at_utc=accepted)
        assert result["ok"] is True
        assert json.loads(Path(result["path"]).read_text())["accepted_at_utc"] == accepted
    turns = store.load_context_projection("s")["turns"]
    assert [turn["turn_id"] for turn in turns] == ["older", "newer"]
