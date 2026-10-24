"""Every native release lock must honor the patched archive decoder floor."""
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version
import pytest


@pytest.mark.parametrize("target", ["linux-x64", "windows-x64"])
@pytest.mark.parametrize("python", ["312", "313", "314"])
def test_release_lock_has_patched_brotli(target: str, python: str) -> None:
    root = Path(__file__).resolve().parents[1]
    lock = root / "latka_jazn/resources/dependencies/locks/core+archive+pdf" / f"{target}-py{python}.txt"
    entries = [line.split(" --hash=", 1)[0] for line in lock.read_text().splitlines()
               if line and not line.startswith("#")]
    brotli = [Requirement(entry) for entry in entries
              if Requirement(entry).name.lower() == "brotli"]
    assert len(brotli) == 1
    pins = list(brotli[0].specifier)
    assert len(pins) == 1 and pins[0].operator == "=="
    assert Version("1.2.1") <= Version(pins[0].version) < Version("2")
