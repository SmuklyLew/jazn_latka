#!/usr/bin/env python3
"""Professional, read-only-first Tk dashboard for Jaźń Start Studio.

GUI never starts services in the background. Health refresh does not call MCP tools.
Workers publish immutable results through a queue; only Tk's main thread renders.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any, TYPE_CHECKING
from urllib.error import URLError
from urllib.request import urlopen

if TYPE_CHECKING:
    from tools.jazn_start_studio import StudioCore

PALETTE = {
    "navy": "#142233",
    "navy_2": "#20354c",
    "accent": "#147d85",
    "paper": "#f3f6fa",
    "surface": "#ffffff",
    "text": "#192b3e",
    "muted": "#627184",
    "line": "#dbe3ea",
    "ok": "#176e52",
    "warning": "#9a6700",
    "error": "#a53236",
}
DESCRIPTIONS = {
    "jazn_status": "Odczytaj tożsamość istniejącego daemona i zestaw z wersją kodu.",
    "jazn_preflight": "Sprawdź możliwości aktualnego procesu hosta (nie oznacza gotowości rozmowy).",
    "jazn_start": "Uruchom tylko wtedy, gdy nie działa już daemon. Nie wykonuje restartu.",
    "jazn_adapter": "Pokaż skonfigurowany model i adapter wybrany dla kanału tej komendy.",
    "jazn_memory": "Odczytaj stan sidecara normalizacji; bez ingerencji w bazę.",
    "jazn_wake": "Odczytaj stan utrwalonej ciągłości wake-state.",
    "jazn_archive": "Odczytaj stan archiwum rozmów.",
    "jazn_route": "Odczytaj konfigurację routingu LLM.",
    "ollama_api": "Sprawdź API Ollamy i nazwy dostępnych modeli.",
    "ollama_generate": "Wywołaj niewielką testową generację przez API Ollamy.",
    "ollama_models": "Wyświetl modele przez oficjalne CLI ollama list.",
    "ollama_serve": "Uruchom serwer Ollamy wyłącznie, gdy lokalny port jest wolny.",
    "ollama_app": "Uruchom aplikację Ollama Windows wyłącznie, gdy API nie odpowiada.",
    "ollama_log": "Śledź plik logu serwera Ollamy bez zatrzymywania serwera.",
    "ollama_app_log": "Śledź plik logu aplikacji Ollama bez zatrzymywania aplikacji.",
    "mcp_help": "Pokaż parametry lokalnego punktu wejścia MCP.",
    "mcp_probe": "Osobna tymczasowa sesja MCP: lista narzędzi, bez wykonywania rozmowy.",
}


@dataclass(frozen=True)
class HealthItem:
    title: str
    state: str
    detail: str


@dataclass(frozen=True)
class HealthSnapshot:
    checked_at: float
    items: tuple[HealthItem, ...]
    note: str = ""


def summarize_daemon(data: dict[str, Any]) -> HealthItem:
    daemon = data.get("daemon")
    if not isinstance(daemon, dict):
        return HealthItem("Jaźń / daemon", "unknown", "Brak sekcji daemon w statusie")
    trusted = (
        daemon.get("active_state") == "active_trusted"
        and daemon.get("endpoint_identity_matches") is True
        and daemon.get("endpoint_heartbeat_fresh") is True
        and daemon.get("endpoint_reachable") is True
    )
    marker = daemon.get("marker")
    marker = marker if isinstance(marker, dict) else {}
    active = marker.get("runtime_version_full") or daemon.get("runtime_version_full")
    current = data.get("runtime_version_full") or data.get("runtime_version")
    pid = None
    jobs = marker.get("daemon_chat_jobs")
    if isinstance(jobs, dict):
        pid = jobs.get("pid")
    label = f"PID {pid}" if pid else "PID nieznany"
    if active and current and str(active) != str(current):
        label += " • wersje różne"
    if trusted:
        return HealthItem("Jaźń / daemon", "ready", label + " • tożsamość potwierdzona")
    if daemon.get("endpoint_reachable") is True:
        return HealthItem("Jaźń / daemon", "warning", label + " • tożsamość niepotwierdzona")
    return HealthItem("Jaźń / daemon", "unknown", "Brak potwierdzenia żywej instancji")


def summarize_memory(data: dict[str, Any]) -> HealthItem:
    caps = data.get("capability_readiness")
    if not isinstance(caps, dict):
        return HealthItem("Pamięć", "unknown", "Brak danych o pełnej gotowości")
    recall = caps.get("full_autobiographical_recall_ready")
    continuity = caps.get("continuity_ready")
    if recall is True and continuity is True:
        return HealthItem("Pamięć", "ready", "Recall i ciągłość potwierdzone")
    if recall is False or continuity is False:
        return HealthItem("Pamięć", "warning", "Pełny recall lub ciągłość niedostępne")
    return HealthItem("Pamięć", "unknown", "Brak pełnego odczytu zdolności")


def summarize_mcp(data: dict[str, Any]) -> HealthItem:
    matrix = data.get("capability_matrix")
    if isinstance(matrix, dict):
        components = matrix.get("components")
        if isinstance(components, dict):
            transport = components.get("remote_transport")
            if isinstance(transport, dict):
                if transport.get("available") is True:
                    return HealthItem("MCP / ChatGPT", "warning", "Transport zgłoszony; tura niezweryfikowana")
                if transport.get("available") is False:
                    return HealthItem("MCP / ChatGPT", "unknown", "Brak dowodu połączenia z ChatGPT")
    return HealthItem("MCP / ChatGPT", "unknown", "Brak potwierdzenia zdalnego hosta")


def summarize_ollama(tags: dict[str, Any] | None, error: str | None = None) -> HealthItem:
    if error:
        return HealthItem("Ollama", "unknown", "API nie odpowiada: " + error[:100])
    if not isinstance(tags, dict) or not isinstance(tags.get("models"), list):
        return HealthItem("Ollama", "unknown", "Niepoprawna odpowiedź API /api/tags")
    models = [
        str(item.get("name")) for item in tags["models"]
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    if not models:
        return HealthItem("Ollama", "warning", "API działa, brak zarejestrowanych modeli")
    return HealthItem("Ollama", "ready", f"API odpowiada • {len(models)} modeli • " + ", ".join(models[:2]))


def read_health(core: StudioCore) -> HealthSnapshot:
    from tools.jazn_start_studio import http_json

    data: dict[str, Any] = {}
    problem = ""
    try:
        proc = subprocess.run(
            [core.python, "-X", "utf8", str(core.root / "run.py"), "status", "--json"],
            cwd=str(core.root), capture_output=True, text=True, encoding="utf-8",
            errors="replace", shell=False, timeout=25, check=False,
        )
        if proc.returncode == 0:
            result = json.loads(proc.stdout)
            if isinstance(result, dict):
                data = result
            else:
                problem = "Nieprawidłowy format statusu"
        else:
            problem = f"Status Jaźni zakończył się kodem {proc.returncode}"
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        problem = type(exc).__name__

    try:
        tags = http_json("/api/tags", timeout=3)
        ollama = summarize_ollama(tags)
    except (OSError, ValueError, RuntimeError, URLError) as exc:
        ollama = summarize_ollama(None, type(exc).__name__)

    if data:
        runtime = summarize_daemon(data)
        memory = summarize_memory(data)
        mcp = summarize_mcp(data)
    else:
        runtime = HealthItem("Jaźń / daemon", "unknown", problem or "Status niedostępny")
        memory = HealthItem("Pamięć", "unknown", "Odczyt Jaźni niedostępny")
        mcp = HealthItem("MCP / ChatGPT", "unknown", "Odczyt Jaźni niedostępny")
    return HealthSnapshot(
        checked_at=time.time(),
        items=(runtime, ollama, memory, mcp),
        note="Status bieżących usług • brak testu finalizacji wiadomości",
    )


def launch(core: StudioCore) -> int:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from tkinter.scrolledtext import ScrolledText
    from tools.jazn_start_studio import TASKS, TASK_INDEX, STUDIO_VERSION, safe_line

    root = tk.Tk()
    root.title(f"Jaźń — Studio Startu {STUDIO_VERSION}")
    root.geometry("1230x790")
    root.minsize(950, 650)
    root.configure(bg=PALETTE["paper"])

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10))
    style.configure("Treeview", rowheight=30, background=PALETTE["surface"],
                    foreground=PALETTE["text"], fieldbackground=PALETTE["surface"],
                    borderwidth=0)
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"),
                    background=PALETTE["paper"], foreground=PALETTE["navy"],
                    relief="flat", padding=7)
    style.map("Treeview", background=[("selected", "#d9eef1")],
              foreground=[("selected", PALETTE["navy"])])
    style.configure("TNotebook", background=PALETTE["paper"], borderwidth=0)
    style.configure("TNotebook.Tab", padding=(18, 9), font=("Segoe UI", 10))
    style.configure("Accent.TButton", padding=(14, 8), foreground="white",
                    background=PALETTE["accent"])
    style.map("Accent.TButton", background=[("active", "#086b73")])
    style.configure("TButton", padding=(10, 8))
    style.configure("Header.TLabel", background=PALETTE["navy"], foreground="white")

    header = tk.Frame(root, bg=PALETTE["navy"], height=93)
    header.pack(fill="x")
    header.pack_propagate(False)
    title_stack = tk.Frame(header, bg=PALETTE["navy"])
    title_stack.pack(side="left", padx=24, pady=14)
    tk.Label(title_stack, text="JAŹŃ  /  STUDIO STARTU",
             bg=PALETTE["navy"], fg="white", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    tk.Label(title_stack, text=f"Centrum operatorskie  •  {STUDIO_VERSION}  •  Windows / Linux",
             bg=PALETTE["navy"], fg="#adbfce", font=("Segoe UI", 10)).pack(anchor="w")
    refresh_button = ttk.Button(header, text="Odśwież diagnostykę", style="Accent.TButton")
    refresh_button.pack(side="right", padx=26, pady=25)

    content = ttk.Frame(root, padding=(20, 17))
    content.pack(fill="both", expand=True)
    notebook = ttk.Notebook(content)
    notebook.pack(fill="both", expand=True)

    dashboard = ttk.Frame(notebook, padding=(9, 14))
    tasks_page = ttk.Frame(notebook, padding=(9, 14))
    notebook.add(dashboard, text="   Pulpit stanu   ")
    notebook.add(tasks_page, text="   Zadania i logi   ")

    intro = ttk.Frame(dashboard)
    intro.pack(fill="x")
    ttk.Label(intro, text="Stan środowiska", font=("Segoe UI", 15, "bold")).pack(side="left")
    checked = tk.StringVar(value="Oczekiwanie na pierwszą diagnostykę")
    ttk.Label(intro, textvariable=checked, foreground=PALETTE["muted"]).pack(side="right")

    cards_frame = tk.Frame(dashboard, bg=PALETTE["paper"])
    cards_frame.pack(fill="x", pady=(16, 10))
    cards: dict[str, tuple[tk.Label, tk.Label]] = {}
    for index, heading in enumerate(("Jaźń / daemon", "Ollama", "Pamięć", "MCP / ChatGPT")):
        column = tk.Frame(cards_frame, bg="white", highlightbackground=PALETTE["line"],
                          highlightthickness=1)
        column.grid(row=0, column=index, sticky="nsew", padx=5, ipadx=5, ipady=5)
        cards_frame.grid_columnconfigure(index, weight=1, uniform="cards")
        tk.Label(column, text=heading.upper(), font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["muted"], bg="white").pack(anchor="w", padx=13, pady=(12, 5))
        state = tk.Label(column, text="NIEZWERYFIKOWANE", bg="white",
                         fg=PALETTE["warning"], font=("Segoe UI", 11, "bold"))
        state.pack(anchor="w", padx=13)
        detail = tk.Label(column, text="Oczekiwanie na odczyt",
                          wraplength=210, justify="left", bg="white", fg=PALETTE["muted"],
                          font=("Segoe UI", 9))
        detail.pack(anchor="w", padx=13, pady=(5, 12))
        cards[heading] = (state, detail)

    notice = tk.Frame(dashboard, bg="#e9f2f5", highlightbackground="#c5dfe5",
                      highlightthickness=1)
    notice.pack(fill="x", pady=(9, 14))
    tk.Label(notice, text="Granice weryfikacji",
             bg="#e9f2f5", fg=PALETTE["navy"], font=("Segoe UI", 11, "bold")
             ).pack(anchor="w", padx=15, pady=(11, 4))
    tk.Label(notice,
             text="Otwarty port i gotowość daemona nie potwierdzają jeszcze aktywnej rozmowy z Łatką. "
                  "Test MCP sprawdza tylko katalog narzędzi. Studio nie uruchamia niczego bez Twojego polecenia.",
             bg="#e9f2f5", fg=PALETTE["text"], font=("Segoe UI", 10),
             wraplength=1040, justify="left").pack(anchor="w", padx=15, pady=(0, 12))
    status_summary = ttk.LabelFrame(dashboard, text="Ostatnia aktywność Studio", padding=12)
    status_summary.pack(fill="both", expand=True)
    summary = ScrolledText(status_summary, height=12, bg=PALETTE["surface"],
                           fg=PALETTE["text"], font=("Consolas", 9), relief="flat",
                           wrap="word", state="disabled")
    summary.pack(fill="both", expand=True)

    ttk.Label(tasks_page, text="Zadania i procesy", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    ttk.Label(tasks_page, text="Stan zadania jest niezależny od stanu usługi. Dwa kliknięcia otwierają logi.",
              foreground=PALETTE["muted"]).pack(anchor="w", pady=(4, 12))
    columns = ("group", "title", "state")
    tree = ttk.Treeview(tasks_page, columns=columns, show="headings", selectmode="browse", height=11)
    for column, title, width in (("group", "Moduł", 130), ("title", "Zadanie", 500),
                                  ("state", "Stan wykonania", 290)):
        tree.heading(column, text=title)
        tree.column(column, width=width, minwidth=100, stretch=column != "group")
    tree.pack(fill="both", expand=True)
    for task in TASKS:
        tree.insert("", "end", iid=task.key,
                    values=(task.group, task.title, "Nieuruchomiony"))
    details = ttk.Frame(tasks_page, padding=(0, 11))
    details.pack(fill="x")
    detail_title = tk.StringVar(value="Wybierz zadanie z listy")
    detail_desc = tk.StringVar(value="Każda operacja jest uruchamiana wyłącznie na żądanie.")
    ttk.Label(details, textvariable=detail_title, font=("Segoe UI", 11, "bold")).pack(anchor="w")
    ttk.Label(details, textvariable=detail_desc, foreground=PALETTE["muted"],
              wraplength=1050).pack(anchor="w", pady=(3, 0))
    commands = ttk.Frame(tasks_page, padding=(0, 9))
    commands.pack(fill="x")
    btn_start = ttk.Button(commands, text="Uruchom zadanie", style="Accent.TButton")
    btn_stop = ttk.Button(commands, text="Zatrzymaj własny proces")
    btn_log = ttk.Button(commands, text="Otwórz pełny log")
    btn_start.pack(side="left", padx=(0, 8))
    btn_stop.pack(side="left", padx=(0, 8))
    btn_log.pack(side="left", padx=(0, 8))

    panes: dict[str, tuple[tk.Toplevel, ScrolledText]] = {}
    latest_event = tk.StringVar(value="Brak aktywności")
    ttk.Label(root, textvariable=latest_event, anchor="w", padding=(22, 7),
              foreground=PALETTE["muted"]).pack(fill="x")

    def selected() -> str | None:
        ids = tree.selection()
        return ids[0] if ids else None

    def task_selected(_event=None) -> None:
        key = selected()
        if key:
            task = TASK_INDEX[key]
            detail_title.set(task.title)
            detail_desc.set(DESCRIPTIONS.get(key, task.key))
        else:
            detail_title.set("Wybierz zadanie z listy")
            detail_desc.set("")

    def put_scrolled(widget: ScrolledText, text: str) -> None:
        widget.configure(state="normal")
        widget.insert("end", text + "\n")
        # Protect the UI from indefinitely growing text widgets.
        if int(widget.index("end-1c").split(".")[0]) > 2200:
            widget.delete("1.0", "250.0")
        widget.see("end")
        widget.configure(state="disabled")

    def open_log(key: str) -> None:
        existing = panes.get(key)
        if existing:
            existing[0].deiconify()
            existing[0].lift()
            return
        win = tk.Toplevel(root)
        win.title("Jaźń — log: " + TASK_INDEX[key].title)
        win.geometry("970x610")
        win.minsize(700, 400)
        toolbar = ttk.Frame(win, padding=11)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text=TASK_INDEX[key].title,
                  font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(toolbar, text="Uruchom", command=lambda: start_task(key)).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Zatrzymaj", command=lambda: stop_task(key)).pack(side="right", padx=4)

        log_widget = ScrolledText(win, font=("Consolas", 10), bg=PALETTE["navy"],
                                  fg="#d8e8ed", insertbackground="white", relief="flat",
                                  padx=12, pady=12, wrap="word", state="disabled")
        log_widget.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        for line in list(core.logs[key]):
            put_scrolled(log_widget, line)

        def export() -> None:
            path = filedialog.asksaveasfilename(
                parent=win, defaultextension=".log",
                filetypes=[("Log", "*.log"), ("Tekst", "*.txt")])
            if path:
                try:
                    Path(path).write_text("\n".join(core.logs[key]) + "\n", encoding="utf-8")
                except OSError as exc:
                    messagebox.showerror("Błąd zapisu", safe_line(str(exc)), parent=win)
        ttk.Button(toolbar, text="Zapisz log", command=export).pack(side="right", padx=4)
        panes[key] = (win, log_widget)
        win.protocol("WM_DELETE_WINDOW", win.withdraw)

    def show_selected_log() -> None:
        key = selected()
        if key:
            open_log(key)

    def start_task(key: str | None = None) -> None:
        key = key or selected()
        if key is None:
            return
        open_log(key)
        try:
            core.start(key)
        except (OSError, KeyError, RuntimeError) as exc:
            messagebox.showerror("Nie uruchomiono", safe_line(str(exc)), parent=root)

    def stop_task(key: str | None = None) -> None:
        key = key or selected()
        if not key:
            return
        if messagebox.askyesno(
            "Zatrzymaj zadanie", f"Zatrzymać tylko proces utworzony przez Studio dla {key}?\n"
            "Nie zatrzyma to istniejącego daemona Jaźni.",
            parent=root,
        ):
            core.stop(key)

    btn_start.configure(command=start_task)
    btn_stop.configure(command=stop_task)
    btn_log.configure(command=show_selected_log)
    tree.bind("<<TreeviewSelect>>", task_selected)
    tree.bind("<Double-1>", lambda _e: show_selected_log())

    reports: queue.Queue[HealthSnapshot] = queue.Queue(maxsize=2)
    refresh_lock = threading.Lock()
    refresh_state = {"in_flight": False, "last": 0.0}

    def run_health_worker() -> None:
        try:
            snapshot = read_health(core)
            try:
                reports.put_nowait(snapshot)
            except queue.Full:
                pass
        finally:
            with refresh_lock:
                refresh_state["in_flight"] = False

    def refresh_health() -> None:
        with refresh_lock:
            if refresh_state["in_flight"]:
                return
            refresh_state["in_flight"] = True
            refresh_state["last"] = time.monotonic()
        checked.set("Odczytywanie diagnostyki...")
        threading.Thread(target=run_health_worker, daemon=True).start()

    refresh_button.configure(command=refresh_health)

    def drain() -> None:
        # Limit processing time; keep Tk responsive under heavy log output.
        for _ in range(150):
            try:
                key, channel, line = core.events.get_nowait()
            except queue.Empty:
                break
            if key in TASK_INDEX:
                tree.set(key, "state", core.states[key].status)
            put_scrolled(summary, f"{TASK_INDEX[key].group if key in TASK_INDEX else key}: {line}")
            latest_event.set("Ostatnie zdarzenie: " + channel + " • " + key)
            if key in panes:
                put_scrolled(panes[key][1], line)
        try:
            snapshot = reports.get_nowait()
        except queue.Empty:
            pass
        else:
            checked.set("Odczyt: " + time.strftime("%H:%M:%S", time.localtime(snapshot.checked_at)))
            for item in snapshot.items:
                state_label, details = cards[item.title]
                txt, color = {
                    "ready": ("DZIAŁA", PALETTE["ok"]),
                    "warning": ("WYMAGA UWAGI", PALETTE["warning"]),
                    "error": ("BŁĄD", PALETTE["error"]),
                }.get(item.state, ("NIEZWERYFIKOWANE", PALETTE["muted"]))
                state_label.configure(text=txt, fg=color)
                details.configure(text=item.detail)
        if time.monotonic() - refresh_state["last"] > 30:
            refresh_health()
        root.after(120, drain)

    def on_close() -> None:
        active = core.active()
        if active:
            messagebox.showwarning(
                "Aktywne zadania Studio",
                "Najpierw zatrzymaj zadania uruchomione w Studiu:\n"
                + ", ".join(active)
                + "\nNie podejmuję próby zatrzymania zewnętrznych usług.",
                parent=root,
            )
            return
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(70, drain)
    root.after(150, refresh_health)
    root.mainloop()
    return 0
