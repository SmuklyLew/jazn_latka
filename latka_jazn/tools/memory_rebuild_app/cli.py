from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
import argparse
import json

from latka_jazn.tools.memory_restore import confirmation_token

from .baseline_registry import discover_baseline_roots
from .controller import MemoryRebuildAppController
from .models import RebuildProject
from .project_store import ProjectStore
from .source_inventory import inspect_source
from .tui import run_studio

APP_VERSION = "1.0.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rebuild_memory_app",
        description="Kursorowa aplikacja operatorska do projektowania, porównywania i uruchamiania odbudowy pamięci Jaźni.",
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    parser.add_argument("--project-root", type=Path, help="Katalog prywatnych konfiguracji projektów.")
    parser.add_argument("--project", help="ID, nazwa lub ścieżka projektu.")
    parser.add_argument("--text-ui", action="store_true", help="Wymuś interfejs tekstowy.")
    parser.add_argument("--json", action="store_true", help="Wypisz wynik jako JSON.")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("studio", help="Uruchom interfejs kursorowy.")
    sub.add_parser("list-projects", help="Pokaż projekty.")

    create = sub.add_parser("create-project", help="Utwórz projekt.")
    create.add_argument("--name", required=True)
    create.add_argument("--target-root", required=True, type=Path)
    create.add_argument("--source-directory", type=Path)
    create.add_argument("--mode", choices=("developer", "system"), default="developer")

    add_source = sub.add_parser("add-source", help="Dodaj i rozpoznaj źródło.")
    add_source.add_argument("path", type=Path)
    add_source.add_argument("--approved", action="store_true")
    add_source.add_argument("--verify-zip-crc", action="store_true")
    add_source.add_argument("--no-sha256", action="store_true")

    inspect = sub.add_parser("inspect-source", help="Rozpoznaj plik bez zapisu projektu.")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--verify-zip-crc", action="store_true")
    inspect.add_argument("--no-sha256", action="store_true")

    add_baseline = sub.add_parser("add-baseline", help="Dodaj bazę testową do porównań.")
    add_baseline.add_argument("path", type=Path)
    add_baseline.add_argument("--label")
    add_baseline.add_argument("--full-integrity", action="store_true")

    discover = sub.add_parser("discover-baselines", help="Znajdź istniejące zestawy pięciu baz.")
    discover.add_argument("roots", nargs="+", type=Path)
    discover.add_argument("--max-depth", type=int, default=4)

    sub.add_parser("show-project", help="Pokaż pełną konfigurację projektu.")
    sub.add_parser("preflight", help="Sprawdź projekt bez zapisu baz.")
    sub.add_parser("plan", help="Uruchom plan silnika bez zapisu baz.")
    sub.add_parser("compare", help="Porównaj cel z baseline’ami.")

    export = sub.add_parser("export", help="Eksportuj manifest.")
    export.add_argument("--format", choices=("project", "test04"), required=True)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--baseline-test03-root", type=Path)
    export.add_argument("--legacy-memory-root", type=Path)

    run = sub.add_parser("run", help="Uruchom odbudowę po jawnym tokenie.")
    run.add_argument("--confirm", required=True)
    return parser


def _emit(payload: Any, *, json_mode: bool) -> None:
    if json_mode or not isinstance(payload, str):
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(payload)


def _require_project(store: ProjectStore, identifier: str | None) -> RebuildProject:
    if not identifier:
        raise ValueError("Ta operacja wymaga --project <ID|nazwa|plik>.")
    return store.load(identifier)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "studio"
    try:
        if command == "studio":
            return run_studio(
                project_root=args.project_root,
                project=args.project,
                tool_root=Path.cwd(),
                text_ui=args.text_ui,
            )

        store = ProjectStore(args.project_root)
        if command == "list-projects":
            payload = [
                {
                    "project_id": item.project_id,
                    "name": item.name,
                    "target_root": item.target_root,
                    "updated_at_utc": item.updated_at_utc,
                    "revision": item.revision,
                    "path": str(item.path),
                }
                for item in store.list()
            ]
            _emit(payload, json_mode=True)
            return 0

        if command == "create-project":
            project = RebuildProject.create(
                args.name,
                args.target_root,
                source_directory=args.source_directory or "",
                mode=args.mode,
            )
            path = store.create(project)
            _emit({"ok": True, "project": project.to_dict(), "path": str(path)}, json_mode=True)
            return 0

        if command == "inspect-source":
            inspection = inspect_source(
                args.path,
                calculate_sha256=not args.no_sha256,
                verify_zip_crc=args.verify_zip_crc,
            )
            _emit(inspection.to_dict(), json_mode=True)
            return 0 if inspection.ok else 2

        if command == "discover-baselines":
            roots = discover_baseline_roots(args.roots, max_depth=max(0, args.max_depth))
            _emit({"ok": True, "roots": [str(path) for path in roots]}, json_mode=True)
            return 0

        project = _require_project(store, args.project)
        controller = MemoryRebuildAppController(project, store=store, tool_root=Path.cwd())

        if command == "add-source":
            source = controller.inspect_and_add_source(
                args.path,
                approved=args.approved,
                calculate_sha256=not args.no_sha256,
                verify_zip_crc=args.verify_zip_crc,
            )
            saved = controller.save()
            _emit({"ok": True, "source": source.to_dict(), "project_path": str(saved)}, json_mode=True)
            return 0
        if command == "add-baseline":
            baseline = controller.add_baseline(
                args.path,
                label=args.label,
                full_integrity=args.full_integrity,
            )
            saved = controller.save()
            _emit({"ok": bool(baseline.summary.get("ok")), "baseline": baseline.to_dict(), "project_path": str(saved)}, json_mode=True)
            return 0 if baseline.summary.get("ok") else 2
        if command == "show-project":
            _emit(project.to_dict(), json_mode=True)
            return 0
        if command == "preflight":
            payload = controller.preflight()
            _emit(payload, json_mode=True)
            return 0 if payload.get("ok") else 2
        if command == "plan":
            payload = controller.plan()
            _emit(payload, json_mode=True)
            return 0 if payload.get("engine_plan", {}).get("ok") else 2
        if command == "compare":
            payload = controller.compare_target_to_baselines(full_integrity=False)
            _emit(payload, json_mode=True)
            return 0 if payload.get("ok") else 2
        if command == "export":
            if args.format == "project":
                output = controller.export_project_manifest(args.output)
            else:
                output = controller.export_test04_manifest(
                    args.output,
                    baseline_test03_root=args.baseline_test03_root,
                    legacy_memory_root=args.legacy_memory_root,
                )
            _emit({"ok": True, "output": str(output)}, json_mode=True)
            return 0
        if command == "run":
            expected = confirmation_token(controller.settings())
            if args.confirm != expected:
                raise ValueError(f"Nieprawidłowy token. Oczekiwano: {expected}")
            payload = controller.run(confirmation=args.confirm)
            _emit(payload, json_mode=True)
            return 0 if payload.get("engine_result", {}).get("ok") else 2
        raise AssertionError(command)
    except KeyboardInterrupt:
        _emit({"ok": False, "status": "cancelled"}, json_mode=True)
        return 130
    except Exception as exc:
        _emit({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}, json_mode=True)
        return 1


__all__ = ["APP_VERSION", "build_parser", "main"]
