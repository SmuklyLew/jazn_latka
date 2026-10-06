import main

def test_direct_message_uses_shared_runner_before_any_debug_engine_construction(monkeypatch, tmp_path):
    calls = []
    def forbidden(*args, **kwargs):
        raise AssertionError("normal direct conversation constructed a debug engine")
    monkeypatch.setattr(main, "RuntimeCompositionRoot", forbidden)
    monkeypatch.setattr(main, "_ensure_daemon_or_error", lambda *args: ({"ok": True}, None))
    def shared(**kwargs):
        calls.append(kwargs)
        return 0
    monkeypatch.setattr(main, "_run_chat_command_one_shot", shared)
    assert main.legacy_main(["--root", str(tmp_path), "--session-id", "owned", "Hello"]) == 0
    assert len(calls) == 1
    assert calls[0]["text"] == "Hello"
    assert calls[0]["session_id"] == "owned"
    assert calls[0]["command"] == "direct_message"
    assert calls[0]["source_client"] == "cli_direct_conversation"
