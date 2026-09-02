from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "pack_generator_sources" / "jazn_pack_generator_v88.py"
OUTPUT = ROOT / "tools" / "jazn_pack_generator.py"


def source_bytes() -> bytes:
    data = SOURCE.read_bytes()
    if not data.endswith(b"\n"):
        data += b"\n"
    return data


def build(*, check: bool = False) -> tuple[bool, str]:
    expected = source_bytes()
    current = OUTPUT.read_bytes() if OUTPUT.is_file() else b""
    fresh = current == expected
    digest = hashlib.sha256(expected).hexdigest()
    if check:
        return fresh, digest
    if not fresh:
        OUTPUT.write_bytes(expected)
    return True, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministically build tools/jazn_pack_generator.py")
    parser.add_argument("--check", action="store_true", help="fail when generated bundle is stale")
    args = parser.parse_args(argv)
    ok, digest = build(check=args.check)
    print(f"generator_bundle_sha256={digest}")
    print(f"bundle_fresh={str(ok).lower()}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
