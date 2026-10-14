"""Desktop Jaźń Studio — one operator UI, canonical Jaźń tools.

Tk is accessed only on the GUI thread; probes and Git calls run in workers.
No call generates a user turn or edits private MEMORY/SQLite.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from .core import (
    STUDIO_VERSION, StudioError, StudioSettings,
    apply_fast_forward, fetch_updates, load_settings, probe_http,
    run_diagnostic, safe_launcher, studio_snapshot, update_plan,
)

BG = "#f3f7fa"
INK = "#193348"
SIDEBAR = "#152d43"
CYAN = "#07867e"
WHITE = "#ffffff"
MUTED = "#567085"


class JaznStudioWindow:
    PAGES = (
        ("dashboard", "Pulpit"),
        ("connections", "MCP i Cloudflare"),
        ("configuration", "Konfiguracja"),
        ("updates", "Aktualizacje"),
        ("diagnostics", "Diagnostyka"),
        ("tools", "Narzędzia"),
    )

    def __init__(self, master: tk.Tk, root: Path) -> None:
        self.master = master
        self.root = root
        self.settings, self.known_sha = load_settings(root)
        self.events: queue.SimpleQueue[tuple[str, Any]] = queue.SimpleQueue()
        self.busy = False
        self.closed = False
        self.page = "dashboard"
        self.master.title("Jaźń — Studio systemowe")
        self.master.geometry("1240x800")
        self.master.minsize(960, 620)
        self.master.configure(bg=BG)
        style = ttk.Style(master)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        style.configure("TButton", padding=(11, 7), font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=BG, foreground=INK, font=("Segoe UI", 20, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("Accent.TButton", background=CYAN, foreground=WHITE)

        shell = tk.Frame(master, bg=BG)
        shell.pack(fill="both", expand=True)
        sidebar = tk.Frame(shell, width=226, bg=SIDEBAR)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="JAŹŃ", bg=SIDEBAR, fg=WHITE,
                 font=("Segoe UI", 23, "bold")).pack(anchor="w", padx=20, pady=(26, 0))
        tk.Label(sidebar, text="STUDIO  " + STUDIO_VERSION, bg=SIDEBAR,
                 fg="#a2c7d4", font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(0, 30))
        for ident, title in self.PAGES:
            tk.Button(sidebar, text=title, anchor="w", relief="flat",
                      padx=19, pady=13, bg=SIDEBAR, fg=WHITE,
                      activebackground="#265370", activeforeground=WHITE,
                      font=("Segoe UI", 11), cursor="hand2",
                      command=lambda name=ident: self.show(name)).pack(fill="x", pady=1)
        self.status_text = tk.StringVar(value="Gotowe. Odczyt nie uruchamia daemona.")
        tk.Label(sidebar, textvariable=self.status_text, bg=SIDEBAR, fg="#a2c7d4",
                 wraplength=197, justify="left", font=("Segoe UI", 9)).pack(
                     side="bottom", fill="x", padx=17, pady=20)

        self.surface = tk.Frame(shell, bg=BG, padx=27, pady=22)
        self.surface.pack(side="left", expand=True, fill="both")
        self.pages: dict[str, ttk.Frame] = {}
        for ident, _ in self.PAGES:
            pane = ttk.Frame(self.surface)
            pane.place(x=0, y=0, relwidth=1, relheight=1)
            self.pages[ident] = pane
        self._dashboard()
        self._connections()
        self._configuration()
        self._updates()
        self._diagnostics()
        self._tools()
        self.show("dashboard")
        self.master.protocol("WM_DELETE_WINDOW", self.close)
        self.master.after(100, self._poll)
        self.master.after(self.settings.refresh_seconds * 1000, self._refresh_timer)

    def _head(self, parent: ttk.Frame, title: str, subtitle: str) -> None:
        ttk.Label(parent, text=title, style="Title.TLabel").pack(anchor="w", pady=(0, 5))
        ttk.Label(parent, text=subtitle, style="Sub.TLabel", wraplength=830).pack(anchor="w", pady=(0, 18))

    def _output(self, parent: ttk.Frame, *, height: int = 17) -> tk.Text:
        panel = tk.Text(parent, bg=WHITE, fg=INK, font=("Consolas", 10),
                        borderwidth=0, padx=17, pady=16, wrap="word",
                        height=height, state="disabled")
        panel.pack(fill="both", expand=True, pady=(9, 0))
        return panel

    @staticmethod
    def _write(panel: tk.Text, value: Any) -> None:
        rendered = json.dumps(value, ensure_ascii=False, indent=2, default=str) if not isinstance(value, str) else value
        panel.configure(state="normal")
        panel.delete("1.0", tk.END)
        panel.insert("1.0", rendered)
        panel.configure(state="disabled")

    def _run(self, label: str, func: Callable[[], Any], output: tk.Text | None = None) -> None:
        if self.busy:
            messagebox.showinfo("Jaźń Studio", "Poczekaj na zakończenie poprzedniej operacji.")
            return
        self.busy = True
        self.status_text.set("Trwa: " + label)
        def worker() -> None:
            try:
                result = func()
                self.events.put(("ok", (label, result, output)))
            except (StudioError, OSError, ValueError, RuntimeError) as exc:
                self.events.put(("error", (label, type(exc).__name__ + ": " + str(exc), output)))
        threading.Thread(target=worker, daemon=True, name="jazn-studio-" + label[:24]).start()

    def _poll(self) -> None:
        if self.closed:
            return
        try:
            while True:
                kind, (name, value, panel) = self.events.get_nowait()
                self.busy = False
                if panel is not None:
                    self._write(panel, value)
                self.status_text.set(("Zakończono: " if kind == "ok" else "Błąd: ") + name)
                if kind != "ok":
                    messagebox.showerror("Jaźń Studio", str(value))
        except queue.Empty:
            pass
        self.master.after(120, self._poll)

    def _refresh_timer(self) -> None:
        if self.closed:
            return
        if self.page == "dashboard" and not self.busy:
            self.refresh_dashboard()
        self.master.after(self.settings.refresh_seconds * 1000, self._refresh_timer)

    def show(self, name: str) -> None:
        self.page = name
        self.pages[name].tkraise()
        if name == "dashboard":
            self.refresh_dashboard()
        elif name == "updates":
            self.refresh_updates()

    def _dashboard(self) -> None:
        area = self.pages["dashboard"]
        self._head(area, "Pulpit Jaźni", "Zweryfikowane procesy i ingress; PID oraz healthz nie są dowodem zaakceptowanej tury.")
        buttons = ttk.Frame(area)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Odśwież status", command=self.refresh_dashboard).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Diagnostyka systemu", command=lambda: self._run("doctor", lambda: run_diagnostic(self.root, "doctor", timeout=30), self.dashboard_text)).pack(side="left", padx=8)
        ttk.Button(buttons, text="Stan modelu", command=lambda: self._run("model", lambda: run_diagnostic(self.root, "model"), self.dashboard_text)).pack(side="left", padx=8)
        self.dashboard_text = self._output(area)

    def refresh_dashboard(self) -> None:
        def inspect() -> dict[str, Any]:
            detail = run_diagnostic(self.root, "status", timeout=25)
            result = detail.get("result", {})
            if not isinstance(result, dict):
                result = {}
            return {
                "package": studio_snapshot(self.root)["system_package"],
                "runtime_status_checked": detail["ok"],
                "runtime_core_ready": result.get("runtime_core_ready"),
                "system_fully_ready": result.get("system_fully_ready"),
                "operational_state": result.get("operational_state"),
                "memory_availability": result.get("memory_availability", {}).get("status")
                    if isinstance(result.get("memory_availability"), dict) else None,
                "daemon": result.get("daemon", {}).get("daemon_instance_id")
                    if isinstance(result.get("daemon"), dict) else None,
                "error": detail.get("error") or detail.get("stderr_tail"),
                "note": "Status procesu != accepted display_exact; remote route is separately verified.",
            }
        self._run("status runtime", inspect, self.dashboard_text)

    def _connections(self) -> None:
        area = self.pages["connections"]
        self._head(area, "MCP i Cloudflare", "Osobne próby lokalnego MCP i publicznego HTTPS. Żadne żądanie nie zawiera tokenu.")
        buttons = ttk.Frame(area)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Lokalne /healthz i /readyz", command=lambda: self._run(
            "local MCP", lambda: [
                probe_http("http://127.0.0.1:8080/healthz", timeout=self.settings.timeout_seconds),
                probe_http("http://127.0.0.1:8080/readyz", timeout=self.settings.timeout_seconds),
            ], self.connection_text)).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Cloudflare /healthz i /readyz", command=lambda: self._run(
            "Cloudflare HTTPS", lambda: [
                probe_http(self.settings.cloudflare_url + "/healthz", timeout=self.settings.timeout_seconds),
                probe_http(self.settings.cloudflare_url + "/readyz", timeout=self.settings.timeout_seconds),
            ], self.connection_text)).pack(side="left", padx=8)
        ttk.Button(buttons, text="Katalog narzędzi MCP", command=lambda: self._run(
            "MCP tools/list", lambda: run_diagnostic(self.root, "mcp_catalog", timeout=16),
            self.connection_text)).pack(side="left", padx=8)
        self.connection_text = self._output(area)
        self._write(self.connection_text, {
            "local": self.settings.local_mcp_url,
            "remote": self.settings.cloudflare_url + "/mcp",
            "public_mcp_available": "unknown_until_auth_and_tools_are_checked",
            "important": "Cloudflare /healthz is only edge liveness; a 503 /mcp can be intentionally fail-closed.",
        })

    def _configuration(self) -> None:
        area = self.pages["configuration"]
        self._head(area, "Ustawienia Studia", "Zapis operatora poza SYSTEM/MEMORY. Konfigurację runtime edytuje kanoniczne Studio Konfiguracji.")
        form = ttk.Frame(area)
        form.pack(fill="x")
        self.remote_var = tk.StringVar(value=self.settings.cloudflare_url)
        self.refresh_var = tk.StringVar(value=str(self.settings.refresh_seconds))
        self.timeout_var = tk.StringVar(value=str(self.settings.timeout_seconds))
        self.details_var = tk.BooleanVar(value=self.settings.show_details)
        for index, (caption, variable) in enumerate([
            ("Adres Cloudflare HTTPS", self.remote_var),
            ("Odświeżanie pulpitu (sekundy)", self.refresh_var),
            ("Timeout żądań (sekundy)", self.timeout_var),
        ]):
            ttk.Label(form, text=caption).grid(row=index, column=0, sticky="w", pady=9, padx=(0, 15))
            ttk.Entry(form, textvariable=variable, width=58 if index == 0 else 15).grid(
                row=index, column=1, sticky="ew", pady=9)
        ttk.Checkbutton(form, text="Pokaż rozszerzone diagnostyki", variable=self.details_var).grid(
            row=3, column=1, sticky="w", pady=8)
        form.columnconfigure(1, weight=1)
        buttons = ttk.Frame(area)
        buttons.pack(fill="x", pady=12)
        ttk.Button(buttons, text="Zapisz profil Studia", command=self.save_settings).pack(side="left", padx=(0, 10))
        ttk.Button(buttons, text="Edytuj konfigurację Jaźni", command=lambda: self.open_studio("configuration")).pack(side="left")
        ttk.Label(area, text="Zmiana profilu Jaźni dotyczy przyszłego uruchomienia. Nie przenosi MEMORY i nie restartuje procesu.",
                  style="Sub.TLabel", wraplength=750).pack(anchor="w", pady=12)

    def save_settings(self) -> None:
        from .core import write_settings
        try:
            config = StudioSettings.validate({
                "cloudflare_url": self.remote_var.get(),
                "local_mcp_url": self.settings.local_mcp_url,
                "refresh_seconds": int(self.refresh_var.get()),
                "timeout_seconds": int(self.timeout_var.get()),
                "show_details": self.details_var.get(),
            })
            path = write_settings(self.root, config, expected_sha256=self.known_sha)
            self.settings, self.known_sha = load_settings(self.root)
        except (StudioError, ValueError, OSError) as exc:
            messagebox.showerror("Konfiguracja", str(exc))
        else:
            self.status_text.set("Zapisano ustawienia: " + str(path))

    def _updates(self) -> None:
        area = self.pages["updates"]
        self._head(area, "Aktualizacje i patche", "Bezpieczeństwo: tylko clean master, fast-forward, zatrzymany daemon i MCP, ręczny backup.")
        buttons = ttk.Frame(area)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Sprawdź lokalne różnice", command=self.refresh_updates).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Pobierz informacje (git fetch)", command=self.fetch).pack(side="left", padx=8)
        ttk.Button(buttons, text="Zastosuj fast-forward", command=self.apply_update).pack(side="left", padx=8)
        self.updates_text = self._output(area)

    def refresh_updates(self) -> None:
        self._run("plan aktualizacji", lambda: update_plan(self.root), self.updates_text)

    def fetch(self) -> None:
        if not messagebox.askyesno("Git fetch", "Pobrać nowe obiekty i referencję origin/master? Nie zmieni to plików SYSTEM."):
            return
        self._run("git fetch", lambda: fetch_updates(self.root), self.updates_text)

    def apply_update(self) -> None:
        plan = update_plan(self.root)
        if not plan.get("apply_allowed"):
            messagebox.showwarning("Aktualizacja zablokowana", str(plan.get("reason")))
            self._write(self.updates_text, plan)
            return
        if not messagebox.askyesno("Aktualizacja Jaźni",
            "Potwierdź niezależny backup MEMORY i workspace, zatrzymany daemon/MCP, "
            "czysty master i sprawdzony CI. Zastosować git merge --ff-only origin/master?"):
            return
        self._run("fast-forward", lambda: apply_fast_forward(self.root, acknowledged_backup=True),
                  self.updates_text)

    def _diagnostics(self) -> None:
        area = self.pages["diagnostics"]
        self._head(area, "Diagnostyka", "Wyłącznie kanoniczne komendy Jaźni. Odczyty nie zapisują nowych tur.")
        buttons = ttk.Frame(area)
        buttons.pack(fill="x")
        for item, caption in (("status", "Runtime"), ("doctor", "Doctor"), ("memory", "MEMORY"),
                              ("model", "Model"), ("mcp_catalog", "MCP")):
            ttk.Button(buttons, text=caption,
                       command=lambda key=item: self._run(
                           key, lambda: run_diagnostic(self.root, key, timeout=30),
                           self.diagnostics_text)).pack(side="left", padx=5)
        self.diagnostics_text = self._output(area)

    def _tools(self) -> None:
        area = self.pages["tools"]
        self._head(area, "Narzędzia Jaźni", "Uruchamianie istniejących aplikacji. Studio nie kopiuje ich logiki ani pamięci.")
        for target, caption, explanation in [
            ("configuration", "Studio Konfiguracji", "Walidowane profile Jaźni i edycja ustawień przyszłego startu"),
            ("tests", "Studio Testów", "Katalog kontraktów, pojedyncze testy i historia"),
            ("memory", "Studio Pamięci", "Kanoniczne narzędzie pamięci, ze swoimi zgodami i zabezpieczeniami"),
        ]:
            row = ttk.Frame(area)
            row.pack(fill="x", pady=9)
            ttk.Button(row, text="Otwórz: " + caption, width=29,
                       command=lambda key=target: self.open_studio(key)).pack(side="left")
            ttk.Label(row, text=explanation, wraplength=460).pack(side="left", padx=16)

    def open_studio(self, target: str) -> None:
        try:
            args = safe_launcher(self.root, target)
            subprocess.Popen(args, cwd=self.root, stdin=subprocess.DEVNULL, shell=False)
        except (StudioError, OSError) as exc:
            messagebox.showerror("Jaźń Studio", str(exc))

    def close(self) -> None:
        self.closed = True
        self.master.destroy()


def run_window(root: Path, *, smoke: bool = False) -> int:
    master = tk.Tk()
    if smoke:
        master.withdraw()
    try:
        JaznStudioWindow(master, root)
        if smoke:
            master.update_idletasks()
        else:
            master.mainloop()
    finally:
        if master.winfo_exists():
            master.destroy()
    return 0
