from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse

from .application import MemoryRebuildApplicationService
from .final_export import export_final_memory
from .test_profiles import PROFILE_NAMES, run_test_profile
from .settings import MemoryRebuildSettings
from .test_spec import TEST_PROTOCOL_ORDER
from .typed_api import MemoryLayer, RecallQuery, TypedMemoryAPI
from .unified_memory import UnifiedMemoryDatabase
from .chat_sources import compare_chat_sources, list_chat_conversations

UNIFIED_COMMANDS = {
    "unified-init",
    "unified-import",
    "unified-migrate",
    "unified-validate",
    "unified-backup",
    "list-conversations",
    "compare-chat-sources",
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
    "protocol-run",
    "protocol-validate",
}


def _add_database(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", required=True, type=Path, help="Zunifikowany plik memory_jazn.sqlite3.")


def add_unified_subcommands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    init = sub.add_parser("unified-init", help="Utwórz jedną kanoniczną bazę memory_jazn.sqlite3.")
    _add_database(init)

    import_cmd = sub.add_parser(
        "unified-import",
        help="Importuj całe źródła albo wybrane rozmowy do jednej bazy.",
    )
    _add_database(import_cmd)
    import_cmd.add_argument("sources", nargs="+", type=Path)
    import_cmd.add_argument("--dry-run", action="store_true")
    import_cmd.add_argument("--quick-validation", action="store_true")
    import_cmd.add_argument(
        "--conversation-id",
        action="append",
        default=[],
        help="Importuj tylko wskazaną rozmowę; opcję można podać wielokrotnie.",
    )
    import_cmd.add_argument("--title", help="Filtr tytułu rozmowy (fragment, bez rozróżniania wielkości liter).")
    import_cmd.add_argument("--from", dest="temporal_start", help="Najwcześniejsza data/epoch rozmowy.")
    import_cmd.add_argument("--to", dest="temporal_end", help="Najpóźniejsza data/epoch rozmowy.")
    import_cmd.add_argument(
        "--html-control",
        type=Path,
        help="Porównaj wybrane rozmowy z chat.html; import jest blokowany przy rozbieżności.",
    )

    catalog = sub.add_parser(
        "list-conversations",
        help="Pokaż katalog rozmów i stabilne conversation_id bez zapisu do bazy.",
    )
    catalog.add_argument("source", type=Path)

    compare = sub.add_parser(
        "compare-chat-sources",
        help="Porównaj semantyczne drzewa rozmów JSON/ZIP z kontrolnym HTML/JSON.",
    )
    compare.add_argument("primary", type=Path)
    compare.add_argument("control", type=Path)
    compare.add_argument("--conversation-id", action="append", default=[])

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

    protocol = sub.add_parser("protocol-run", help="Uruchom proceduralny Test00-04 albo Final przez wspólny ProtocolEngine.")
    protocol.add_argument("--profile", required=True, choices=TEST_PROTOCOL_ORDER)
    protocol.add_argument("--output-root", required=True, type=Path)
    protocol.add_argument("--source", action="append", type=Path, default=[])
    protocol.add_argument("--database", type=Path)
    protocol.add_argument("--test00-result", type=Path)
    protocol.add_argument("--benchmark", type=Path)
    protocol.add_argument("--restart-continuity-report", type=Path)
    protocol.add_argument("--test04-result", type=Path)
    protocol.add_argument("--final-output", type=Path)
    protocol.add_argument("--system-acceptance", action="store_true")
    protocol.add_argument("--base-commit")
    protocol.add_argument("--run-id")

    validate_protocol = sub.add_parser("protocol-validate", help="Waliduj istniejący artefakt bez uruchamiania protokołu.")
    validate_protocol.add_argument("--profile", required=True, choices=TEST_PROTOCOL_ORDER)
    validate_protocol.add_argument("--artifact", required=True, type=Path)
    validate_protocol.add_argument("--output-root", required=True, type=Path)
    validate_protocol.add_argument("--benchmark", type=Path)
    validate_protocol.add_argument("--test04-result", type=Path)
    validate_protocol.add_argument("--restart-continuity-report", type=Path)
    validate_protocol.add_argument("--system-acceptance", action="store_true")
    validate_protocol.add_argument("--base-commit")


def run_unified_command(
    args: argparse.Namespace,
    *,
    settings: MemoryRebuildSettings | None = None,
) -> dict[str, Any]:
    command = args.command
    if command == "list-conversations":
        return list_chat_conversations(args.source)
    if command == "compare-chat-sources":
        return compare_chat_sources(
            args.primary,
            args.control,
            conversation_ids=args.conversation_id,
        )

    resolved_settings = settings or MemoryRebuildSettings()
    if command in {"protocol-run", "protocol-validate"}:
        service = MemoryRebuildApplicationService(
            args.output_root,
            tool_root=Path.cwd(),
            settings=resolved_settings,
            base_commit=args.base_commit,
            run_id=getattr(args, "run_id", None),
        )
        if command == "protocol-validate":
            kwargs: dict[str, Any] = {}
            if args.profile == "test04":
                if args.benchmark is None:
                    raise ValueError("protocol-validate test04 requires --benchmark")
                kwargs = {
                    "benchmark": args.benchmark,
                    "system_acceptance": args.system_acceptance,
                    "restart_continuity_report": args.restart_continuity_report,
                }
            elif args.profile == "final":
                if args.test04_result is None:
                    raise ValueError("protocol-validate final requires --test04-result")
                kwargs = {"test04_result": args.test04_result}
            return service.validate_protocol(args.profile, args.artifact, **kwargs)

        profile = args.profile
        if profile in {"test00", "test01", "test03"} and not args.source:
            raise ValueError(f"protocol-run {profile} requires at least one --source")
        if profile in {"test01", "test02", "test04", "final"} and args.database is None:
            raise ValueError(f"protocol-run {profile} requires --database")
        if profile == "test00":
            run_kwargs = {"sources": args.source}
        elif profile == "test01":
            if args.test00_result is None:
                raise ValueError("protocol-run test01 requires --test00-result")
            run_kwargs = {
                "sources": args.source,
                "database": args.database,
                "test00_result": args.test00_result,
            }
        elif profile == "test02":
            run_kwargs = {"database": args.database}
        elif profile == "test03":
            run_kwargs = {"sources": args.source, "test00_result": args.test00_result}
        elif profile == "test04":
            if args.benchmark is None:
                raise ValueError("protocol-run test04 requires --benchmark")
            run_kwargs = {
                "database": args.database,
                "benchmark": args.benchmark,
                "system_acceptance": args.system_acceptance,
                "restart_continuity_report": args.restart_continuity_report,
            }
        else:
            if args.test04_result is None or args.final_output is None:
                raise ValueError("protocol-run final requires --test04-result and --final-output")
            run_kwargs = {
                "database": args.database,
                "output": args.final_output,
                "test04_result": args.test04_result,
                "sources": args.source,
            }
        return service.run_protocol(profile, **run_kwargs)

    store = UnifiedMemoryDatabase(args.database, settings=resolved_settings)
    if command == "unified-init":
        return store.initialize()
    if command == "unified-import":
        selective = bool(
            args.conversation_id
            or args.title
            or args.temporal_start
            or args.temporal_end
            or args.html_control
        )
        if selective:
            if len(args.sources) != 1:
                raise ValueError("Selektywny import wymaga dokładnie jednego źródła rozmów.")
            importer = getattr(store, "import_source_selected", None)
            if importer is None:
                raise RuntimeError("selective_chat_import_hardening_not_loaded")
            result = importer(
                args.sources[0],
                conversation_ids=args.conversation_id,
                title=args.title,
                temporal_start=args.temporal_start,
                temporal_end=args.temporal_end,
                html_control=args.html_control,
                dry_run=args.dry_run,
            )
            if not args.dry_run and not args.quick_validation:
                result["validation"] = store.validate(full=True)
                result["ok"] = bool(result.get("ok")) and bool(result["validation"].get("ok"))
            return result
        return store.import_sources(
            args.sources,
            dry_run=args.dry_run,
            full_validation=not args.quick_validation,
        )
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
