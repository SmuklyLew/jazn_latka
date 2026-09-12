from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Sequence

from latka_jazn.tools.application_shell import DiagnosticsHub, TerminalSplash, normalize_ui_mode, run_guarded

from .core import (
    APP_NAME,
    APP_VERSION,
    VALID_REVIEW,
    audit,
    invalidate_caches,
    effective_contract,
    filtered,
    find_root,
    load_ui_settings,
    _read_json_cached,
    set_review,
    support_dir,
)
from .runner import PytestRun, run_pytest
from .ui_text import run_text_ui
from .ui_tui import run_tui
from .ui_window import run_window_ui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jazn-tests-studio",
        description=f"{APP_NAME} {APP_VERSION} — uruchamianie, obserwacja i przegląd kontraktów testów Jaźni.",
        allow_abbrev=False,
    )
    parser.add_argument("--root", help="Root repozytorium Jaźni; domyślnie wykrywany automatycznie.")
    parser.add_argument(
        "--ui",
        choices=["text", "tui", "window", "studio"],
        help="Tryb interfejsu. 'studio' pozostaje aliasem zgodności dla 'window'.",
    )
    parser.add_argument("--no-splash", action="store_true", help="Pomiń ekran startowy dla interfejsów terminalowych.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")

    sub = parser.add_subparsers(dest="command")
    p_catalog = sub.add_parser("catalog", help="Pokaż katalog aktywnych testów.", allow_abbrev=False)
    p_catalog.add_argument("--filter", default="")
    p_catalog.add_argument("--status", default="all")
    p_catalog.add_argument("--limit", type=int, default=200)
    p_catalog.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="Pokaż kontrakt pojedynczego testu.", allow_abbrev=False)
    p_show.add_argument("nodeid")

    p_run = sub.add_parser("run", help="Uruchom pojedynczy test.", allow_abbrev=False)
    p_run.add_argument("nodeid")
    p_run.add_argument("--timeout", type=int, default=1800)

    p_all = sub.add_parser("run-all", help="Uruchom cały aktywny zestaw testów.", allow_abbrev=False)
    p_all.add_argument("--timeout", type=int, default=1800)

    sub.add_parser("audit", help="Pokaż audyt katalogu testów.", allow_abbrev=False)
    sub.add_parser("self-test", help="Sprawdź kanał zdarzeń i runner Studia.", allow_abbrev=False)

    p_review = sub.add_parser("review", help="Zapisz ręczną ocenę kontraktu testu.", allow_abbrev=False)
    p_review.add_argument("nodeid")
    p_review.add_argument("--status", required=True, choices=sorted(VALID_REVIEW))
    p_review.add_argument("--purpose", default="")
    p_review.add_argument("--expected", default="")
    p_review.add_argument("--note", default="")
    return parser


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="jazn-tests-studio-") as td:
        root = Path(td)
        (root / "tests").mkdir()
        package = root / "tools" / "jazn_tests_studio"
        package.mkdir(parents=True)
        (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        source = Path(__file__).with_name("progress_plugin.py")
        (package / "__init__.py").write_text("", encoding="utf-8")
        shutil.copyfile(source, package / "progress_plugin.py")
        (root / "tests" / "test_demo.py").write_text(
            "def test_ok():\n    assert True\n\ndef test_skip():\n    import pytest\n    pytest.skip('demo')\n",
            encoding="utf-8",
        )
        catalog = {
            "schema": "jazn_tests_studio_contract_catalog/v2",
            "active_definition_count": 2,
            "contracts": {
                "tests/test_demo.py::test_ok": {
                    "status": "current", "category": "unit", "purpose": "Demo pass", "tags": []
                },
                "tests/test_demo.py::test_skip": {
                    "status": "current", "category": "unit", "purpose": "Demo skip", "tags": []
                },
            },
        }
        (package / "test_contracts.json").write_text(json.dumps(catalog), encoding="utf-8")
        invalidate_caches()
        cache_before = _read_json_cached.cache_info()
        first_rows = filtered(root)
        cache_middle = _read_json_cached.cache_info()
        second_rows = filtered(root)
        cache_after = _read_json_cached.cache_info()
        cache_ok = (
            len(first_rows) == len(second_rows) == 2
            and cache_middle.misses - cache_before.misses == 1
            and cache_after.misses == cache_middle.misses
            and cache_after.hits > cache_middle.hits
        )
        events: list[dict[str, Any]] = []
        result = PytestRun(root, timeout=60, on_event=events.append).start().wait(90)
        types = {str(event.get("type")) for event in events}
        statuses = {str(event.get("status")) for event in events if event.get("type") == "result"}
        ok = (
            bool(result.get("ok"))
            and cache_ok
            and normalize_ui_mode("studio", default="text") == "window"
            and {"collection", "start", "result", "finished"}.issubset(types)
            and {"PASSED", "SKIPPED"}.issubset(statuses)
        )
        return {
            "ok": ok,
            "result": result,
            "event_types": sorted(types),
            "statuses": sorted(statuses),
            "catalog_cache_ok": cache_ok,
            "studio_alias": normalize_ui_mode("studio", default="text"),
        }


def _run_command(args: argparse.Namespace, root: Path) -> int:
    command = args.command
    if command == "audit":
        print(json.dumps(audit(root), indent=2, ensure_ascii=False))
        return 0
    if command == "catalog":
        rows = filtered(root, args.filter, args.status)[: max(0, int(args.limit))]
        if args.json:
            print(json.dumps(dict(rows), indent=2, ensure_ascii=False))
        else:
            for nodeid, item in rows:
                print(f"[{item.get('status', 'current')}] {nodeid} — {item.get('purpose', '')}")
        return 0
    if command == "show":
        print(json.dumps(effective_contract(root, args.nodeid), indent=2, ensure_ascii=False))
        return 0
    if command == "run":
        result = run_pytest(root, [args.nodeid], timeout=args.timeout, live=True)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    if command == "run-all":
        result = run_pytest(root, timeout=args.timeout, live=True)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    if command == "review":
        set_review(root, args.nodeid, args.status, args.purpose, args.expected, args.note)
        return 0
    raise RuntimeError(f"Nieznana komenda: {command}")


def _dispatch_ui(root: Path, ui: str, diagnostics: DiagnosticsHub) -> int:
    if ui == "window":
        return run_window_ui(root, diagnostics)
    if ui == "tui":
        return run_tui(root, diagnostics)
    return run_text_ui(root, diagnostics)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "self-test":
        diagnostics = DiagnosticsHub("jazn-tests-studio", Path(tempfile.gettempdir()) / "jazn-tests-studio-self-test", enabled=True)
        return run_guarded(
            lambda: _print_self_test(), diagnostics, app_name=APP_NAME
        )

    try:
        root = find_root(args.root)
    except Exception as exc:
        print(f"{APP_NAME}: {type(exc).__name__}: {exc}")
        return 2

    settings = load_ui_settings(root)
    diagnostics = DiagnosticsHub(
        "jazn-tests-studio",
        support_dir(root),
        enabled=settings.diagnostics_enabled,
        limit=settings.diagnostics_limit,
        minimum_level=settings.log_level,
    )
    diagnostics.record("INFO", "Start aplikacji", version=APP_VERSION, root=str(root), command=args.command)

    if args.command:
        return run_guarded(lambda: _run_command(args, root), diagnostics, app_name=APP_NAME)

    try:
        ui = normalize_ui_mode(args.ui, default=settings.ui_mode)
    except ValueError as exc:
        print(f"{APP_NAME}: {exc}")
        return 2

    def run_interface() -> int:
        splash_enabled = settings.splash_enabled and not bool(args.no_splash)
        if ui == "window":
            return _dispatch_ui(root, ui, diagnostics)
        with TerminalSplash(APP_NAME, enabled=splash_enabled) as splash:
            splash.step("Wczytywanie katalogu i ustawień")
            audit(root)
            splash.step(f"Uruchamianie interfejsu {ui}")
        return _dispatch_ui(root, ui, diagnostics)

    return run_guarded(run_interface, diagnostics, app_name=APP_NAME)


def _print_self_test() -> int:
    payload = self_test()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
