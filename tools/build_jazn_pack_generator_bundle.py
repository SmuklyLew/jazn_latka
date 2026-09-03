from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "tools" / "pack_generator_sources"
CORE_SOURCE = SOURCE_DIR / "jazn_pack_generator_v1001.py"
UI_SOURCE = SOURCE_DIR / "jazn_pack_generator_v1001_ui.py"
SOURCE_METADATA = SOURCE_DIR / "__init__.py"
LAUNCHER = ROOT / "tools" / "jazn_pack_generator.py"

SOURCE_SET = (LAUNCHER, CORE_SOURCE, UI_SOURCE, SOURCE_METADATA)
LAUNCHER_MARKERS = (
    "jazn_pack_generator_v1001.py",
    "jazn_pack_generator_v1001_ui.py",
    'GENERATOR_VERSION = _impl.GENERATOR_VERSION',
)


def source_set_bytes() -> bytes:
    payload = bytearray()
    for path in SOURCE_SET:
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        data = path.read_bytes()
        payload.extend(len(relative).to_bytes(4, "big"))
        payload.extend(relative)
        payload.extend(len(data).to_bytes(8, "big"))
        payload.extend(data)
    return bytes(payload)


def build(*, check: bool = False) -> tuple[bool, str]:
    existing = all(path.is_file() for path in SOURCE_SET)
    launcher = LAUNCHER.read_text(encoding="utf-8") if LAUNCHER.is_file() else ""
    markers_ok = all(marker in launcher for marker in LAUNCHER_MARKERS)
    legacy_not_loaded = (
        "jazn_pack_generator_v89.py" not in launcher
        and "jazn_pack_generator_v88.py" not in launcher
        and "tkinter" not in launcher
    )
    fresh = bool(existing and markers_ok and legacy_not_loaded)
    digest = hashlib.sha256(source_set_bytes()).hexdigest() if existing else "missing"
    if check:
        return fresh, digest
    if not fresh:
        raise RuntimeError("Generator v10.0.1 modular launcher/source set is incomplete")
    return True, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the modular Jaźń Pack Generator v10.0.1 source set",
        allow_abbrev=False,
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    ok, digest = build(check=args.check)
    print(f"generator_source_set_sha256={digest}")
    print(f"bundle_fresh={str(ok).lower()}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
