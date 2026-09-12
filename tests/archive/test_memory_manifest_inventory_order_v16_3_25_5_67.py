from latka_jazn.tools.memory_rebuild_app.run_manifest import RunManifest


def test_checkpoint_preserves_non_alphabetical_inventory_order(tmp_path):
    identity = dict(run_id="order", tool_version="1", system_version="1", base_commit="a" * 40)
    manifest = RunManifest.begin(**identity).with_sources((
        {"path": "z.json", "role": "journal", "sha256": "b" * 64},
        {"path": "a.json", "role": "conversation", "sha256": "a" * 64},
    ))
    manifest.write_draft(tmp_path)
    restored = RunManifest.load_draft(tmp_path, **identity)
    assert restored.sanitized_dict() == manifest.sanitized_dict()
    assert restored.source_sha256 == manifest.source_sha256
