from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse

from .final_export import export_final_memory
from .test_profiles import PROFILE_NAMES, run_test_profile
from .settings import MemoryRebuildSettings
from .typed_api import MemoryLayer, RecallQuery, TypedMemoryAPI
from .unified_memory import UnifiedMemoryDatabase

UNIFIED_COMMANDS = {
    "unified-init",
    "unified-import",
    "unified-migrate",
    "unified-validate",
    "unified-backup",
    "generate-candidates",
    "list-candidates",
    "show-candidate",
    "edit-candidate",
    "review-candidate",
    "add-candidate-evidence",
    "merge-candidates",
    "split-candidate",
    "test-profile",
    "final-export",
    "recall",
}


def _add_database(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", required=True, type=Path, help="Zunifikowany plik memory_jazn.sqlite3.")


def add_unified_subcommands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    init = sub.add_parser("unified-init", help="Utwórz jedną kanoniczną bazę memory_jazn.sqlite3.")
    _add_database(init)

    import_cmd = sub.add_parser("unified-import", help="Importuj rozmowy, HTML, nowe wątki, dzienniki lub SQLite do jednej bazy.")
    _add_database(import_cmd)
    import_cmd.add_argument("sources", nargs="+", type=Path)
    import_cmd.add_argument("--dry-run", action="store_true")
    import_cmd.add_argument("--quick-validation", action="store_true")

    migrate = sub.add_parser("unified-migrate", help="Połącz stare bazy Testów 01–04 z jedną bazą.")
    _add_database(migrate)
    migrate.add_argument("--legacy-root", required=True, type=Path)
    migrate.add_argument("--dry-run", action="store_true")

    validate = sub.add_parser("unified-validate", help="Sprawdź integralność i liczniki jednej bazy.")
    _add_database(validate)
    validate.add_argument("--quick", action="store_true")

    backup = sub.add_parser("unified-backup", help="Utwórz spójny backup przez SQLite Backup API.")
    _add_database(backup)
    backup.add_argument("--output", required=True, type=Path)

    generate = sub.add_parser("generate-candidates", help="Wygeneruj kandydatów bez automatycznej akceptacji.")
    _add_database(generate)
    generate.add_argument("--no-chats", action="store_true")
    generate.add_argument("--no-journal", action="store_true")
    generate.add_argument("--limit", type=int)

    candidates = sub.add_parser("list-candidates", help="Pokaż kandydatów pamięci.")
    _add_database(candidates)
    candidates.add_argument("--status", default="pending_review")
    candidates.add_argument("--limit", type=int, default=200)
    candidates.add_argument("--query")

    show = sub.add_parser("show-candidate", help="Pokaż kandydata, rewizje, dowody i powiązania.")
    _add_database(show)
    show.add_argument("candidate_id")

    edit = sub.add_parser("edit-candidate", help="Edytuj kandydata z niezmienną rewizją poprzedniego stanu.")
    _add_database(edit)
    edit.add_argument("candidate_id")
    edit.add_argument("--title")
    edit.add_argument("--summary")
    edit.add_argument("--truth-status")
    edit.add_argument("--confidence", type=float)
    edit.add_argument("--importance", type=float)
    edit.add_argument("--domains", nargs="*")
    edit.add_argument("--status")
    edit.add_argument("--edited-by", required=True)
    edit.add_argument("--reason", required=True)

    review = sub.add_parser("review-candidate", help="Zatwierdź, odrzuć albo przywróć kandydata do przeglądu.")
    _add_database(review)
    review.add_argument("candidate_id")
    review.add_argument("--decision", required=True, choices=("approve", "reject", "pending"))
    review.add_argument("--reviewed-by", required=True)
    review.add_argument("--reason", required=True)

    evidence = sub.add_parser("add-candidate-evidence", help="Dodaj fragment i kontekst źródłowy.")
    _add_database(evidence)
    evidence.add_argument("candidate_id")
    evidence.add_argument("--source-database", required=True)
    evidence.add_argument("--source-type", required=True)
    evidence.add_argument("--source-record-id", required=True)
    evidence.add_argument("--source-sha256")
    evidence.add_argument("--excerpt", default="")
    evidence.add_argument("--context-before", default="")
    evidence.add_argument("--context-after", default="")

    merge = sub.add_parser("merge-candidates", help="Połącz kandydatów w nowy rekord.")
    _add_database(merge)
    merge.add_argument("candidate_ids", nargs="+")
    merge.add_argument("--title", required=True)
    merge.add_argument("--summary", required=True)
    merge.add_argument("--edited-by", required=True)
    merge.add_argument("--reason", required=True)

    split = sub.add_parser("split-candidate", help="Utwórz osobnego kandydata z części treści.")
    _add_database(split)
    split.add_argument("candidate_id")
    split.add_argument("--title", required=True)
    split.add_argument("--summary", required=True)
    split.add_argument("--edited-by", required=True)
    split.add_argument("--reason", required=True)

    profile = sub.add_parser("test-profile", help="Uruchom profil Testu 01, 02, 03, 04 albo finalny.")
    _add_database(profile)
    profile.add_argument("--profile", required=True, choices=PROFILE_NAMES)
    profile.add_argument("--baseline", action="append", type=Path, default=[])
    profile.add_argument("--quick", action="store_true")
    profile.add_argument("--acceptance-report", type=Path)
    profile.add_argument("--system-acceptance", action="store_true")

    final = sub.add_parser("final-export", help="Zbuduj stagingowy, zweryfikowany eksport finalny.")
    _add_database(final)
    final.add_argument("--output", required=True, type=Path)
    final.add_argument("--baseline", action="append", type=Path, default=[])
    final.add_argument("--source", action="append", type=Path, default=[])
    final.add_argument("--overwrite", action="store_true")
    final.add_argument("--acceptance-report", type=Path, required=True)
    final.add_argument("--system-acceptance", action="store_true")

    recall = sub.add_parser("recall", help="Typowane, temporalne wyszukiwanie z proweniencją; bez dowolnego SQL.")
    _add_database(recall)
    recall.add_argument("query")
    recall.add_argument("--from", dest="temporal_start")
    recall.add_argument("--to", dest="temporal_end")
    recall.add_argument(
        "--limit",
        type=int,
        help="Maksymalna liczba trafień; domyślnie retrieval_limit z ustawień.",
    )
    recall.add_argument("--include-active", action="store_true", help="Jawnie dołącz pamięć aktywną do domyślnego L0.")
    recall.add_argument("--allow-missing-provenance", action="store_true")


def run_unified_command(
    args: argparse.Namespace,
    *,
    settings: MemoryRebuildSettings | None = None,
) -> dict[str, Any]:
    command = args.command
    resolved_settings = settings or MemoryRebuildSettings()
    store = UnifiedMemoryDatabase(args.database, settings=resolved_settings)
    if command == "unified-init":
        return store.initialize()
    if command == "unified-import":
        return store.import_sources(args.sources, dry_run=args.dry_run, full_validation=not args.quick_validation)
    if command == "unified-migrate":
        return store.migrate_legacy_root(args.legacy_root, dry_run=args.dry_run)
    if command == "unified-validate":
        return store.validate(full=not args.quick)
    if command == "unified-backup":
        output = store.backup(args.output)
        return {"ok": True, "output": str(output), "validation": UnifiedMemoryDatabase(output).validate(full=True)}
    if command == "generate-candidates":
        return store.generate_candidates(chats=not args.no_chats, journal=not args.no_journal, limit=args.limit)
    if command == "list-candidates":
        return {"ok": True, "candidates": store.list_candidates(status=args.status, limit=args.limit, query=args.query)}
    if command == "show-candidate":
        return {"ok": True, "candidate": store.get_candidate(args.candidate_id)}
    if command == "edit-candidate":
        changes = {
            key: value
            for key, value in {
                "title": args.title,
                "summary": args.summary,
                "truth_status": args.truth_status,
                "confidence": args.confidence,
                "importance": args.importance,
                "domains_json": args.domains,
                "status": args.status,
            }.items()
            if value is not None
        }
        return {"ok": True, "candidate": store.edit_candidate(args.candidate_id, changes, edited_by=args.edited_by, reason=args.reason)}
    if command == "review-candidate":
        return {"ok": True, "review": store.review_candidate(args.candidate_id, decision=args.decision, reviewed_by=args.reviewed_by, reason=args.reason)}
    if command == "add-candidate-evidence":
        return {"ok": True, "candidate": store.add_candidate_evidence(
            args.candidate_id,
            source_database=args.source_database,
            source_type=args.source_type,
            source_record_id=args.source_record_id,
            source_sha256=args.source_sha256,
            excerpt=args.excerpt,
            context_before=args.context_before,
            context_after=args.context_after,
        )}
    if command == "merge-candidates":
        return {"ok": True, "candidate": store.merge_candidates(args.candidate_ids, title=args.title, summary=args.summary, edited_by=args.edited_by, reason=args.reason)}
    if command == "split-candidate":
        return {"ok": True, "candidate": store.split_candidate(args.candidate_id, title=args.title, summary=args.summary, edited_by=args.edited_by, reason=args.reason)}
    if command == "test-profile":
        return run_test_profile(
            store.path, args.profile, baselines=args.baseline, full_validation=not args.quick,
            acceptance_report=args.acceptance_report, system_acceptance=args.system_acceptance,
        )
    if command == "final-export":
        return export_final_memory(
            store.path, args.output, baselines=args.baseline, sources=args.source,
            overwrite=args.overwrite, acceptance_report=args.acceptance_report,
            system_acceptance=args.system_acceptance,
        )
    if command == "recall":
        layers = (MemoryLayer.L0, MemoryLayer.ACTIVE) if args.include_active else (MemoryLayer.L0,)
        response = TypedMemoryAPI(store.path, settings=resolved_settings).recall(RecallQuery(
            text=args.query,
            layers=layers,
            temporal_start=args.temporal_start,
            temporal_end=args.temporal_end,
            limit=args.limit if args.limit is not None else resolved_settings.retrieval_limit,
            require_provenance=(
                resolved_settings.require_provenance and not args.allow_missing_provenance
            ),
        ))
        return {"ok": True, **response.to_dict()}
    raise AssertionError(command)


__all__ = ["UNIFIED_COMMANDS", "add_unified_subcommands", "run_unified_command"]
