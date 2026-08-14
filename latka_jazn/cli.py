from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

from latka_jazn import _cli_core as _core
from latka_jazn._cli_core import *  # noqa: F403


def _subparsers(parser: argparse.ArgumentParser) -> Any:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise RuntimeError("canonical CLI parser has no subparsers action")


def build_parser() -> argparse.ArgumentParser:
    """Return the canonical CLI plus the independent memory-attach command."""

    parser = _core.build_parser()
    sub = _subparsers(parser)
    if "memory-attach" not in sub.choices:
        child = sub.add_parser("memory-attach", allow_abbrev=False)
        _core._add_common(child)
        child.add_argument("--parts-dir", type=Path, required=True)
        child.add_argument("--zip-name")
        child.add_argument("--work-dir", type=Path)
        child.add_argument("--time-budget-seconds", type=float, default=25.0)
        child.add_argument("--no-crc", action="store_true")
        child.add_argument(
            "--force-reextract",
            action="store_true",
            help=(
                "Wyczyść staging dołączania pamięci; nigdy nie omija "
                "weryfikacji systemu ani manifestu memory."
            ),
        )
    return parser


def _memory_attach(argv: Sequence[str]) -> int:
    parser = build_parser()
    ns = parser.parse_args(list(argv))
    root = Path(ns.root).resolve()
    from latka_jazn.packaging.memory_package_contract import attach_memory_package

    result = attach_memory_package(
        root,
        parts_dir=ns.parts_dir,
        base_zip_name=ns.zip_name,
        work_dir=ns.work_dir,
        time_budget_seconds=ns.time_budget_seconds,
        run_crc=not ns.no_crc,
        force_reextract=bool(ns.force_reextract),
    )
    _core._emit(result.to_dict(), as_json=True)
    return int(result.exit_code)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "memory-attach":
        return _memory_attach(args)
    return int(_core.main(args))


if __name__ == "__main__":
    raise SystemExit(main())
