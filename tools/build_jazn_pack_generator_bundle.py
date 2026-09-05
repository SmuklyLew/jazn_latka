from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "tools" / "pack_generator_sources"
SOURCE_METADATA = SOURCE_DIR / "__init__.py"
LAUNCHER = ROOT / "tools" / "jazn_pack_generator.py"
MODULE_SOURCES = (
    ("_jazn_pack_generator_core", SOURCE_DIR / "jazn_pack_generator_core.py"),
    ("_jazn_pack_generator_compat", SOURCE_DIR / "jazn_pack_generator_compat.py"),
    ("_jazn_pack_generator_runtime", SOURCE_DIR / "jazn_pack_generator_runtime.py"),
    ("_jazn_pack_generator_ui", SOURCE_DIR / "jazn_pack_generator_ui.py"),
)
SOURCE_SET = tuple(path for _, path in MODULE_SOURCES) + (SOURCE_METADATA,)


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


def source_set_sha256() -> str:
    return hashlib.sha256(source_set_bytes()).hexdigest()


def _embedded_sources() -> dict[str, str]:
    return {
        name: base64.b85encode(path.read_bytes()).decode("ascii")
        for name, path in MODULE_SOURCES
    }


def render_launcher() -> bytes:
    digest = source_set_sha256()
    embedded = json.dumps(_embedded_sources(), indent=4, sort_keys=True)
    text = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Jaźń / Łatka Pack Generator v10.1.86.0 — bundled public launcher.

Physical operator files:
  1. jazn_pack_generator.py
  2. jazn_pack_generator_settings.json

Run from the repository on Windows:
  py -X utf8 .\\tools\\jazn_pack_generator.py

The maintained generator modules are Base85-encoded into this file and loaded
only in memory. The selected Jaźń source tree remains the canonical provider
of runtime, packaging, dependency and release contracts.
"""
from __future__ import annotations

import base64 as _bundle_base64
import json as _bundle_json
import os as _bundle_os
from pathlib import Path as _BundlePath
import sys as _bundle_sys
import types as _bundle_types
from typing import Any


_BUNDLE_FILE = str(_BundlePath(__file__).resolve())
_BUNDLE_SOURCE_SHA256 = "{digest}"
_BUNDLED_MODULES: dict[str, str] = {embedded}


def _candidate_source_roots() -> tuple[_BundlePath, ...]:
    candidates: list[_BundlePath] = []
    explicit = str(_bundle_os.environ.get("JAZN_SOURCE_ROOT") or "").strip()
    if explicit:
        candidates.append(_BundlePath(explicit).expanduser())

    settings = _BundlePath(_BUNDLE_FILE).with_name("jazn_pack_generator_settings.json")
    if settings.is_file():
        try:
            payload = _bundle_json.loads(settings.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, _bundle_json.JSONDecodeError):
            payload = {{}}
        if isinstance(payload, dict) and str(payload.get("source") or "").strip():
            candidates.append(_BundlePath(str(payload["source"])).expanduser())

    candidates.extend(
        (
            _BundlePath(_BUNDLE_FILE).parent.parent,
            _BundlePath.cwd(),
            _BundlePath("D:/" + ".AI/jazn_latka_master"),
            _BundlePath.home() / "jazn_latka",
        )
    )
    unique: list[_BundlePath] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            continue
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def _bootstrap_source_root() -> _BundlePath:
    for candidate in _candidate_source_roots():
        if (candidate / "latka_jazn" / "version.py").is_file() and (candidate / "run.py").is_file():
            value = str(candidate)
            if value not in _bundle_sys.path:
                _bundle_sys.path.insert(0, value)
            return candidate
    raise RuntimeError(
        "Nie można odnaleźć źródła Jaźni. Ustaw JAZN_SOURCE_ROOT albo umieść obok generatora "
        "jazn_pack_generator_settings.json z polem source wskazującym root Jaźni."
    )


_SOURCE_ROOT = _bootstrap_source_root()


def _load_bundled_module(name: str) -> _bundle_types.ModuleType:
    encoded = _BUNDLED_MODULES[name]
    source = _bundle_base64.b85decode(encoded.encode("ascii")).decode("utf-8")
    module = _bundle_types.ModuleType(name)
    module.__file__ = _BUNDLE_FILE
    module.__package__ = ""
    _bundle_sys.modules[name] = module
    exec(compile(source, f"{{_BUNDLE_FILE}}::{{name}}", "exec"), module.__dict__)
    return module


_impl = _load_bundled_module("_jazn_pack_generator_core")
_compat = _load_bundled_module("_jazn_pack_generator_compat")
_compat.install(_impl)
_runtime = _load_bundled_module("_jazn_pack_generator_runtime")
_runtime.install(_impl)
_ui = _load_bundled_module("_jazn_pack_generator_ui")
_ui.bind(_impl)

GENERATOR_VERSION = _impl.GENERATOR_VERSION
GENERATOR_TITLE = _impl.GENERATOR_TITLE
SETTINGS_SCHEMA = _impl.SETTINGS_SCHEMA
UI_MODE_CHOICES = _ui.UI_MODE_CHOICES
UI_MODE_LABELS = _ui.UI_MODE_LABELS
main = _ui.main


def __getattr__(name: str) -> Any:
    for target in (_ui, _impl, _runtime, _compat):
        if hasattr(target, name):
            return getattr(target, name)
    raise AttributeError(f"module {{__name__!r}} has no attribute {{name!r}}")


class _PublicModule(_bundle_types.ModuleType):
    """Forward compatibility monkeypatches to the in-memory implementation."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name.startswith("__") or name in {{
            "_impl", "_compat", "_runtime", "_ui", "GENERATOR_VERSION",
            "GENERATOR_TITLE", "SETTINGS_SCHEMA", "UI_MODE_CHOICES",
            "UI_MODE_LABELS", "main",
        }}:
            return
        for target in (_impl, _compat, _runtime, _ui):
            if hasattr(target, name):
                setattr(target, name, value)


_current_module = _bundle_sys.modules.get(__name__)
if _current_module is not None and not isinstance(_current_module, _PublicModule):
    _current_module.__class__ = _PublicModule


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
'''
    return text.encode("utf-8")


def build(*, check: bool = False) -> tuple[bool, str]:
    missing = [str(path) for path in SOURCE_SET if not path.is_file()]
    if missing:
        raise RuntimeError("Generator source set is incomplete: " + ", ".join(missing))
    rendered = render_launcher()
    current = LAUNCHER.read_bytes() if LAUNCHER.is_file() else b""
    fresh = current == rendered
    digest = source_set_sha256()
    if check:
        return fresh, digest
    if not fresh:
        temporary = LAUNCHER.with_name(LAUNCHER.name + ".tmp")
        temporary.write_bytes(rendered)
        os.replace(temporary, LAUNCHER)
    return True, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic Jaźń Pack Generator v10.1.86.0 bundled launcher",
        allow_abbrev=False,
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    ok, digest = build(check=args.check)
    print(f"generator_source_set_sha256={digest}")
    print(f"bundle_fresh={str(ok).lower()}")
    if args.check and not ok:
        encoded = base64.b64encode(render_launcher()).decode("ascii")
        for index in range(0, len(encoded), 4000):
            print(f"bundle_expected_base64[{index // 4000:04d}]={encoded[index:index + 4000]}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
