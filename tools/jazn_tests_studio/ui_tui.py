from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import threading
from typing import Any

from latka_jazn.tools.application_shell import DiagnosticsHub

from .core import (
    APP_NAME,
    APP_VERSION,
    UI_STATUS,
    audit,
    effective_contract,
    filtered,
    load_ui_settings,
    save_ui_settings,
)
from .runner import PytestRun


class _State:
    def __init__(self, root: Path, diagnostics: DiagnosticsHub) -> None:
        self.root = root
        self.diagnostics = diagnostics
        self.page = "home"
        self.rows = filtered(root)
        self.selected = 0
        self.active_run: PytestRun | None = None
        self.current = "—"
        self.total = 0
        self.completed = 0
        self.counts = {name: 0 for name in ("CORRECT", "FAIL", "ERROR", "SKIP", "XFAIL", "XPASS")}
        self.results: list[tuple[str, str, float]] = []
        self.output: list[str] = []
        self.settings = load_ui_settings(root)
        self._lock = threading.Lock()

    def on_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            kind = str(event.get("type") or "")
            if kind == "process_start":
                self.output.append("START: " + " ".join(map(str, event.get("command") or [])))
            elif kind == "collection":
                self.total = int(event.get("total") or 0)
            elif kind == "start":
                self.current = str(event.get("nodeid") or "—")
            elif kind == "result":
                raw = str(event.get("status") or "ERROR")
                shown = UI_STATUS.get(raw, raw)
                if shown not in self.counts:
                    shown = "ERROR"
                self.counts[shown] += 1
                self.completed = int(event.get("completed") or self.completed + 1)
                self.total = int(event.get("total") or self.total)
                self.results.append((shown, str(event.get("nodeid") or ""), float(event.get("duration") or 0.0)))
                if len(self.results) > 400:
                    self.results = self.results[-400:]
            elif kind == "output":
                text = str(event.get("text") or "").rstrip()
                if text:
                    self.output.append(text)
                    self.output = self.output[-250:]
            elif kind == "finished":
                self.current = "—"
                self.active_run = None
                self.output.append("FINAL: " + json.dumps({k: v for k, v in event.items() if k != "output"}, ensure_ascii=False, default=str))
            self.diagnostics.record("DEBUG", "pytest-event", event_type=kind, nodeid=event.get("nodeid"), status=event.get("status"))

    def start(self, nodeids: list[str] | None) -> None:
        if self.active_run is not None:
            return
        self.completed = self.total = 0
        self.current = "—"
        self.counts = {name: 0 for name in self.counts}
        self.results.clear()
        self.output.clear()
        self.page = "results"
        self.active_run = PytestRun(self.root, nodeids, timeout=1800, on_event=self.on_event).start()
        self.diagnostics.record("INFO", "Uruchomiono pytest", scope="selected" if nodeids else "all", nodeids=nodeids or [])

    def stop(self) -> None:
        if self.active_run is not None:
            self.active_run.stop()
            self.diagnostics.record("WARNING", "Zażądano zatrzymania pytest")


