"""Non-invasive Qt visual and interaction acceptance for JSS.

Only synthetic SYSTEM data in a fresh directory outside the checkout.  This
program never starts Jaźń, Ollama, a tunnel, or an MCP service.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import html
import json
import os
from pathlib import Path
from typing import Any

PROFILES = ("technical-workbench", "operations-studio", "fluent-studio")
SCREENS = (
    ("pulpit", "Pulpit"),
    ("uslugi", "Usługi i procesy"),
    ("testy", "Katalog testów"),
    ("tpa", "TPA"),
    ("ustawienia", "Ustawienia"),
    ("polaczenia", "Połączenie z ChatGPT"),
)


def prepare_output(path: Path, checkout: Path) -> Path:
    """Refuse checkout, its descendants, symlinks and pre-existing output."""
    if path.is_symlink():
        raise ValueError("output_symlink_forbidden")
    target = path.resolve()
    if target == checkout.resolve() or checkout.resolve() in target.parents:
        raise ValueError("output_must_be_outside_checkout")
    if target.exists():
        raise FileExistsError("output_must_be_new")
    target.mkdir(parents=True, exist_ok=False)
    return target


def isolate_environment(output: Path) -> Path:
    """Scrub host Jaźń settings before any runtime/Qt modules are imported."""
    for key in tuple(os.environ):
        if key.upper().startswith("JAZN_"):
            os.environ.pop(key)
    home = output / "_private_home"
    home.mkdir(mode=0o700)
    for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
                 "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        os.environ[name] = str(home)
    workspace = output / "_runtime"
    os.environ.update(
        JAZN_RUNTIME_WORKSPACE_DIR=str(workspace),
        JAZN_OPERATOR_STATE_ROOT=str(output / "_operator"),
        JAZN_MEMORY_ROOT=str(output / "_memory_disabled"),
        JAZN_MEMORY_MODE="off",
        JAZN_ALLOW_NETWORK="0",
        JAZN_DICTIONARY_ALLOW_NETWORK="0",
        JAZN_MODEL_ADAPTER="null",
        QT_QPA_PLATFORM="offscreen",
    )
    root = output / "_synthetic_system"
    (root / "latka_jazn").mkdir(parents=True)
    for name in ("main.py", "run.py", "latka_jazn/version.py"):
        (root / name).write_text("# synthetic JSS visual CI; not an executable runtime\n", encoding="utf-8")
    return root


def record_png(widget: Any, output: Path, name: str) -> dict[str, Any]:
    """Grab the actual Qt widget, not a generated mockup or stock image."""
    pixmap = widget.grab()
    if pixmap.isNull() or pixmap.width() < 500 or pixmap.height() < 350:
        raise AssertionError("empty_or_undersized_qt_capture:" + name)
    target = output / (name + ".png")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(target), "PNG") or target.stat().st_size < 1024:
        raise AssertionError("png_not_saved:" + name)
    return {"file": target.relative_to(output).as_posix(),
            "width": pixmap.width(), "height": pixmap.height(),
            "bytes": target.stat().st_size,
            "sha256": sha256(target.read_bytes()).hexdigest()}


def emit_reports(output: Path, report: dict[str, Any]) -> None:
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = ["# JSS Visual & Integration CI", "",
            f"Overall: **{report['status']}** · Platform: {report.get('qt_platform', 'unknown')}",
            "", "| Check | Result |", "|---|---|"]
    rows.extend(f"| {key} | {'PASS' if passed else 'FAIL'} |"
                for key, passed in sorted(report["checks"].items()))
    rows += ["", f"PNG captures: **{len(report['captures'])}**",
             "", "All screenshots use a synthetic SYSTEM, MEMORY=off and no service connections.",
             "Screenshots are review evidence, not approved golden pixel baselines.",
             ""]
    if report["errors"]:
        rows += ["## Failures", ""]
        rows.extend(f"- {item}" for item in report["errors"])
    (output / "report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    images = "\n".join(
        f'<figure><img loading="lazy" src="{html.escape(item["file"], quote=True)}" '
        f'alt="{html.escape(item["file"], quote=True)}"><figcaption>'
        f'{html.escape(item["file"])}</figcaption></figure>'
        for item in report["captures"]
    )
    page = ("<!doctype html><html lang='pl'><meta charset='utf-8'>"
            "<title>JSS visual CI</title><style>body{background:#131923;color:#f5f8fc;"
            "font:15px system-ui;margin:25px}main{display:grid;"
            "grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:16px}"
            "figure{margin:0;padding:10px;background:#253041;border-radius:8px}"
            "img{display:block;max-width:100%;height:auto}figcaption{padding:8px}"
            "</style><h1>JSS Visual CI</h1><p>Izolowane dane syntetyczne; "
            "brak dostępu do produkcyjnej MEMORY.</p><main>" + images +
            "</main></html>\n")
    (output / "index.html").write_text(page, encoding="utf-8")


def mark_phase(report: dict[str, Any], phase: str) -> None:
    """Crash-resilient, non-sensitive marker for isolated Qt CI only."""
    report["phase"] = phase
    print("JSS_VISUAL_PHASE " + phase, flush=True)


def run_visual(output: Path, report: dict[str, Any]) -> None:
    # Set all sandbox boundaries before any Qt or Jaźń runtime import.
    root = isolate_environment(output)
    mark_phase(report, "qt_imports")
    from unittest.mock import patch
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPalette
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QScrollArea
    from .core import Controller, Settings, load_settings
    from .window import Window
    from .workspace_layout import load_layout
    from .workbench_theme import workbench_colors

    app = QApplication.instance() or QApplication([])
    if not isinstance(app, QApplication) or app.platformName() != "offscreen":
        raise AssertionError("non_offscreen_qt_backend")
    report["qt_platform"] = app.platformName()
    report["pyside_version"] = pyside_version
    core = Controller(root, Settings())
    if core.settings.theme != PROFILES[0]:
        raise AssertionError("default_not_technical_workbench")
    report["checks"]["synthetic_root_and_memory_off"] = (
        core.root == root and os.environ["JAZN_MEMORY_MODE"] == "off")
    if not report["checks"]["synthetic_root_and_memory_off"]:
        raise AssertionError("nonisolated_core_root")

    def deny(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("unexpected_process_or_network_operation")

    # A GUI action or timer that accidentally attempts service creation fails
    # this job rather than reaching a real daemon or external provider.
    with patch("subprocess.Popen", side_effect=deny), patch("socket.create_connection", side_effect=deny):
        mark_phase(report, "construct_window")
        window = Window(core, smoke=True)
        try:
            window.resize(1240, 840)
            window.show()
            QTest.qWait(90)
            if not window.isVisible():
                raise AssertionError("main_window_hidden")
            for theme in PROFILES:
                mark_phase(report, "theme:" + theme)
                window.select_style(theme)
                QTest.qWait(50)
                saved, _digest = load_settings(root)
                if (window.core.settings.theme != theme or saved.theme != theme
                        or window.style_selector.currentData() != theme):
                    raise AssertionError("theme_not_saved:" + theme)
                colors = workbench_colors(theme, core.settings.accent)
                if window.palette().color(QPalette.ColorRole.Window).name().lower() != colors.background.lower():
                    raise AssertionError("theme_palette_not_applied:" + theme)
                report["checks"]["theme_and_settings:" + theme] = True
                if window.services_table.rowCount() != 6:
                    raise AssertionError("service_rows_missing")
                for slug, title in SCREENS:
                    mark_phase(report, "capture:" + theme + ":" + slug)
                    window.navigate(title)
                    QTest.qWait(35)
                    if window.current_section.text() != title:
                        raise AssertionError("navigation_mismatch:" + title)
                    if not isinstance(window.pages.currentWidget(), QScrollArea):
                        raise AssertionError("page_not_scrollable:" + title)
                    report["captures"].append(record_png(
                        window, output, theme + "/" + slug + "-1240x840"))
                report["checks"]["navigation_and_pages:" + theme] = True
                window.navigate("Usługi i procesy")
                window.resize(860, 580)
                QTest.qWait(95)
                page = window.pages.currentWidget()
                if not isinstance(page, QScrollArea):
                    raise AssertionError("minimum_viewport_not_scrollable:" + theme)
                if (window.width() != 860 or window.height() != 580
                        or page.horizontalScrollBar().maximum() > 0):
                    raise AssertionError("minimum_viewport_overflow:" + theme)
                report["captures"].append(record_png(
                    window, output, theme + "/uslugi-860x580"))
                window.resize(1240, 840)
                QTest.qWait(70)
                report["checks"]["minimum_viewport:" + theme] = True

            mark_phase(report, "distinct_visual_palettes")
            for slug, _title in SCREENS:
                hashes = [next(c["sha256"] for c in report["captures"]
                               if c["file"] == theme + "/" + slug + "-1240x840.png")
                          for theme in PROFILES]
                if len(set(hashes)) != len(PROFILES):
                    raise AssertionError("duplicate_theme_pixels:" + slug)
            report["checks"]["distinct_rendered_theme_images"] = True

            mark_phase(report, "navigation_layout")
            # Keyboard navigation, splitters and dock controls.
            window.navigate("Pulpit")
            window.section_search.setText("Katalog testów")
            QTest.keyClick(window.section_search, Qt.Key.Key_Return)
            if window.current_section.text() != "Katalog testów":
                raise AssertionError("search_keyboard_navigation_failed")
            if window.shell_splitter.count() != 2 or window.content_splitter.count() != 2:
                raise AssertionError("missing_resizeable_panels")
            window.toggle_sidebar()
            if window.sidebar.isVisible():
                raise AssertionError("sidebar_did_not_hide")
            window.toggle_sidebar()
            if not window.sidebar.isVisible():
                raise AssertionError("sidebar_did_not_restore")
            window.switch_sidebar()
            window.persist_layout()
            if not load_layout(root).get("sidebar_right"):
                raise AssertionError("layout_not_persisted")
            window.reset_layout()
            report["checks"]["keyboard_sidebar_splitters_layout"] = True

            mark_phase(report, "unsaved_settings")
            # Preserve an unsaved settings draft when attempting style changes.
            previous = window.core.settings.theme
            original_port = window.fields["mcp_port"].text()
            window.fields["mcp_port"].setText("8999")
            window.select_style("operations-studio" if previous != "operations-studio"
                                else "fluent-studio")
            if (window.core.settings.theme != previous
                    or window.fields["mcp_port"].text() != "8999"):
                raise AssertionError("unsaved_settings_lost")
            window.fields["mcp_port"].setText(original_port)
            report["checks"]["unsaved_settings_guard"] = True

            mark_phase(report, "synthetic_failure")
            # Synthetic failure must be visible and not imply daemon readiness.
            core.emit("status", "state", {"state": "failed", "error": "invalid_status_json"})
            window.poll()
            if ("status" not in window.workspace.failures
                    or "BŁĄD" not in window.dashboard_last_operation.text()
                    or window.quick_runtime_ready
                    or core.accepted_turn_proof):
                raise AssertionError("failure_truth_gate")
            window.navigate("Diagnostyka")
            report["captures"].append(record_png(window, output, "diagnostyka-synthetic-error"))
            report["checks"]["failure_reporting_without_live_runtime"] = True
            if core.jobs:
                raise AssertionError("service_job_started")
            report["checks"]["no_service_jobs"] = True
        finally:
            mark_phase(report, "closing_window")
            window.close()
            app.processEvents()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JSS isolated Qt visual CI", allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    checkout = Path(__file__).resolve().parents[2]
    output = prepare_output(args.output, checkout)
    report: dict[str, Any] = {
        "schema": "jss_visual_ci/v1", "status": "FAIL", "qt_platform": "unknown",
        "profiles": list(PROFILES), "checks": {}, "captures": [],
        "errors": [], "synthetic_only": True, "memory_mode": "off",
        "phase": "startup", "source_sha": os.environ.get("GITHUB_SHA", ""),
        "golden_baselines_verified": False,
    }
    try:
        run_visual(output, report)
        if len(report["captures"]) != len(PROFILES) * (len(SCREENS) + 1) + 1:
            raise AssertionError("capture_count_mismatch")
        if not report["checks"] or not all(report["checks"].values()):
            raise AssertionError("incomplete_checks")
        report["status"] = "PASS"
    except Exception as exc:
        # Do not export potentially private paths, settings, tokens or raw traces.
        report["errors"].append(type(exc).__name__ + ":visual_ci_failure:" + report["phase"])
    finally:
        emit_reports(output, report)
    print(json.dumps({"status": report["status"], "captures": len(report["captures"]),
                      "checks": len(report["checks"]), "errors": report["errors"]}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
