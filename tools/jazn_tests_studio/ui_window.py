from __future__ import annotations

import json
from pathlib import Path
import queue
import sys
from typing import Any, Literal

from latka_jazn.tools.application_shell import DiagnosticsHub, ShellSettings

from .core import (
    APP_NAME, APP_VERSION, UI_STATUS, VALID_REVIEW, audit, effective_contract, filtered,
    load_ui_settings, save_ui_settings, set_review,
)
from .runner import PytestRun

def run_window_ui(root: Path, diagnostics: DiagnosticsHub) -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    app = tk.Tk()
    app.title(f"{APP_NAME} {APP_VERSION}")
    app.geometry("1320x860")
    app.minsize(1080, 680)
    style = ttk.Style(app)
    try:
        style.theme_use("vista" if sys.platform.startswith("win") else "clam")
    except tk.TclError:
        pass

    notebook = ttk.Notebook(app)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)
    start = ttk.Frame(notebook)
    tests = ttk.Frame(notebook)
    expectations = ttk.Frame(notebook)
    results = ttk.Frame(notebook)
    notebook.add(start, text="Start")
    notebook.add(tests, text="Testy")
    notebook.add(expectations, text="Oczekiwania")
    notebook.add(results, text="Wyniki")
    settings_page = ttk.Frame(notebook)
    diagnostics_page = ttk.Frame(notebook)
    notebook.add(settings_page, text="Ustawienia")
    notebook.add(diagnostics_page, text="Diagnostyka")

    def text_with_scrollbars(parent, *, wrap: Literal["none", "char", "word"] = "none"):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        widget = tk.Text(frame, wrap=wrap)
        ybar = ttk.Scrollbar(frame, orient="vertical", command=widget.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=widget.xview)
        widget.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        widget.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        return widget

    shell_settings = load_ui_settings(root)
    settings_page.columnconfigure(1, weight=1)
    ttk.Label(settings_page, text="Ustawienia interfejsu", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 12))
    ui_mode_var = tk.StringVar(value=shell_settings.ui_mode)
    splash_var = tk.BooleanVar(value=shell_settings.splash_enabled)
    diagnostics_var = tk.BooleanVar(value=shell_settings.diagnostics_enabled)
    log_level_var = tk.StringVar(value=shell_settings.log_level)
    ttk.Label(settings_page, text="Domyślny tryb").grid(row=1, column=0, sticky="w", padx=16, pady=6)
    ttk.Combobox(settings_page, textvariable=ui_mode_var, values=("text", "tui", "window"), state="readonly", width=20).grid(row=1, column=1, sticky="w", padx=8, pady=6)
    ttk.Checkbutton(settings_page, text="Pokazuj splashscreen podczas dłuższego startu", variable=splash_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=6)
    ttk.Checkbutton(settings_page, text="Włącz zapis diagnostyki i logów", variable=diagnostics_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=16, pady=6)
    ttk.Label(settings_page, text="Poziom logów").grid(row=4, column=0, sticky="w", padx=16, pady=6)
    ttk.Combobox(settings_page, textvariable=log_level_var, values=("DEBUG", "INFO", "WARNING", "ERROR"), state="readonly", width=20).grid(row=4, column=1, sticky="w", padx=8, pady=6)
    ttk.Label(settings_page, text=f"Plik diagnostyczny: {diagnostics.log_path}", wraplength=900).grid(row=5, column=0, columnspan=2, sticky="w", padx=16, pady=(10, 6))

    def save_shell_settings_from_window() -> None:
        nonlocal shell_settings
        shell_settings = save_ui_settings(
            root,
            ShellSettings(
                ui_mode=ui_mode_var.get(),
                splash_enabled=bool(splash_var.get()),
                diagnostics_enabled=bool(diagnostics_var.get()),
                diagnostics_limit=shell_settings.diagnostics_limit,
                log_level=log_level_var.get(),
            ),
        )
        diagnostics.reconfigure(
            enabled=shell_settings.diagnostics_enabled,
            limit=shell_settings.diagnostics_limit,
            minimum_level=shell_settings.log_level,
        )
        diagnostics.record("INFO", "Zapisano ustawienia aplikacji", ui_mode=shell_settings.ui_mode)
        messagebox.showinfo(APP_NAME, "Ustawienia zapisane.", parent=app)

    ttk.Button(settings_page, text="Zapisz ustawienia", command=save_shell_settings_from_window).grid(row=6, column=0, columnspan=2, sticky="w", padx=16, pady=16)

    diagnostics_text = text_with_scrollbars(diagnostics_page, wrap="none")
    diagnostics_text.configure(state="disabled")

    info = text_with_scrollbars(start, wrap="word")
    info.insert(
        "1.0",
        json.dumps(audit(root), indent=2, ensure_ascii=False)
        + "\n\ncurrent = aktywny kontrakt techniczny; sens może wymagać recenzji.\n"
        + "Run-all działa w osobnym wątku i pokazuje bieżący test oraz wynik na żywo.",
    )
    info.configure(state="disabled")

    tests.rowconfigure(1, weight=1)
    tests.columnconfigure(0, weight=1)
    top = ttk.Frame(tests)
    top.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
    search_var = tk.StringVar()
    status_var = tk.StringVar(value="all")
    ttk.Label(top, text="Szukaj:").pack(side="left", padx=(0, 4))
    ttk.Entry(top, textvariable=search_var, width=48).pack(side="left", padx=4)
    ttk.Label(top, text="Status:").pack(side="left", padx=(12, 4))
    ttk.Combobox(
        top,
        textvariable=status_var,
        values=["all", *sorted(VALID_REVIEW)],
        state="readonly",
        width=18,
    ).pack(side="left", padx=4)

    tree_frame = ttk.Frame(tests)
    tree_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
    tree_frame.rowconfigure(0, weight=1)
    tree_frame.columnconfigure(0, weight=1)
    tree = ttk.Treeview(tree_frame, columns=("status", "category", "purpose"), show="tree headings")
    tree.heading("#0", text="Nodeid")
    tree.heading("status", text="Status")
    tree.heading("category", text="Kategoria")
    tree.heading("purpose", text="Cel")
    tree.column("#0", width=500, minwidth=250)
    tree.column("status", width=120, minwidth=90)
    tree.column("category", width=120, minwidth=90)
    tree.column("purpose", width=620, minwidth=300)
    tree_y = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)
    tree.grid(row=0, column=0, sticky="nsew")
    tree_y.grid(row=0, column=1, sticky="ns")
    tree_x.grid(row=1, column=0, sticky="ew")

    buttons = ttk.Frame(tests)
    buttons.grid(row=2, column=0, sticky="ew", padx=8, pady=8)

    detail = text_with_scrollbars(expectations, wrap="none")

    results.rowconfigure(2, weight=1)
    results.columnconfigure(0, weight=1)
    summary = ttk.Frame(results)
    summary.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
    run_state_var = tk.StringVar(value="GOTOWE")
    current_var = tk.StringVar(value="—")
    progress_text_var = tk.StringVar(value="0 / 0 (0%)")
    ttk.Label(summary, text="Stan:").grid(row=0, column=0, sticky="w")
    ttk.Label(summary, textvariable=run_state_var).grid(row=0, column=1, sticky="w", padx=(4, 18))
    ttk.Label(summary, text="Bieżący test:").grid(row=0, column=2, sticky="w")
    ttk.Label(summary, textvariable=current_var).grid(row=0, column=3, sticky="ew", padx=4)
    summary.columnconfigure(3, weight=1)
    ttk.Label(summary, textvariable=progress_text_var).grid(row=0, column=4, sticky="e")

    progress = ttk.Progressbar(results, orient="horizontal", mode="determinate", maximum=1)
    progress.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

    result_pane = ttk.Panedwindow(results, orient="vertical")
    result_pane.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
    status_frame = ttk.Frame(result_pane)
    log_frame = ttk.Frame(result_pane)
    result_pane.add(status_frame, weight=3)
    result_pane.add(log_frame, weight=2)

    status_frame.rowconfigure(1, weight=1)
    status_frame.columnconfigure(0, weight=1)
    counters_frame = ttk.Frame(status_frame)
    counters_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    counter_vars = {name: tk.StringVar(value="0") for name in ("CORRECT", "FAIL", "ERROR", "SKIP", "XFAIL", "XPASS")}
    for col, name in enumerate(counter_vars):
        ttk.Label(counters_frame, text=f"{name}:").grid(row=0, column=col * 2, padx=(0, 3))
        ttk.Label(counters_frame, textvariable=counter_vars[name]).grid(row=0, column=col * 2 + 1, padx=(0, 14))

    status_tree = ttk.Treeview(status_frame, columns=("status", "duration", "nodeid"), show="headings")
    status_tree.heading("status", text="Wynik")
    status_tree.heading("duration", text="Czas [s]")
    status_tree.heading("nodeid", text="Test")
    status_tree.column("status", width=100, minwidth=80)
    status_tree.column("duration", width=95, minwidth=75)
    status_tree.column("nodeid", width=980, minwidth=420)
    status_y = ttk.Scrollbar(status_frame, orient="vertical", command=status_tree.yview)
    status_x = ttk.Scrollbar(status_frame, orient="horizontal", command=status_tree.xview)
    status_tree.configure(yscrollcommand=status_y.set, xscrollcommand=status_x.set)
    status_tree.grid(row=1, column=0, sticky="nsew")
    status_y.grid(row=1, column=1, sticky="ns")
    status_x.grid(row=2, column=0, sticky="ew")

    log_frame.rowconfigure(0, weight=1)
    log_frame.columnconfigure(0, weight=1)
    result_text = tk.Text(log_frame, wrap="none")
    log_y = ttk.Scrollbar(log_frame, orient="vertical", command=result_text.yview)
    log_x = ttk.Scrollbar(log_frame, orient="horizontal", command=result_text.xview)
    result_text.configure(yscrollcommand=log_y.set, xscrollcommand=log_x.set)
    result_text.grid(row=0, column=0, sticky="nsew")
    log_y.grid(row=0, column=1, sticky="ns")
    log_x.grid(row=1, column=0, sticky="ew")

    result_buttons = ttk.Frame(results)
    result_buttons.grid(row=3, column=0, sticky="ew", padx=8, pady=8)
    stop_button = ttk.Button(result_buttons, text="Zatrzymaj", state="disabled")
    stop_button.pack(side="left", padx=4)
    ttk.Button(
        result_buttons,
        text="Wyczyść wyniki",
        command=lambda: (status_tree.delete(*status_tree.get_children()), result_text.delete("1.0", "end")),
    ).pack(side="left", padx=4)

    event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    active_run: PytestRun | None = None
    totals = {"total": 0, "completed": 0}
    counts = {key: 0 for key in counter_vars}

    def selected() -> str | None:
        sel = tree.selection()
        return sel[0] if sel else None

    def refresh(*_args) -> None:
        for iid in tree.get_children():
            tree.delete(iid)
        for nodeid, item in filtered(root, search_var.get(), status_var.get()):
            tree.insert(
                "",
                "end",
                iid=nodeid,
                text=nodeid,
                values=(item.get("status"), item.get("category"), item.get("purpose")),
            )

    def show_detail(*_args) -> None:
        nodeid = selected()
        if not nodeid:
            return
        detail.delete("1.0", "end")
        detail.insert("1.0", json.dumps(effective_contract(root, nodeid), indent=2, ensure_ascii=False))
        notebook.select(expectations)

    def append_log(text: str) -> None:
        if not text:
            return
        result_text.insert("end", text)
        result_text.see("end")

    def reset_run_view() -> None:
        nonlocal totals, counts
        status_tree.delete(*status_tree.get_children())
        result_text.delete("1.0", "end")
        totals = {"total": 0, "completed": 0}
        counts = {key: 0 for key in counter_vars}
        for name, var in counter_vars.items():
            var.set("0")
        progress.configure(maximum=1, value=0)
        progress_text_var.set("0 / 0 (0%)")
        current_var.set("—")

    def set_running_controls(running: bool) -> None:
        state = "disabled" if running else "normal"
        run_one_button.configure(state=state)
        run_all_button.configure(state=state)
        stop_button.configure(state="normal" if running else "disabled")

    def handle_event(event: dict[str, Any]) -> None:
        nonlocal active_run
        kind = event.get("type")
        diagnostics.record("DEBUG", "pytest-event", event_type=kind, nodeid=event.get("nodeid"), status=event.get("status"))
        if kind == "process_start":
            run_state_var.set("RUNNING")
            append_log("START: " + " ".join(event.get("command", [])) + "\n")
        elif kind == "collection":
            totals["total"] = int(event.get("total") or 0)
            progress.configure(maximum=max(1, totals["total"]))
            progress_text_var.set(f"0 / {totals['total']} (0%)")
        elif kind == "start":
            current_var.set(str(event.get("nodeid") or "—"))
        elif kind == "result":
            totals["completed"] = int(event.get("completed") or totals["completed"] + 1)
            totals["total"] = int(event.get("total") or totals["total"])
            raw_status = str(event.get("status") or "ERROR")
            shown = UI_STATUS.get(raw_status, raw_status)
            if shown not in counts:
                shown = "ERROR"
            counts[shown] += 1
            counter_vars[shown].set(str(counts[shown]))
            percent = float(event.get("percent") or 0.0)
            progress.configure(maximum=max(1, totals["total"]), value=totals["completed"])
            progress_text_var.set(f"{totals['completed']} / {totals['total']} ({percent:.1f}%)")
            iid = f"{totals['completed']:06d}"
            status_tree.insert(
                "",
                "end",
                iid=iid,
                values=(shown, f"{float(event.get('duration') or 0.0):.3f}", event.get("nodeid", "")),
            )
            status_tree.see(iid)
        elif kind == "output":
            append_log(str(event.get("text") or ""))
        elif kind == "finished":
            outcome = str(event.get("outcome") or "error")
            if outcome == "passed":
                run_state_var.set("CORRECT")
            elif outcome == "failed":
                run_state_var.set("FAIL")
            elif outcome == "cancelled":
                run_state_var.set("CANCELLED")
            elif outcome == "timeout":
                run_state_var.set("TIMEOUT")
            else:
                run_state_var.set("ERROR")
            current_var.set("—")
            append_log("\nFINAL:\n" + json.dumps(event, indent=2, ensure_ascii=False) + "\n")
            set_running_controls(False)
            active_run = None

    def poll_events() -> None:
        drained = False
        while True:
            try:
                event = event_queue.get_nowait()
            except queue.Empty:
                break
            drained = True
            handle_event(event)
        if active_run is not None or drained:
            app.after(50, poll_events)

    def start_run(nodeids: list[str] | None) -> None:
        nonlocal active_run
        if active_run is not None:
            messagebox.showinfo(APP_NAME, "Testy już są uruchomione.")
            return
        reset_run_view()
        notebook.select(results)
        run_state_var.set("STARTING")
        set_running_controls(True)
        diagnostics.record("INFO", "Uruchomiono pytest", scope="selected" if nodeids else "all", nodeids=nodeids or [])
        active_run = PytestRun(root, nodeids, timeout=1800, on_event=event_queue.put).start()
        app.after(25, poll_events)

    def run_one() -> None:
        nodeid = selected()
        if nodeid:
            start_run([nodeid])

    def run_all() -> None:
        if messagebox.askyesno(APP_NAME, "Uruchomić cały aktywny zestaw testów?"):
            start_run(None)

    def stop_run() -> None:
        if active_run is not None and messagebox.askyesno(APP_NAME, "Zatrzymać bieżący przebieg testów?"):
            run_state_var.set("STOPPING")
            active_run.stop()

    stop_button.configure(command=stop_run)

    def review_dialog() -> None:
        nodeid = selected()
        if not nodeid:
            return
        item = effective_contract(root, nodeid)
        win = tk.Toplevel(app)
        win.title("Recenzja kontraktu")
        win.geometry("720x500")
        status = tk.StringVar(value=item.get("status", "current"))
        purpose = tk.StringVar(value=item.get("purpose", ""))
        expected = tk.StringVar(value=item.get("expected", ""))
        ttk.Label(win, text=nodeid, wraplength=680).pack(anchor="w", padx=10, pady=8)
        ttk.Combobox(win, textvariable=status, values=sorted(VALID_REVIEW), state="readonly").pack(fill="x", padx=10, pady=4)
        ttk.Label(win, text="Purpose").pack(anchor="w", padx=10)
        ttk.Entry(win, textvariable=purpose).pack(fill="x", padx=10)
        ttk.Label(win, text="Expected").pack(anchor="w", padx=10)
        ttk.Entry(win, textvariable=expected).pack(fill="x", padx=10)
        notes_frame = ttk.Frame(win)
        notes_frame.pack(fill="both", expand=True, padx=10, pady=6)
        notes_frame.rowconfigure(0, weight=1)
        notes_frame.columnconfigure(0, weight=1)
        notes = tk.Text(notes_frame, wrap="word")
        notes_y = ttk.Scrollbar(notes_frame, orient="vertical", command=notes.yview)
        notes.configure(yscrollcommand=notes_y.set)
        notes.grid(row=0, column=0, sticky="nsew")
        notes_y.grid(row=0, column=1, sticky="ns")
        notes.insert("1.0", str(item.get("notes") or ""))

        def save() -> None:
            set_review(
                root,
                nodeid,
                status.get(),
                purpose.get(),
                expected.get(),
                notes.get("1.0", "end").strip(),
            )
            win.destroy()
            refresh()

        ttk.Button(win, text="Zapisz", command=save).pack(pady=8)

    ttk.Button(buttons, text="Odśwież", command=refresh).pack(side="left", padx=4)
    ttk.Button(buttons, text="Szczegóły", command=show_detail).pack(side="left", padx=4)
    run_one_button = ttk.Button(buttons, text="Uruchom wybrany", command=run_one)
    run_one_button.pack(side="left", padx=4)
    ttk.Button(buttons, text="Recenzja", command=review_dialog).pack(side="left", padx=4)
    run_all_button = ttk.Button(buttons, text="Uruchom wszystkie", command=run_all)
    run_all_button.pack(side="right", padx=4)

    def refresh_diagnostics() -> None:
        if not app.winfo_exists():
            return
        if diagnostics_var.get():
            diagnostics_text.configure(state="normal")
            diagnostics_text.delete("1.0", "end")
            diagnostics_text.insert("1.0", diagnostics.text(limit=200))
            diagnostics_text.configure(state="disabled")
            diagnostics_text.see("end")
        app.after(500, refresh_diagnostics)

    def close_app() -> None:
        nonlocal active_run
        if active_run is not None:
            active_run.stop()
            active_run = None
        diagnostics.record("INFO", "Zamknięto okno Test Studio")
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", close_app)
    search_var.trace_add("write", refresh)
    status_var.trace_add("write", refresh)
    tree.bind("<Double-1>", show_detail)
    refresh()
    diagnostics.record("INFO", "Uruchomiono okno Test Studio")
    refresh_diagnostics()
    try:
        app.mainloop()
        return 0
    except KeyboardInterrupt:
        close_app()
        return 130
