"""Repeatable native/offscreen TPA smoke with screenshots and real run reports."""
from __future__ import annotations
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tpa_view import TPAPanel


def select_existing_model(panel: TPAPanel, requested: str, installed: list[str]) -> None:
    """Select only a model returned by the verified local Ollama inventory."""
    panel.set_installed_models(installed)
    index = panel.model.findData(requested)
    if index < 0:
        raise ValueError("Wskazany model Ollama nie jest zainstalowany lokalnie: " + requested)
    panel.model.setCurrentIndex(index)


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default="")
    parser.add_argument("--expected-platform", default="windows" if os.name == "nt" else "offscreen")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    from latka_jazn.tools.application_shell.operator_paths import validate_operator_path
    output = validate_operator_path(args.output.absolute(), root, directory=True)
    output.mkdir(parents=True, exist_ok=False)
    # This helper is a fresh process, never the active operator application's ENV.
    for name in list(os.environ):
        if name.upper().startswith("JAZN_"):
            os.environ.pop(name)
    os.environ.update(JAZN_OPERATOR_STATE_ROOT=str(output / "operator"), JAZN_RUNTIME_WORKSPACE_DIR=str(output / "runtime"),
                      JAZN_MEMORY_ROOT=str(output / "memory"), JAZN_MEMORY_MODE="off")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QScrollArea
    from .core import Controller, Settings
    from .window import Window
    from .tpa_catalog import execution_map
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    assert app.platformName() == args.expected_platform, app.platformName()
    window = Window(Controller(root, Settings(theme="violet-night")), smoke=True)
    window.resize(1380, 1000)
    window.show()
    window.navigate("TPA")
    QTest.qWait(150)
    panel = window.local_acceptance_panel
    ids = tuple(args.case or [c["id"] for c in execution_map()])
    if args.live and args.model:
        from .probes import ollama
        evidence = ollama(args.model)
        installed = evidence["models"]
        assert isinstance(installed, list)
        select_existing_model(panel, args.model, installed)
    beats = []
    from PySide6.QtCore import QTimer
    timer = QTimer()
    timer.timeout.connect(lambda: beats.append(time.monotonic()))
    timer.start(50)
    panel.check_ready()
    deadline = time.monotonic() + 30
    while panel.runner.active and time.monotonic() < deadline:
        QTest.qWait(20)
    assert not panel.runner.active and panel.runner.probe.get("ok"), panel.runner.probe
    panel.start(ids, "live" if args.live else "regression")
    deadline = time.monotonic() + (1000 if args.live else 360)
    QTest.qWait(100)
    assert window.isVisible()
    window.grab().save(str(output / "tpa-running.png"))
    while panel.runner.active and time.monotonic() < deadline:
        QTest.qWait(20)
    if panel.runner.active:
        panel.runner.stop()
        while panel.runner.active:
            QTest.qWait(20)
        raise TimeoutError("TPA smoke did not finish within its deadline")
    report = panel.report
    assert report and report["finished_utc"]
    window.resize(1380, 1000)
    scroll = window.pages.currentWidget()
    assert isinstance(scroll, QScrollArea)
    scroll.verticalScrollBar().setValue(0)
    panel.open_report()
    QTest.qWait(100)
    window.grab().save(str(output / "tpa-report.png"))
    panel.tabs.setCurrentWidget(panel.instructions)
    window.grab().save(str(output / "tpa-results.png"))
    window.resize(860, 580)
    QTest.qWait(150)
    assert window.width() == 860 and window.height() == 580, (window.width(), window.height())
    page = window.pages.currentWidget()
    assert isinstance(page, QScrollArea)
    assert page.horizontalScrollBar().maximum() == 0, page.horizontalScrollBar().maximum()
    window.grab().save(str(output / "tpa-small.png"))
    window.core.settings = replace(window.core.settings, theme="light")
    window.apply_theme()
    window.resize(1380, 1000)
    QTest.qWait(100)
    panel.table.setFocus()
    QTest.keyClick(panel.table, Qt.Key.Key_Down)
    scroll.verticalScrollBar().setValue(0)
    window.grab().save(str(output / "tpa-light.png"))
    panel.runner.store.export_zip(report, output / "example-report.zip")
    (output / "example-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {"platform": app.platformName(), "device_pixel_ratio": window.devicePixelRatioF(),
              "visible": window.isVisible(), "responsive_timer_ticks": len(beats),
              "minimum_window_checked": [860, 580],
              "horizontal_scroll_minimum_window": page.horizontalScrollBar().maximum(),
              "run_id": report["run_id"], "source": report["source"],
              "results": [{k: row.get(k) for k in ("case_id", "status", "full_gate", "reason")} for row in report["results"]],
              "persistence_error": report.get("persistence_error")}
    (output / "smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    timer.stop()
    window.close()
    app.processEvents()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if len(beats) > 3 and not report.get("persistence_error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
