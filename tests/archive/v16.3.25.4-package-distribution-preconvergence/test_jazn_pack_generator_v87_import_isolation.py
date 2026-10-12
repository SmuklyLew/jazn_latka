from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_direct_spec_load_keeps_public_tools_generator_importable() -> None:
    script = """
import importlib
import importlib.util
from pathlib import Path
import sys

path = Path("tools/jazn_pack_generator.py").resolve()
name = "jazn_pack_generator_direct_spec_guard"
spec = importlib.util.spec_from_file_location(name, path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module
spec.loader.exec_module(module)

public = importlib.import_module("tools.jazn_pack_generator")
assert public.GENERATOR_VERSION == "8.7"
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
