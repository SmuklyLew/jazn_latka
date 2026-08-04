from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import zlib


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_ROOT = ROOT / ".github" / "runtime_fix_payload"

FILES: dict[str, tuple[str, str | None, str]] = {
    "latka_jazn/tools/package_integrity.py": (
        "package_integrity.py.zlib.b64",
        "2377b94cf46f13248022df9a93dee6d9f14d5a286cec3d1a6f248bb92e703081",
        "aff3b01b9dc97249a87f9636bc0a50c49f399cc2c73880f1021fd2c0e68f6f14",
    ),
    "latka_jazn/cli.py": (
        "cli.py.zlib.b64",
        "b1cb01f9d479959fc2fe0d7e4456fe33cf29c2ec24cd701ea91cfae1d3d55ebc",
        "4def38a6f2e7105267bdde1a1530222a42bcd90a6d0ff045b75217abe581031b",
    ),
    "README.md": (
        "README.md.zlib.b64",
        "e565f344c5e191121b4aeaad4223bba908cbe511551046d56d8f9b6ace95eb7b",
        "37364b61491c8c9a1cf28b278edbd3ccd50cfa368ce29a65f2baa7aac0ce3313",
    ),
    "tests/test_package_integrity_canonical_worktree.py": (
        "test_package_integrity_canonical_worktree.py.zlib.b64",
        "43fd7fe3e4fd1642cbee255d9fb1a7e3dcd048353ef9bb2f48bece41d56a506c",
        "18bf3c6b4863469af6a37dc607f47bdc78466cf0a4c26db691055330aa5c70db",
    ),
    "tests/test_cli_canonical_root.py": (
        "test_cli_canonical_root.py.zlib.b64",
        None,
        "114c882b538b70859d32ba51b4c815b09425d14e75d75013a107e0688059071f",
    ),
    "tests/test_windows_launchers_contract.py": (
        "test_windows_launchers_contract.py.zlib.b64",
        None,
        "134eb50840016202314d9e71a13080e678cfb2759d6cbb9c237a1cfdf87d618c",
    ),
    "JAZN.cmd": (
        "JAZN.cmd.zlib.b64",
        None,
        "55243ab8c0d75edfe28b644629ce474744ebbbb1614d4068ac2ac6354befb44d",
    ),
}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    for relative, (payload_name, expected_before, expected_after) in FILES.items():
        destination = ROOT / relative
        current = destination.read_bytes() if destination.is_file() else None
        if current is not None and sha256(current) == expected_after:
            continue
        if expected_before is None:
            if current is not None:
                raise RuntimeError(f"refusing to replace unexpected existing file: {relative}")
        elif current is None or sha256(current) != expected_before:
            actual = "missing" if current is None else sha256(current)
            raise RuntimeError(
                f"source hash mismatch for {relative}: expected {expected_before}, got {actual}"
            )

        encoded = (PAYLOAD_ROOT / payload_name).read_text(encoding="ascii").strip()
        raw = zlib.decompress(base64.b64decode(encoded, validate=True))
        actual_after = sha256(raw)
        if actual_after != expected_after:
            raise RuntimeError(
                f"payload hash mismatch for {relative}: expected {expected_after}, got {actual_after}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".runtime-fix.tmp")
        temporary.write_bytes(raw)
        temporary.replace(destination)
        print(f"updated {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
