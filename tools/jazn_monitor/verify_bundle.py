"""Verify that an actual frozen executable starts; hash every distributed file."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify_bundle.py dist/JaznMonitor")
    folder = Path(sys.argv[1]).resolve()
    binary = folder / ("JaznMonitor.exe" if os.name == "nt" else "JaznMonitor")
    if not binary.is_file():
        raise SystemExit("Frozen executable missing")
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [str(binary), "--gui-smoke"], capture_output=True,
        timeout=40, env=env, check=False,
    )
    if completed.returncode != 0:
        print(completed.stderr.decode(errors="replace")[-3000:], file=sys.stderr)
        raise SystemExit("Frozen GUI smoke failed: " + str(completed.returncode))
    checksums = []
    for file in sorted(folder.rglob("*")):
        if not file.is_file() or file.name == "SHA256SUMS.txt":
            continue
        hasher = hashlib.sha256()
        with file.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                hasher.update(chunk)
        checksums.append(f"{hasher.hexdigest()}  {file.relative_to(folder).as_posix()}")
    (folder / "SHA256SUMS.txt").write_text(
        "\n".join(checksums) + "\n", encoding="utf-8")
    print(f"Frozen GUI smoke PASS; hashed {len(checksums)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
