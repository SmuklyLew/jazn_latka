"""XAMPP-inspired presentation cannot infer readiness from process IDs."""
from tools.jazn_run_studio.service_visual_state import visual_state

def test_unknown_does_not_look_running():
    assert visual_state("runtime", {"pid": 12, "endpoint_reachable": True}) == "unknown"
    assert visual_state("cloudflare", {"url": "https://example.test"}) == "unknown"

def test_runtime_identity_and_heartbeat_required():
    e = dict(active_state="active_trusted", endpoint_reachable=True,
             process_identity_confirmed=True, endpoint_identity_matches=True,
             heartbeat_fresh=True, conversation_ready=True)
    assert visual_state("runtime", e) == "ready"
    assert visual_state("runtime", {**e, "heartbeat_fresh": False}) == "unknown"
    assert visual_state("runtime", {**e, "root_matches": False}) == "error"
    assert visual_state("runtime", {"active_state": "stopped"}) == "stopped"

def test_optional_ollama_endpoint_only():
    assert visual_state("ollama", {"endpoint_reachable": True}) == "reachable"
    assert visual_state("ollama", {"ready": False}) == "error"
    assert visual_state("gateway", {"ready": True}) == "ready"
