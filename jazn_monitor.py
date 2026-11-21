"""Standalone Jaźń Monitor launcher; no runtime control-plane imports."""
from __future__ import annotations

import argparse
import hashlib
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
        from PySide6.QtCore import QLockFile, QTimer
        from PySide6.QtWidgets import QApplication
        from tools.jazn_monitor.window import MonitorWindow
    except ImportError:
        print("PySide6 is an optional GUI dependency; nothing was installed.", file=sys.stderr)
        return 2
    app = QApplication(sys.argv[:1])
    # One observer per selected root, without daemon ownership or PID killing.
    lock = None
    if not opts.gui_smoke:
        selected_root = str(opts.root.expanduser().resolve()) if opts.root else "unselected"
        digest = hashlib.sha256(selected_root.casefold().encode("utf-8")).hexdigest()[:20]
        lock_dir = Path.home() / ".jazn_monitor"
        try:
            lock_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print("Nie można utworzyć blokady Monitora: " + type(exc).__name__, file=sys.stderr)
            return 2
        lock = QLockFile(str(lock_dir / (digest + ".lock")))
        lock.setStaleLockTime(0)  # long-lived singleton; never steal by age
        if not lock.tryLock(0):
            if lock.error() == QLockFile.LockError.LockFailedError:
                print("Jaźń Monitor jest już uruchomiony dla wybranego ROOT.")
                return 0
            print("Nie można potwierdzić wyłączności Monitora.", file=sys.stderr)
            return 2
    try:
        window = MonitorWindow(opts.root, opts.daemon_port, opts.ollama_port,
                               smoke=opts.gui_smoke)
        if opts.gui_smoke:
            QTimer.singleShot(100, app.quit)
        else:
            window.show()
        return int(app.exec())
    finally:
        if lock is not None:
            lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