def run_tui(root: Path, diagnostics: DiagnosticsHub) -> int:
    try:
        from prompt_toolkit import Application
        from prompt_toolkit.formatted_text import FormattedText
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.layout.dimension import Dimension
        from prompt_toolkit.styles import Style
    except ImportError:
        diagnostics.record("ERROR", "Brak prompt_toolkit dla trybu TUI")
        from .ui_text import run_text_ui
        print("Tryb TUI wymaga prompt-toolkit; uruchamiam bezpieczny tryb tekstowy.")
        return run_text_ui(root, diagnostics)

    state = _State(root, diagnostics)
    pages = ["home", "tests", "results", "settings", "diagnostics"]
    labels = {
        "home": "Główna",
        "tests": "Testy",
        "results": "Wyniki",
        "settings": "Ustawienia",
        "diagnostics": "Diagnostyka",
    }

    def header_text() -> FormattedText:
        running = "RUNNING" if state.active_run is not None else "READY"
        return FormattedText([
            ("class:brand", f" {APP_NAME} {APP_VERSION} "),
            ("class:muted", f"│ {labels.get(state.page, state.page)} │ {running} "),
        ])

    def nav_text() -> FormattedText:
        parts: list[tuple[str, str]] = []
        for idx, page in enumerate(pages, 1):
            active = page == state.page
            parts.append(("class:nav.active" if active else "class:nav", f" {idx}  {labels[page]} \n"))
        parts.append(("class:muted", "\n r  uruchom test\n a  uruchom wszystkie\n x  zatrzymaj\n q  wyjście\n"))
        return FormattedText(parts)

    def home_text() -> str:
        data = audit(root)
        return (
            f"{APP_NAME} {APP_VERSION}\n\n"
            f"Repozytorium: {data['root']}\n"
            f"Aktywne definicje: {data['definitions']}\n"
            f"Ręczne recenzje: {data['manual_reviews']}\n"
            f"Statusy: {data['by_status']}\n"
            f"Kategorie: {data['by_category']}\n"
            f"Wczytanie katalogu: {data['catalog_load_seconds']:.4f}s\n\n"
            "Studio ma trzy równorzędne tryby: tekstowy, pełnoekranowy TUI i okno.\n"
            "Długie testy są uruchamiane poza pętlą interfejsu; postęp pozostaje żywy."
        )

    def tests_text() -> str:
        if not state.rows:
            return "Brak testów."
        state.selected = max(0, min(state.selected, len(state.rows) - 1))
        start = max(0, state.selected - 12)
        end = min(len(state.rows), start + 26)
        lines = [f"Testy {state.selected + 1}/{len(state.rows)} — ↑/↓ wybór, Enter szczegóły, r uruchom\n"]
        for i in range(start, end):
            nodeid, item = state.rows[i]
            marker = "▶" if i == state.selected else " "
            lines.append(f"{marker} [{item.get('status','current')}] {nodeid}")
            if i == state.selected:
                lines.append(f"    {item.get('purpose','')}")
        return "\n".join(lines)

    def result_text() -> str:
        counts = "  ".join(f"{key}:{value}" for key, value in state.counts.items())
        pct = (state.completed / state.total * 100.0) if state.total else 0.0
        lines = [
            f"Postęp: {state.completed}/{state.total} ({pct:.1f}%)",
            f"Bieżący: {state.current}",
            counts,
            "",
            "Ostatnie wyniki:",
        ]
        for status, nodeid, duration in state.results[-18:]:
            lines.append(f"{status:8} {duration:7.3f}s  {nodeid}")
        if state.output:
            lines.extend(["", "Log:", *state.output[-16:]])
        return "\n".join(lines)

    def settings_text() -> str:
        s = state.settings
        return (
            "USTAWIENIA\n\n"
            f"Domyślny interfejs: {s.ui_mode}        [u] zmień\n"
            f"Splashscreen: {'ON' if s.splash_enabled else 'OFF'}             [p] przełącz\n"
            f"Diagnostyka/log: {'ON' if s.diagnostics_enabled else 'OFF'}         [g] przełącz\n"
            f"Poziom logów: {s.log_level}\n"
            f"Log: {diagnostics.log_path}\n\n"
            "Zmiany są zapisywane automatycznie do lokalnych ustawień operatora."
        )

    def diagnostics_text() -> str:
        return f"LOG: {diagnostics.log_path}\n\n{diagnostics.text(limit=80)}"

    def content_text() -> str:
        with state._lock:
            if state.page == "home":
                return home_text()
            if state.page == "tests":
                return tests_text()
            if state.page == "results":
                return result_text()
            if state.page == "settings":
                return settings_text()
            if state.page == "diagnostics":
                return diagnostics_text()
            if state.page == "detail" and state.rows:
                nodeid = state.rows[state.selected][0]
                return json.dumps(effective_contract(root, nodeid), ensure_ascii=False, indent=2)
            return ""

    header = Window(FormattedTextControl(header_text), height=1, style="class:header")
    nav = Window(FormattedTextControl(nav_text), width=Dimension.exact(26), style="class:sidebar", wrap_lines=False)
    content = Window(FormattedTextControl(content_text), style="class:content", wrap_lines=False, always_hide_cursor=True)
    footer = Window(
        FormattedTextControl(lambda: FormattedText([
            ("class:key", " 1-5 "), ("class:footer", "strony  "),
            ("class:key", " ↑↓ "), ("class:footer", "nawigacja  "),
            ("class:key", " r/a "), ("class:footer", "test / wszystkie  "),
            ("class:key", " x "), ("class:footer", "stop  "),
            ("class:key", " q/Ctrl+C "), ("class:footer", "wyjście "),
        ])),
        height=1,
        style="class:footer",
    )
    layout = Layout(HSplit([header, VSplit([nav, content]), footer]))
    kb = KeyBindings()

    @kb.add("q")
    @kb.add("c-c")
    def _quit(event) -> None:
        state.stop()
        diagnostics.record("INFO", "Zamknięto TUI")
        event.app.exit(result=0)

    for idx, page in enumerate(pages, 1):
        def bind_page(page_name: str, key: str) -> None:
            @kb.add(key)
            def _page(event) -> None:  # type: ignore[misc]
                state.page = page_name
        bind_page(page, str(idx))

    @kb.add("up")
    @kb.add("k")
    def _up(event) -> None:
        if state.page == "tests" and state.rows:
            state.selected = max(0, state.selected - 1)

    @kb.add("down")
    @kb.add("j")
    def _down(event) -> None:
        if state.page == "tests" and state.rows:
            state.selected = min(len(state.rows) - 1, state.selected + 1)

    @kb.add("enter")
    def _detail(event) -> None:
        if state.page == "tests" and state.rows:
            state.page = "detail"
        elif state.page == "detail":
            state.page = "tests"

    @kb.add("r")
    def _run_selected(event) -> None:
        if state.rows:
            state.start([state.rows[state.selected][0]])

    @kb.add("a")
    def _run_all(event) -> None:
        state.start(None)

    @kb.add("x")
    def _stop(event) -> None:
        state.stop()

    @kb.add("u")
    def _cycle_ui(event) -> None:
        if state.page != "settings":
            return
        modes = ["text", "tui", "window"]
        pos = modes.index(state.settings.ui_mode) if state.settings.ui_mode in modes else 0
        state.settings = replace(state.settings, ui_mode=modes[(pos + 1) % len(modes)])
        state.settings = save_ui_settings(root, state.settings)

    @kb.add("p")
    def _toggle_splash(event) -> None:
        if state.page == "settings":
            state.settings = save_ui_settings(root, replace(state.settings, splash_enabled=not state.settings.splash_enabled))

    @kb.add("g")
    def _toggle_diag(event) -> None:
        if state.page == "settings":
            state.settings = save_ui_settings(root, replace(state.settings, diagnostics_enabled=not state.settings.diagnostics_enabled))
            diagnostics.reconfigure(enabled=state.settings.diagnostics_enabled)

    style = Style.from_dict({
        "header": "bg:#1f2937 #f9fafb bold",
        "brand": "bg:#2563eb #ffffff bold",
        "muted": "#9ca3af",
        "sidebar": "bg:#111827 #d1d5db",
        "nav": "#d1d5db",
        "nav.active": "bg:#374151 #ffffff bold",
        "content": "bg:#0b1220 #e5e7eb",
        "footer": "bg:#1f2937 #d1d5db",
        "key": "bg:#374151 #f9fafb bold",
    })
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
        mouse_support=True,
        style=style,
        refresh_interval=0.15,
    )
    diagnostics.record("INFO", "Uruchomiono TUI", tests=len(state.rows))
    result = app.run()
    return int(result or 0)
