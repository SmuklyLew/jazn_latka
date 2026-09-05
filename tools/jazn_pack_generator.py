#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Jaźń Pack Generator v10.1.86.0.111.

Public launcher for the rewritten folder archiver.

The generator has one core and three interfaces:
- text: classic terminal flow,
- tui: cursor-driven terminal interface,
- studio: native tkinter/ttk window.

Its job is deliberately narrow: archive SYSTEM, MEMORY or SYSTEM+MEMORY,
optionally split one logical ZIP into transport parts, verify and unpack it.
It does not build wheelhouses, dependency bundles or Python runtimes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

try:
    from .jazn_pack_generator_app import (
        CONTENT_CHOICES,
        GENERATOR_TITLE,
        GENERATOR_VERSION,
        SETTINGS_SCHEMA,
        UI_MODE_CHOICES,
        ContentMode,
        PackRequest,
        TransportMode,
        config_report,
        join_parts,
        load_settings,
        save_settings,
        pack,
        plan_pack,
        unpack_package,
        verify_package,
    )
    from .jazn_pack_generator_app.ui_studio import run_studio_ui
    from .jazn_pack_generator_app.ui_text import run_text_ui
    from .jazn_pack_generator_app.ui_tui import run_terminal_tui
except ImportError:
    _tool_dir = str(Path(__file__).resolve().parent)
    if _tool_dir not in sys.path:
        sys.path.insert(0, _tool_dir)
    from jazn_pack_generator_app import (  # type: ignore[no-redef]
        CONTENT_CHOICES,
        GENERATOR_TITLE,
        GENERATOR_VERSION,
        SETTINGS_SCHEMA,
        UI_MODE_CHOICES,
        ContentMode,
        PackRequest,
        TransportMode,
        config_report,
        join_parts,
        load_settings,
        save_settings,
        pack,
        plan_pack,
        unpack_package,
        verify_package,
    )
    from jazn_pack_generator_app.ui_studio import run_studio_ui  # type: ignore[no-redef]
    from jazn_pack_generator_app.ui_text import run_text_ui  # type: ignore[no-redef]
    from jazn_pack_generator_app.ui_tui import run_terminal_tui  # type: ignore[no-redef]


def _request_from_args(args: argparse.Namespace) -> PackRequest:
    memory = Path(args.memory_root).expanduser() if getattr(args, "memory_root", None) else None
    return PackRequest(
        source_root=Path(args.source).expanduser(),
        output_root=Path(args.out_dir).expanduser(),
        content=ContentMode(args.content),
        memory_root=memory,
        transport=TransportMode.SPLIT if args.split else TransportMode.SINGLE,
        part_size_mib=int(args.part_size_mib),
        compression_level=int(args.compression_level),
        force_split=bool(args.force_split),
        overwrite=bool(args.overwrite),
    )


def run_pack_request(
    *,
    source: str | Path,
    out_dir: str | Path,
    content: str = "system",
    split: bool = False,
    split_size_mib: int = 450,
    compression_level: int = 6,
    memory_root: str | Path | None = None,
    force_split: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Programmatic compatibility entrypoint for the rewritten archiver."""
    request = PackRequest(
        source_root=Path(source),
        output_root=Path(out_dir),
        content=ContentMode(content),
        memory_root=Path(memory_root) if memory_root else None,
        transport=TransportMode.SPLIT if split else TransportMode.SINGLE,
        part_size_mib=split_size_mib,
        compression_level=compression_level,
        force_split=force_split,
        overwrite=overwrite,
    )
    return pack(request).to_dict()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jazn_pack_generator.py",
        description=f"{GENERATOR_TITLE} v{GENERATOR_VERSION}",
        allow_abbrev=False,
    )
    parser.add_argument("--ui", choices=UI_MODE_CHOICES, help="Uruchom wybrany interfejs.")
    sub = parser.add_subparsers(dest="command")

    pack_cmd = sub.add_parser("pack", allow_abbrev=False, help="Spakuj SYSTEM/MEMORY.")
    pack_cmd.add_argument("--source", required=True)
    pack_cmd.add_argument("--out-dir", required=True)
    pack_cmd.add_argument("--content", choices=CONTENT_CHOICES, default="system")
    pack_cmd.add_argument("--memory-root")
    pack_cmd.add_argument("--split", action="store_true")
    pack_cmd.add_argument("--part-size-mib", type=int, default=450)
    pack_cmd.add_argument("--compression-level", type=int, default=6)
    pack_cmd.add_argument("--force-split", action="store_true")
    pack_cmd.add_argument("--overwrite", action="store_true")
    pack_cmd.add_argument("--plan-only", action="store_true")

    verify_cmd = sub.add_parser("verify", allow_abbrev=False, help="Sprawdź ZIP lub .zip.001.")
    verify_cmd.add_argument("archive")

    join_cmd = sub.add_parser("join", allow_abbrev=False, help="Połącz części .zip.001...")
    join_cmd.add_argument("first_part")
    join_cmd.add_argument("--output")

    unpack_cmd = sub.add_parser("unpack", allow_abbrev=False, help="Bezpiecznie rozpakuj paczkę.")
    unpack_cmd.add_argument("archive")
    unpack_cmd.add_argument("--destination", required=True)
    unpack_cmd.add_argument("--overwrite", action="store_true")

    sub.add_parser("config", allow_abbrev=False, help="Pokaż konfigurację generatora.")
    return parser


def _run_ui(mode: str) -> int:
    if mode == "text":
        return run_text_ui()
    if mode == "tui":
        return run_terminal_tui()
    if mode == "studio":
        return run_studio_ui()
    raise ValueError(mode)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        if args.ui:
            return _run_ui(args.ui)

        if args.command == "pack":
            request = _request_from_args(args)
            if args.plan_only:
                payload: Any = plan_pack(request).summary()
            else:
                payload = pack(request).to_dict()
        elif args.command == "verify":
            payload = verify_package(Path(args.archive))
        elif args.command == "join":
            destination = Path(args.output) if args.output else None
            payload = {"ok": True, "archive": str(join_parts(Path(args.first_part), destination))}
        elif args.command == "unpack":
            payload = {
                "ok": True,
                "destination": str(
                    unpack_package(
                        Path(args.archive),
                        Path(args.destination),
                        overwrite=bool(args.overwrite),
                    )
                ),
            }
        elif args.command == "config":
            payload = config_report()
        else:
            settings = load_settings()
            mode = str(settings.get("ui_mode") or "studio")
            return _run_ui(mode)

        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
