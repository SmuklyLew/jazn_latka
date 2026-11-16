"""Standalone Jaźń Monitor launcher; no runtime control-plane imports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jaźń Monitor (Windows/Ubuntu, read-only)")
    parser.add_argument("--root", type=Path, help="Selected Jaźń SYSTEM directory")
    parser.add_argument("--daemon-port", type=int, default=8787)
    parser.add_argument("--ollama-port", type=int, default=11434)
    parser.add_argument("--probe-json", action="store_true", help="Single read-only JSON observation")
    parser.add_argument("--gui-smoke", action="store_true", help="Qt smoke without any probes")
    opts = parser.parse_args(argv)
    if not 1 <= opts.daemon_port <= 65535 or not 1 <= opts.ollama_port <= 65535:
        parser.error("Ports must be 1..65535")
    if opts.probe_json:
        from tools.jazn_monitor.probe import snapshot
        print(json.dumps(snapshot(opts.root, daemon_port=opts.daemon_port,
                                  ollama_port=opts.ollama_port), ensure_ascii=False, indent=2))
        return 0
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from tools.jazn_monitor.window import MonitorWindow
    except ImportError:
        print("PySide6 is an optional GUI dependency; nothing was installed.", file=sys.stderr)
        return 2
    app = QApplication(sys.argv[:1])
    window = MonitorWindow(opts.root, opts.daemon_port, opts.ollama_port,
                           smoke=opts.gui_smoke)
    if opts.gui_smoke:
        QTimer.singleShot(100, app.quit)
    else:
        window.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
