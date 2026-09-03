from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "pack_generator_sources" / "jazn_pack_generator_v89.py"
LEGACY_SOURCE = ROOT / "tools" / "pack_generator_sources" / "jazn_pack_generator_v88.py"
OUTPUT = ROOT / "tools" / "jazn_pack_generator.py"

LAUNCHER_MARKER = 'pack_generator_sources" / "jazn_pack_generator_v89.py"'


def source_bytes() -> bytes:
    data = SOURCE.read_bytes()
    if not data.endswith(b"\n"):
        data += b"\n"
    return data


def build(*, check: bool = False) -> tuple[bool, str]:
    source = source_bytes()
    digest = hashlib.sha256(source).hexdigest()
    launcher = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
    fresh = bool(SOURCE.is_file() and LEGACY_SOURCE.is_file() and LAUNCHER_MARKER in launcher)
    if check:
        return fresh, digest
    if not fresh:
        raise RuntimeError("Generator 8.9 modular launcher/source set is incomplete")
    return True, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the modular Jaźń Pack Generator 8.9 source set")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    ok, digest = build(check=args.check)
    print(f"generator_source_sha256={digest}")
    print(f"bundle_fresh={str(ok).lower()}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
