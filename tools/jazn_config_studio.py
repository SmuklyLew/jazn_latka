#!/usr/bin/env python3
"""Jaźń Configuration Studio launcher; EXE remains an operator client, not SYSTEM."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def resolve_root(explicit: str | None = None) -> Path:
    requested = explicit or os.environ.get("JAZN_ROOT")
    candidates = [Path(requested)] if requested else [Path.cwd(), Path(__file__).resolve().parent.parent]
    for candidate in candidates:
        root = candidate.expanduser().resolve()
        if (root / "main.py").is_file() and (root / "latka_jazn" / "version.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            return root
    raise RuntimeError("Brak zweryfikowanego katalogu Jaźni; ustaw JAZN_ROOT.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jaźń — Studio konfiguracji")
    parser.add_argument("--root", help="Katalog SYSTEM; alternatywnie JAZN_ROOT")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--smoke", action="store_true", help="Test importu i dostępu do repo bez tworzenia okna")
    modes.add_argument("--gui-smoke", action="store_true", help="Utwórz rzeczywiste okno i ekrany GUI bez mainloop")
    modes.add_argument("--paths-json", action="store_true", help="Stan lokalizacji w JSON (tylko odczyt)")
    modes.add_argument("--check-profile", type=Path, help="Zweryfikuj profil przed startem PowerShell")
    parser.add_argument("--emit-validated-env", action="store_true",
                        help="Zwróć jeden zweryfikowany snapshot JSON dla launchera")
    args = parser.parse_args(argv)
    if args.emit_validated_env and not args.check_profile:
        parser.error("--emit-validated-env wymaga --check-profile")
    root = resolve_root(args.root)
    from latka_jazn.tools.configuration_studio import (
        describe_profile, inspect_system, profile_file, validated_launch_values,
    )
    if args.smoke:
        from latka_jazn.tools.configuration_studio_ui import ConfigurationStudio
        assert ConfigurationStudio is not None
        inspect_system(root)
        print("JaznConfigurationStudio smoke OK")
        return 0
    if args.gui_smoke:
        import tkinter as tk
        from latka_jazn.tools.configuration_studio_ui import ConfigurationStudio
        window = tk.Tk()
        window.withdraw()
        try:
            studio = ConfigurationStudio(window, system=root)
            for page in ("overview", "paths", "settings", "diagnostics"):
                studio.open_page(page)
            window.update_idletasks()
        finally:
            window.destroy()
        print("JaznConfigurationStudio GUI smoke OK")
        return 0
    if args.paths_json:
        print(json.dumps(inspect_system(root), ensure_ascii=False, indent=2))
        return 0
    if args.check_profile:
        path = args.check_profile.expanduser().resolve()
        expected = profile_file(root, name=path.stem)
        if expected != path or not path.is_file():
            raise ValueError("Profil musi istnieć w kanonicznym katalogu profili Jaźni.")
        values = validated_launch_values(root, name=path.stem)
        if args.emit_validated_env:
            print(json.dumps({"schema": "jazn_configuration_profile/v1", "values": values},
                             ensure_ascii=False, sort_keys=True))
        else:
            print("Validated configuration profile")
        return 0
    describe_profile(root)
    from latka_jazn.tools.configuration_studio_ui import run_window
    return int(run_window(root))


if __name__ == "__main__":
    raise SystemExit(main())
