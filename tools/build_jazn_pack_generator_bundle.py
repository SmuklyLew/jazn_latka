from __future__ import annotations

"""Compatibility CI validator for Jaźń Pack Generator v10.1.86.0.114.

The pre-10.1.86.0.112 tool generated a Base85 single-file launcher. The clean
rewrite uses a small public launcher plus maintained modules under
``tools/jazn_pack_generator_app``. This filename and ``--check`` command remain
as a stable CI entrypoint and validate the active source layout.
"""

import argparse
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "tools" / "jazn_pack_generator.py"
SOURCE_DIR = ROOT / "tools" / "jazn_pack_generator_app"
MODULE_SOURCES = (
    SOURCE_DIR / "__init__.py",
    SOURCE_DIR / "constants.py",
    SOURCE_DIR / "errors.py",
    SOURCE_DIR / "models.py",
    SOURCE_DIR / "settings.py",
    SOURCE_DIR / "scanner.py",
    SOURCE_DIR / "staging.py",
    SOURCE_DIR / "archive.py",
    SOURCE_DIR / "transport.py",
    SOURCE_DIR / "manifest.py",
    SOURCE_DIR / "service.py",
    SOURCE_DIR / "ui_text.py",
    SOURCE_DIR / "ui_tui.py",
    SOURCE_DIR / "ui_studio.py",
)
SOURCE_SET = (LAUNCHER,) + MODULE_SOURCES
EXPECTED_GENERATOR_VERSION = "10.1.86.0.114"


def source_set_sha256() -> str:
    digest = hashlib.sha256()
    for path in SOURCE_SET:
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def validate() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for path in SOURCE_SET:
        if not path.is_file():
            errors.append(f"missing:{path.relative_to(ROOT).as_posix()}")
    if errors:
        return False, errors

    launcher = LAUNCHER.read_text(encoding="utf-8")
    constants = (SOURCE_DIR / "constants.py").read_text(encoding="utf-8")
    match = re.search(r'^GENERATOR_VERSION\s*=\s*"([^"]+)"', constants, re.MULTILINE)
    observed = match.group(1) if match else None
    if observed != EXPECTED_GENERATOR_VERSION:
        errors.append(f"generator_version:{observed!r}")
    if "_BUNDLED_MODULES" in launcher or "b85decode" in launcher:
        errors.append("launcher_still_contains_embedded_bundle")
    if "package_distribution" in launcher:
        errors.append("launcher_still_routes_package_distribution")
    if "jazn_pack_generator_app" not in launcher:
        errors.append("launcher_does_not_use_app_package")
    return not errors, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Jaźń Pack Generator v10.1.86.0.114 source layout",
        allow_abbrev=False,
    )
    parser.add_argument("--check", action="store_true", help="Compatibility flag; validation is always read-only.")
    args = parser.parse_args(argv)
    del args
    ok, errors = validate()
    print(f"generator_source_set_sha256={source_set_sha256() if ok else 'unavailable'}")
    print(f"source_layout_valid={str(ok).lower()}")
    for error in errors:
        print(f"error={error}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
