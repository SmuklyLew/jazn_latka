from __future__ import annotations

from pathlib import Path
import json
import shutil
import stat
import zipfile

import pytest

from latka_jazn.tools.memory_restore import (
    DEVELOPER_CONFIRMATION,
    MemoryRestoreOrchestrator,
)
from latka_jazn.tools.memory_sqlite_test04 import (
    EXPECTED_BRANCH,
    MULTI_TURN_SCHEMA,
    PROTOCOL_SCHEMA,
    REQUIRED_REPORTS,
    SOURCE_MANIFEST_SCHEMA,
    ProtocolRequest,
    Test04Error,
    Test04Protocol,
    acceptance_complete,
    assert_sources_unchanged,
    build_plan,
    compare_logical_snapshots,
    evaluate_html_import_dry_run,
    evaluate_multi_turn_review,
    evaluate_recall_cases,
    full_validate_database_set,
    html_review_rows,
    inspect_zip_safety,
    inventory_sources,
    l3_status,
    load_recall_cases,
    load_source_manifest,
    logical_database_snapshot,
    repository_preflight,
    restore_settings,
    sanitized_inventory,
    validate_request,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "Invoke-JaznMemorySqliteTest04.ps1"
DOC = ROOT / "docs" / "tools" / "MEMORY_SQLITE_TEST_04.md"


def _message(message_id: str, role: str, text: str, timestamp: float) -> dict:
    return {
        "id": message_id,
        "author": {"role": role},
        "create_time": timestamp,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": {},
    }


def _conversation(conversation_id: str, *, extended: bool = False) -> dict:
    mapping = {
        "root": {
            "id": "root",
            "parent": None,
            "children": ["user"],
            "message": None,
        },
        "user": {
            "id": "user",
            "parent": "root",
            "children": ["assistant"] if extended else [],
            "message": _message(
                f"{conversation_id}-user",
                "user",
                "Prywatny-sekret-fixture nad jeziorem.",
                101.0,
            ),
        },
    }
    current = "user"
    if extended:
        mapping["assistant"] = {
            "id": "assistant",
            "parent": "user",
            "children": [],
            "message": _message(
                f"{conversation_id}-assistant",
                "assistant",
                "Dalsza część tej samej rozmowy.",
                102.0,
            ),
        }
        current = "assistant"
    return {
        "id": conversation_id,
        "title": f"Tajny tytuł {conversation_id}",
        "create_time": 100.0,
        "update_time": 103.0 if extended else 101.0,
        "current_node": current,
        "mapping": mapping,
    }


def _write_zip(path: Path, members: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            if isinstance(value, str) and name.endswith(".html"):
                archive.writestr(name, value)
            else:
                archive.writestr(
                    name,
                    json.dumps(value, ensure_ascii=False),
                )


def _write_html(path: Path, conversation: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([conversation], ensure_ascii=False)
    path.write_text(
        f"<html><body><script>var jsonData = {payload};</script></body></html>",
        encoding="utf-8",
    )
    return path


def _write_manifest(
    path: Path,
    sources: list[dict],
    *,
    baseline: Path | None = None,
    legacy: Path | None = None,
    attest: bool = True,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SOURCE_MANIFEST_SCHEMA,
        "operator_attestation": {
            "all_known_chatgpt_exports_included": attest,
            "latest_export_created_immediately_before_test": attest,
            "source_order_reviewed": attest,
        },
        "baseline_test03_root": str(baseline) if baseline else "",
        "legacy_memory_root": str(legacy) if legacy else "",
        "baseline_decline_justifications": {},
        "sources": sources,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _source(
    ordinal: int,
    path: Path,
    *,
    role: str = "chatgpt_export",
    latest: bool = False,
    pipeline: str = "memory_rebuild",
) -> dict:
    return {
        "ordinal": ordinal,
        "role": role,
        "path": str(path),
        "exported_at": f"2026-07-{ordinal:02d}",
        "latest_export": latest,
        "pipeline": pipeline,
        "approved": True,
    }


def _small_manifest(tmp_path: Path) -> tuple[Path, Path, Path]:
    first = tmp_path / "private" / "old-large-name.zip"
    second = tmp_path / "private" / "latest-small-name.zip"
    _write_zip(first, {"conversations.json": [_conversation("same")]})
    _write_zip(
        second,
        {
            "conversations.json": [_conversation("same", extended=True)],
            "chat.html": "<html></html>",
        },
    )
    manifest = _write_manifest(
        tmp_path / "private" / "source-manifest.private.json",
        [
            _source(1, first),
            _source(2, second, latest=True),
        ],
    )
    return manifest, first, second


def _run_restore(target: Path, sources: list[Path], manifest: Path) -> dict:
    settings = restore_settings(manifest, target)
    settings.create_backup = False
    settings.audit_classifiers = False
    settings.reclassify_journal_dry_run = False
    orchestrator = MemoryRestoreOrchestrator(
        settings,
        tool_root=target.parent / "repo",
    )
    plan = orchestrator.plan(sources)
    return orchestrator.run(
        sources,
        confirmation=DEVELOPER_CONFIRMATION,
        prepared_plan=plan,
    )


def test_powershell_operator_has_fail_closed_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert "[CmdletBinding(PositionalBinding = $false)]" in text
    assert "Set-StrictMode -Version Latest" in text
    assert '$ErrorActionPreference = "Stop"' in text
    for parameter in (
        "$Root",
        "$SourceManifest",
        "$TargetRoot",
        "$BaselineTest03Root",
        "$LegacyMemoryRoot",
        "$RecallCases",
        "$PlanOnly",
        "$RunRebuild",
        "$RunIdempotence",
        "$RunFreshRebuildComparison",
        "$RunRecall",
        "$RunHtmlDryRun",
        "$HtmlLimitConversations",
        "$RestartDaemon",
        "$RestartTimeoutSeconds",
        "$Resume",
        "$AllowDirty",
    ):
        assert parameter in text
    assert EXPECTED_BRANCH in text
    assert "latka_jazn.tools.memory_sqlite_test04" in text
    assert "approve-l3-manifest-sha" not in text.casefold()
    assert "force-push" not in text.casefold()


def test_final_acceptance_requires_every_mandatory_phase() -> None:
    final = {
        "structural_integrity": "passed",
        "source_completeness": "passed",
        "same_target_idempotence": "passed",
        "fresh_rebuild_reproducibility": "passed",
        "test03_reconciliation": "passed",
        "recall": "not_run",
        "multi_turn_review": "passed",
        "restart_continuity": "not_run",
        "l2_review": "not_created",
        "l3_decision": "not_created",
        "system_activation_ready": False,
    }
    assert acceptance_complete(final) is False
    final["recall"] = "passed"
    assert acceptance_complete(final) is True


def test_wrong_branch_is_rejected_before_workspace_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    manifest, _, _ = _small_manifest(tmp_path)
    target = tmp_path / "target"

    def fake_git(_root: Path, *arguments: str, **_kwargs) -> str:
        if arguments == ("branch", "--show-current"):
            return "wrong-branch\n"
        raise AssertionError(arguments)

    monkeypatch.setattr(
        "latka_jazn.tools.memory_sqlite_test04._git",
        fake_git,
    )
    protocol = Test04Protocol(
        ProtocolRequest(
            root=repo,
            source_manifest=manifest,
            target_root=target,
            plan_only=True,
        ),
        skip_runtime_preflight=True,
    )
    with pytest.raises(Test04Error, match="wrong branch"):
        protocol.execute()
    assert not (repo / "workspace_runtime").exists()
    assert not target.exists()


def test_explicit_baselines_cannot_conflict_with_private_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private" / "latest.zip"
    _write_zip(source, {"conversations.json": [_conversation("one")]})
    manifest_baseline = tmp_path / "baseline-from-manifest"
    manifest_legacy = tmp_path / "legacy-from-manifest"
    manifest = _write_manifest(
        tmp_path / "private" / "manifest.json",
        [_source(1, source, latest=True)],
        baseline=manifest_baseline,
        legacy=manifest_legacy,
    )
    request = ProtocolRequest(
        root=ROOT,
        source_manifest=manifest,
        target_root=tmp_path / "target",
        baseline_test03_root=tmp_path / "different-baseline",
        legacy_memory_root=manifest_legacy,
        plan_only=True,
    )
    with pytest.raises(Test04Error, match="conflicts with source manifest"):
        Test04Protocol(request, skip_runtime_preflight=True)


def test_plan_only_is_cumulative_exact_and_does_not_create_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    manifest, first, second = _small_manifest(tmp_path)
    target = tmp_path / "target"
    monkeypatch.setattr(
        "latka_jazn.tools.memory_sqlite_test04.repository_preflight",
        lambda *_args, **_kwargs: {
            "branch": EXPECTED_BRANCH,
            "head": "a" * 40,
            "status_short": [],
            "tracked_status_short": [],
            "allow_dirty": False,
            "restore_point": {
                "kind": "immutable_git_commit",
                "commit": "a" * 40,
                "worktree_clean": True,
            },
        },
    )
    protocol = Test04Protocol(
        ProtocolRequest(
            root=repo,
            source_manifest=manifest,
            target_root=target,
            plan_only=True,
        ),
        skip_runtime_preflight=True,
    )

    code, summary = protocol.execute()

    assert code == 0, summary
    assert not target.exists()
    run_dirs = list(
        (repo / "workspace_runtime" / "memory_sqlite_test_04").iterdir()
    )
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    assert [Path(item["path"]) for item in plan["chats"]] == [
        first.resolve(),
        second.resolve(),
    ]
    assert plan["chats"][0]["plan"]["conversation_counters"] == {"new": 1}
    assert plan["chats"][1]["plan"]["conversation_counters"] == {
        "extends_active": 1
    }
    readable = (run_dir / "plan.txt").read_text(encoding="utf-8")
    assert "conversation_counters" in readable
    assert "extends_active" in readable
    assert set(REQUIRED_REPORTS).issubset(
        {path.name for path in run_dir.iterdir()}
    )
    assert summary["final"]["system_activation_ready"] is False


def test_manifest_order_never_uses_file_size_and_same_sha_is_deduplicated(
    tmp_path: Path,
) -> None:
    small = tmp_path / "small-first.zip"
    large = tmp_path / "large-second.zip"
    duplicate = tmp_path / "renamed-duplicate.zip"
    _write_zip(small, {"conversations.json": [_conversation("small")]})
    _write_zip(
        large,
        {"conversations.json": [_conversation(f"large-{index}") for index in range(8)]},
    )
    shutil.copyfile(small, duplicate)
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        [
            _source(1, small),
            _source(2, large, latest=True),
            _source(3, duplicate, role="approved_l0"),
        ],
    )
    manifest = load_source_manifest(manifest_path)
    reports, execution_paths, completeness = inventory_sources(manifest)

    assert completeness == "passed"
    assert execution_paths == [small.resolve(), large.resolve()]
    assert reports[0]["size_bytes"] < reports[1]["size_bytes"]
    assert reports[2]["duplicate_of_ordinal"] == 1
    assert reports[2]["include_in_execution"] is False


def test_shared_metadata_numbered_members_and_html_contract(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared-only.zip"
    _write_zip(
        shared,
        {
            "shared_conversations.json": [
                {
                    "id": "share",
                    "conversation_id": "conversation",
                    "title": "Shared",
                    "is_anonymous": True,
                }
            ]
        },
    )
    shared_manifest = _write_manifest(
        tmp_path / "shared-manifest.json",
        [_source(1, shared, latest=True)],
    )
    reports, execution, completeness = inventory_sources(
        load_source_manifest(shared_manifest)
    )
    assert completeness == "failed"
    assert execution == []
    assert "canonical_conversation_json_missing" in reports[0]["errors"]

    numbered = tmp_path / "numbered.zip"
    _write_zip(
        numbered,
        {
            "conversations-002.json": [_conversation("second")],
            "chat.html": "<html></html>",
            "conversations-001.json": [_conversation("first")],
        },
    )
    manifest = _write_manifest(
        tmp_path / "numbered-manifest.json",
        [_source(1, numbered, latest=True)],
    )
    loaded = load_source_manifest(manifest)
    reports, execution, completeness = inventory_sources(loaded)
    assert completeness == "passed"
    assert reports[0]["canonical_conversation_members"] == [
        "conversations-001.json",
        "conversations-002.json",
    ]
    _, plan, _ = build_plan(
        root=tmp_path / "repo",
        manifest_path=manifest,
        target_root=tmp_path / "target",
        sources=execution,
    )
    assert plan["chats"][0]["plan"]["conversation_counters"] == {"new": 2}
    assert plan["chats"][0]["chat_html_available"] is True


def test_zip_traversal_symlink_duplicates_case_collisions_and_corruption_block(
    tmp_path: Path,
) -> None:
    traversal = tmp_path / "traversal.zip"
    _write_zip(
        traversal,
        {
            "../conversations.json": [_conversation("escape")],
        },
    )
    assert inspect_zip_safety(traversal)["path_traversal_ok"] is False

    symlink = tmp_path / "symlink.zip"
    with zipfile.ZipFile(symlink, "w") as archive:
        link = zipfile.ZipInfo("conversations.json")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "target.json")
    assert inspect_zip_safety(symlink)["symlink_check_ok"] is False

    duplicates = tmp_path / "duplicates.zip"
    with zipfile.ZipFile(duplicates, "w") as archive:
        archive.writestr("conversations.json", "[]")
        with pytest.warns(UserWarning):
            archive.writestr("conversations.json", "[]")
    assert inspect_zip_safety(duplicates)["duplicate_member_check_ok"] is False

    collision = tmp_path / "collision.zip"
    with zipfile.ZipFile(collision, "w") as archive:
        archive.writestr("conversations.json", "[]")
        archive.writestr("CONVERSATIONS.JSON", "[]")
    assert inspect_zip_safety(collision)["case_collision_check_ok"] is False

    corrupt = tmp_path / "corrupt.zip"
    corrupt.write_bytes(b"not-a-complete-zip")
    safety = inspect_zip_safety(corrupt)
    assert safety["ok"] is False
    assert any("zip_open_or_crc_failed" in item for item in safety["errors"])


def test_html_only_source_uses_existing_dry_run_without_target_write(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "private" / "canonical.zip"
    html = _write_html(
        tmp_path / "private" / "BARDZO-PRYWATNY-eksport.html",
        _conversation("html-source", extended=True),
    )
    _write_zip(canonical, {"conversations.json": [_conversation("canonical")]})
    manifest_path = _write_manifest(
        tmp_path / "private" / "source-manifest.private.json",
        [
            _source(1, canonical, latest=True),
            _source(
                2,
                html,
                role="chatgpt_export",
                pipeline="html_only_review",
            ),
        ],
    )

    inventory, execution, completeness = inventory_sources(
        load_source_manifest(manifest_path)
    )
    assert completeness == "passed"
    assert execution == [canonical.resolve()]
    assert [row["ordinal"] for row in html_review_rows(inventory)] == [2]

    repo = tmp_path / "repo"
    repo.mkdir()
    report = evaluate_html_import_dry_run(repo, inventory)

    assert report["ok"] is True
    assert report["status"] == "passed"
    assert report["source_count"] == 1
    assert report["sources"][0]["conversations_seen"] == 1
    assert report["sources"][0]["messages_seen"] == 2
    assert report["target_database_modified"] is False
    assert report["automatic_l2"] is False
    assert report["automatic_l3"] is False
    rendered = json.dumps(report, ensure_ascii=False)
    assert str(html.parent) not in rendered
    assert html.name not in rendered
    assert "Prywatny-sekret-fixture" not in rendered
    assert not (repo / "memory").exists()


def test_html_only_source_rejects_non_html_file(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.zip"
    fake_html = tmp_path / "not-html.zip"
    _write_zip(canonical, {"conversations.json": [_conversation("canonical")]})
    _write_zip(fake_html, {"conversations.json": [_conversation("other")]})
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        [
            _source(1, canonical, latest=True),
            _source(
                2,
                fake_html,
                role="chatgpt_export",
                pipeline="html_only_review",
            ),
        ],
    )

    inventory, _, completeness = inventory_sources(
        load_source_manifest(manifest_path)
    )
    assert completeness == "failed"
    assert "html_only_pipeline_requires_html_file" in inventory[1]["errors"]


def test_acceptance_requires_html_dry_run_when_html_is_declared() -> None:
    final = {
        "structural_integrity": "passed",
        "source_completeness": "passed",
        "same_target_idempotence": "passed",
        "fresh_rebuild_reproducibility": "passed",
        "test03_reconciliation": "passed",
        "recall": "passed",
        "html_import_dry_run": "not_run",
        "multi_turn_review": "passed",
    }
    assert acceptance_complete(final) is False
    final["html_import_dry_run"] = "passed"
    assert acceptance_complete(final) is True
    final["html_import_dry_run"] = "not_applicable"
    assert acceptance_complete(final) is True


def test_protocol_requires_and_runs_html_dry_run_before_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = tmp_path / "private" / "canonical.zip"
    html = _write_html(
        tmp_path / "private" / "legacy.html",
        _conversation("html-protocol", extended=True),
    )
    _write_zip(canonical, {"conversations.json": [_conversation("canonical")]})
    manifest_path = _write_manifest(
        tmp_path / "private" / "manifest.json",
        [
            _source(1, canonical, latest=True),
            _source(
                2,
                html,
                role="chatgpt_export",
                pipeline="html_only_review",
            ),
        ],
    )

    monkeypatch.setattr(
        "latka_jazn.tools.memory_sqlite_test04.repository_preflight",
        lambda *_args, **_kwargs: {
            "branch": EXPECTED_BRANCH,
            "head": "b" * 40,
            "status_short": [],
            "tracked_status_short": [],
            "allow_dirty": False,
            "restore_point": {
                "kind": "immutable_git_commit",
                "commit": "b" * 40,
                "worktree_clean": True,
            },
        },
    )

    blocked_repo = tmp_path / "repo-blocked"
    blocked_repo.mkdir()
    blocked = Test04Protocol(
        ProtocolRequest(
            root=blocked_repo,
            source_manifest=manifest_path,
            target_root=tmp_path / "target-blocked",
            plan_only=True,
        ),
        skip_runtime_preflight=True,
    )
    blocked_code, blocked_summary = blocked.execute()
    assert blocked_code == 2
    assert blocked_summary["final"]["html_import_dry_run"] == "not_run"
    assert blocked_summary["error_types"] == ["Test04Error"]

    ready_repo = tmp_path / "repo-ready"
    ready_repo.mkdir()
    ready = Test04Protocol(
        ProtocolRequest(
            root=ready_repo,
            source_manifest=manifest_path,
            target_root=tmp_path / "target-ready",
            plan_only=True,
            run_html_dry_run=True,
            html_limit_conversations=10,
        ),
        skip_runtime_preflight=True,
    )
    ready_code, ready_summary = ready.execute()
    assert ready_code == 0
    assert ready_summary["final"]["html_import_dry_run"] == "passed"
    assert ready_summary["final"]["source_completeness"] == "passed"
    assert not (ready_repo / "memory").exists()


def test_source_change_after_plan_blocks_execution(tmp_path: Path) -> None:
    manifest_path, first, _ = _small_manifest(tmp_path)
    manifest = load_source_manifest(manifest_path)
    inventory, execution, completeness = inventory_sources(manifest)
    assert completeness == "passed"
    build_plan(
        root=tmp_path / "repo",
        manifest_path=manifest_path,
        target_root=tmp_path / "target",
        sources=execution,
    )
    _write_zip(first, {"conversations.json": [_conversation("changed")]})
    with pytest.raises(Test04Error, match="source changed after plan"):
        assert_sources_unchanged(inventory)


def test_first_import_error_stops_following_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, first, second = _small_manifest(tmp_path)
    target = tmp_path / "target"
    orchestrator = MemoryRestoreOrchestrator(
        restore_settings(manifest_path, target),
        tool_root=tmp_path / "repo",
    )
    plan = orchestrator.plan([first, second])
    calls: list[Path] = []

    def fail_first(source: Path) -> dict:
        calls.append(source)
        raise RuntimeError("synthetic first-source failure")

    monkeypatch.setattr(orchestrator, "_import_chat_source", fail_first)
    result = orchestrator.run(
        [first, second],
        confirmation=DEVELOPER_CONFIRMATION,
        prepared_plan=plan,
    )

    assert result["ok"] is False
    assert calls == [first.resolve()]
    assert any(
        "synthetic first-source failure" in item["error"]
        for item in result["errors"]
    )


def test_same_target_idempotence_and_two_fresh_rebuild_fingerprints(
    tmp_path: Path,
) -> None:
    manifest_path, first, second = _small_manifest(tmp_path)
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    assert _run_restore(target_a, [first, second], manifest_path)["ok"]
    first_snapshot = logical_database_snapshot(target_a)
    assert _run_restore(target_a, [first, second], manifest_path)["ok"]
    second_snapshot = logical_database_snapshot(target_a)
    idempotence = compare_logical_snapshots(
        first_snapshot,
        second_snapshot,
        allow_operation_count_delta=True,
    )
    assert idempotence["ok"], idempotence

    assert _run_restore(target_b, [first, second], manifest_path)["ok"]
    fresh_snapshot = logical_database_snapshot(target_b)
    reproducibility = compare_logical_snapshots(
        first_snapshot,
        fresh_snapshot,
        allow_operation_count_delta=False,
    )
    assert reproducibility["ok"], reproducibility


def test_full_validation_and_l2_l3_stay_unpromoted(tmp_path: Path) -> None:
    manifest_path, first, second = _small_manifest(tmp_path)
    target = tmp_path / "target"
    assert _run_restore(target, [first, second], manifest_path)["ok"]

    validation = full_validate_database_set(target)
    status = l3_status(target)

    assert validation["ok"], validation
    assert all(
        item["integrity_result"] == ["ok"]
        for item in validation["databases"].values()
    )
    assert all(
        item["foreign_key_error_count"] == 0
        for item in validation["databases"].values()
    )
    assert status["ok"] is True
    assert status["l2_record_count"] == 0
    assert status["l3_record_count"] == 0
    assert status["manifest_approved"] is False
    assert status["promotion_executed"] is False
    assert status["approve_l3_manifest_sha_invoked"] is False


def test_sanitized_reports_contain_no_private_paths_names_queries_or_terms(
    tmp_path: Path,
) -> None:
    secret_dir = tmp_path / "BARDZO-PRYWATNY-KATALOG"
    secret_export_name = "sekretny-eksport-Krzysztofa.zip"
    source = secret_dir / secret_export_name
    _write_zip(source, {"conversations.json": [_conversation("secret")]})
    manifest_path = _write_manifest(
        secret_dir / "manifest.private.json",
        [_source(1, source, latest=True)],
    )
    reports, _, completeness = inventory_sources(
        load_source_manifest(manifest_path)
    )
    sanitized = sanitized_inventory(reports, completeness)
    rendered_inventory = json.dumps(sanitized, ensure_ascii=False)
    assert str(secret_dir) not in rendered_inventory
    assert secret_export_name not in rendered_inventory
    assert "Tajny tytuł" not in rendered_inventory

    target = tmp_path / "target"
    assert _run_restore(target, [source], manifest_path)["ok"]
    private_query = "Prywatny-sekret-fixture"
    expected_term = "jeziorze"
    forbidden_term = "tajne-fałszywe-dopasowanie"
    recall = evaluate_recall_cases(
        target,
        {
            "schema_version": "jazn_private_recall_cases/v1",
            "recall_cases": [
                {
                    "id": "secret-case",
                    "query": private_query,
                    "expected_any": [expected_term],
                    "expected_all": [],
                    "forbidden_any": [forbidden_term],
                    "expected_sources": ["archive_chats"],
                    "minimum_hits": 1,
                    "limit": 20,
                }
            ],
        },
    )
    rendered_recall = json.dumps(recall, ensure_ascii=False)
    assert private_query not in rendered_recall
    assert expected_term not in rendered_recall
    assert forbidden_term not in rendered_recall
    assert "Prywatny-sekret-fixture nad jeziorem" not in rendered_recall


def test_recall_requires_real_case_and_restart_requires_explicit_execution(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "empty-recall.json"
    empty.write_text(
        json.dumps(
            {
                "schema_version": "jazn_private_recall_cases/v1",
                "recall_cases": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(Test04Error, match="at least one real recall case"):
        load_recall_cases(empty)

    manifest, _, _ = _small_manifest(tmp_path)
    with pytest.raises(Test04Error, match="restart-daemon requires"):
        validate_request(
            ProtocolRequest(
                root=tmp_path,
                source_manifest=manifest,
                target_root=tmp_path.parent / "outside-target",
                plan_only=False,
                run_rebuild=False,
                restart_daemon=True,
            )
        )


def test_multi_turn_naturalness_requires_manual_complete_review(
    tmp_path: Path,
) -> None:
    review = tmp_path / "review.json"
    checks = {
        "earlier_fact_recalled": True,
        "topic_maintained_across_turns": True,
        "memories_not_mixed": True,
        "source_and_provenance_visible": True,
        "book_scene_not_physical_event": True,
        "dream_or_vision_not_fact": True,
        "no_confabulation_after_miss": True,
        "missing_memory_admitted": False,
    }
    review.write_text(
        json.dumps(
            {
                "schema_version": MULTI_TURN_SCHEMA,
                "overall_status": "passed",
                "reviewed_by": "operator",
                "reviewed_at_utc": "2026-07-26T12:00:00Z",
                "checks": checks,
                "private_scenario": {"turns": [], "review_notes": ""},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(Test04Error, match="cannot pass"):
        evaluate_multi_turn_review(review)
    checks["missing_memory_admitted"] = True
    payload = json.loads(review.read_text(encoding="utf-8"))
    payload["checks"] = checks
    review.write_text(json.dumps(payload), encoding="utf-8")
    result = evaluate_multi_turn_review(review)
    assert result["status"] == "passed"
    assert result["passed_check_count"] == 8
    assert result["reviewed_at_utc_normalized"] == "2026-07-26T12:00:00+00:00"
    assert result["private_content_persisted"] is False

    payload["reviewed_by"] = ""
    review.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(Test04Error, match="without reviewed_by"):
        evaluate_multi_turn_review(review)

    payload["reviewed_by"] = "operator"
    payload["reviewed_at_utc"] = "2026-07-26T12:00:00"
    review.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(Test04Error, match="explicit timezone"):
        evaluate_multi_turn_review(review)


def test_first_rebuild_targets_only_external_developer_root(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    manifest_path, first, second = _small_manifest(tmp_path)
    target = tmp_path / "external-target"
    protocol = Test04Protocol(
        ProtocolRequest(
            root=repo,
            source_manifest=manifest_path,
            target_root=target,
            run_rebuild=True,
        ),
        skip_runtime_preflight=True,
    )
    protocol._prepare_run_dir()
    manifest = load_source_manifest(manifest_path)
    inventory, execution, completeness = inventory_sources(manifest)
    assert completeness == "passed"

    report = protocol._first_rebuild(execution, inventory)

    assert report["ok"], report
    assert target.is_dir()
    assert not (repo / "memory").exists()
    assert not (repo / "memory" / "sqlite").exists()
    assert report["automatic_l2"] is False
    assert report["automatic_l3"] is False


def test_documentation_preserves_truth_boundary_and_cleanup_contract() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "nadal samodzielnie nie aktywuje pamięci systemowej" in text
    assert "Issue #59 pozostaje otwarte" in text
    assert "system_activation_ready" in text
    assert "source-manifest.private.json" in text
    assert "RunHtmlDryRun" in text
    assert "developer_test04_passed" in text
    assert "Remove-Item -LiteralPath <DOKŁADNY_CEL> -Recurse" in text
    assert "nie aplikowano" not in text.casefold() or "patcha" in text.casefold()
