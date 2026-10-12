#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from latka_jazn.archive import (  # noqa: E402
    ArchiveError,
    ArchiveExtractionService,
    ArchiveSecurityLimits,
    normalize_archive_format,
)


def _limits(args: argparse.Namespace) -> ArchiveSecurityLimits:
    return ArchiveSecurityLimits(
        max_members=args.max_members,
        max_total_uncompressed_bytes=int(args.max_total_gib * 1024**3),
        max_member_bytes=int(args.max_member_gib * 1024**3),
        max_compression_ratio=args.max_ratio,
        require_free_space=not args.no_free_space_check,
    )


def _password(args: argparse.Namespace) -> str | None:
    variable = str(args.password_env or "").strip()
    return os.environ.get(variable) if variable else None


def _add_security(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--password-env", default="JAZN_ARCHIVE_PASSWORD", help="Nazwa zmiennej środowiskowej; hasło nigdy nie trafia do argumentu ani pliku ustawień.")
    parser.add_argument("--max-members", type=int, default=200_000)
    parser.add_argument("--max-total-gib", type=float, default=64.0)
    parser.add_argument("--max-member-gib", type=float, default=16.0)
    parser.add_argument("--max-ratio", type=float, default=500.0)
    parser.add_argument("--no-free-space-check", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jaźń archive I/O — ZIP/ZIP64, 7z, AES-ZIP i split package sets", allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", allow_abbrev=False)
    inspect.add_argument("source", type=Path)
    inspect.add_argument("--format", choices=("auto", "zip", "7z", "aes_zip", "pyzip", "pyzipfile"), default="auto")
    _add_security(inspect)

    extract = sub.add_parser("extract", allow_abbrev=False)
    extract.add_argument("source", type=Path, help="Archiwum, *.package.json albo bazowa nazwa paczki z sidecarem.")
    extract.add_argument("destination", type=Path)
    extract.add_argument("--format", choices=("auto", "zip", "7z", "aes_zip", "pyzip", "pyzipfile"), default="auto")
    extract.add_argument("--replace-existing", action="store_true")
    _add_security(extract)

    pack = sub.add_parser("pack", allow_abbrev=False)
    pack.add_argument("source", type=Path)
    pack.add_argument("output", type=Path)
    pack.add_argument("--format", choices=("zip", "7z", "aes_zip", "pyzip", "pyzipfile"), default="zip")
    pack.add_argument("--compression-level", type=int, default=6)
    pack.add_argument("--aes-bits", type=int, choices=(128, 192, 256), default=256)
    _add_security(pack)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = ArchiveExtractionService(_limits(args))
    password = _password(args)
    if args.command == "inspect":
        source = args.source.expanduser()
        sidecar = source if source.name.endswith(".package.json") else Path(str(source) + ".package.json")
        if sidecar.is_file():
            report = service.verify_package_sidecar(sidecar, password=password)
        else:
            report = service.inspect(source, archive_format=args.format, password=password).to_dict()
    elif args.command == "extract":
        report = service.extract_source(
            args.source,
            args.destination,
            archive_format=args.format,
            password=password,
            replace_existing=args.replace_existing,
        )
    else:
        fmt = normalize_archive_format(args.format)
        if fmt == "aes_zip" and password is None:
            raise ArchiveError(f"Brak hasła w zmiennej {args.password_env!r}.")
        entries = service.entries_from_directory(args.source)
        inspection = service.create_archive(
            entries,
            args.output,
            archive_format=fmt,
            compression_level=args.compression_level,
            password=password if fmt in {"aes_zip", "7z"} else None,
            aes_bits=args.aes_bits,
        )
        report = {"ok": True, "output": str(args.output.expanduser().resolve()), **inspection.to_dict()}
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ArchiveError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
