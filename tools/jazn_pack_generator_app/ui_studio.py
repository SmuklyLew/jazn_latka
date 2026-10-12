from __future__ import annotations

import json
from pathlib import Path
import queue
import threading
from typing import Any, Callable

from latka_jazn.tools.application_shell import DiagnosticsHub

from .constants import GENERATOR_TITLE, GENERATOR_VERSION
from .models import ContentMode, PackRequest, ProgressEvent, TransportMode
from .service import config_report, pack, unpack_package, verify_package
from .settings import load_settings, save_settings


def run_studio_ui(diagnostics: DiagnosticsHub | None = None) -> int:
    """Run the Windows/Tk surface over the same Pack Generator domain core."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise RuntimeError("Tryb window wymaga tkinter/Tk.") from exc

    class StudioApp:
        def __init__(self) -> None:
            self.root = tk.Tk()
            self.root.title(f"{GENERATOR_TITLE} {GENERATOR_VERSION}")
            self.root.geometry("1180x760")
            self.root.minsize(960, 620)
            self.settings = load_settings()
            self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
            self.cancel_event = threading.Event()
            self.worker: threading.Thread | None = None
            self.status_var = tk.StringVar(value="Gotowe")
            self.progress_var = tk.DoubleVar(value=0.0)
            self.pages: dict[str, ttk.Frame] = {}
            self._build_shell()
            self._build_pages()
            self.show_page("Główna")
            self.root.protocol("WM_DELETE_WINDOW", self.close)
            self.root.after(100, self._poll)
            if diagnostics is not None:
                diagnostics.record("INFO", "Uruchomiono okno Pack Generator", version=GENERATOR_VERSION)

        def _build_shell(self) -> None:
            style = ttk.Style(self.root)
            try:
                style.theme_use("vista")
            except tk.TclError:
                pass
            body = ttk.Frame(self.root, padding=10)
            body.pack(fill="both", expand=True)
            nav = ttk.Frame(body, width=210)
            nav.pack(side="left", fill="y", padx=(0, 10))
            self.content = ttk.Frame(body)
            self.content.pack(side="left", fill="both", expand=True)
            ttk.Label(nav, text="JAŹŃ\nPACK GENERATOR", font=("Segoe UI", 15, "bold"), justify="left").pack(anchor="w", pady=(4, 18))
            for page in ("Główna", "Pakowanie", "Rozpakowanie", "Weryfikacja", "Ustawienia", "Diagnostyka"):
                ttk.Button(nav, text=page, command=lambda p=page: self.show_page(p)).pack(fill="x", pady=3)
            ttk.Separator(nav).pack(fill="x", pady=14)
            ttk.Label(nav, text=f"v{GENERATOR_VERSION}", justify="left").pack(anchor="w")
            status = ttk.Frame(self.root, padding=(10, 4))
            status.pack(side="bottom", fill="x")
            ttk.Label(status, textvariable=self.status_var).pack(side="left")
            ttk.Progressbar(status, variable=self.progress_var, maximum=100, length=300).pack(side="right")
            self.stop_button = ttk.Button(status, text="STOP", state="disabled", command=self.stop)
            self.stop_button.pack(side="right", padx=(0, 8))

        def _build_pages(self) -> None:
            for name in ("Główna", "Pakowanie", "Rozpakowanie", "Weryfikacja", "Ustawienia", "Diagnostyka"):
                frame = ttk.Frame(self.content, padding=16)
                frame.grid(row=0, column=0, sticky="nsew")
                self.pages[name] = frame
            self.content.rowconfigure(0, weight=1)
            self.content.columnconfigure(0, weight=1)
            self._build_home()
            self._build_pack()
            self._build_unpack()
            self._build_verify()
            self._build_settings()
            self._build_diagnostics()

        @staticmethod
        def _title(frame: Any, title: str, subtitle: str) -> None:
            ttk.Label(frame, text=title, font=("Segoe UI", 20, "bold")).pack(anchor="w")
            ttk.Label(frame, text=subtitle, wraplength=820).pack(anchor="w", pady=(3, 14))
            ttk.Separator(frame).pack(fill="x", pady=(0, 14))

        def show_page(self, name: str) -> None:
            self.pages[name].tkraise()
            if name == "Diagnostyka":
                self.refresh_diagnostics()

        def _build_home(self) -> None:
            frame = self.pages["Główna"]
            self._title(frame, "Jaźń Pack Generator", "Kanoniczne pakowanie SYSTEM/MEMORY, weryfikacja integralności i bezpieczne rozpakowanie.")
            cfg = config_report()
            ttk.Label(
                frame,
                text=(
                    f"Wersja: {GENERATOR_VERSION}\n"
                    f"Platforma: {cfg.get('platform')}\n"
                    f"Python: {cfg.get('python')}\n\n"
                    "Ten sam rdzeń działa w trybie tekstowym, TUI i oknie Windows. "
                    "Długie operacje są wykonywane poza pętlą GUI."
                ),
                justify="left",
                wraplength=820,
            ).pack(anchor="w")
            ttk.Button(frame, text="Przejdź do pakowania", command=lambda: self.show_page("Pakowanie")).pack(anchor="w", pady=20)

        def _row(self, parent: Any, row: int, label: str, variable: Any, *, directory: bool = True) -> None:
            parent.columnconfigure(1, weight=1)
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
            action = (lambda: filedialog.askdirectory(initialdir=variable.get() or None)) if directory else (lambda: filedialog.askopenfilename(initialdir=str(Path(variable.get()).parent) if variable.get() else None))
            def browse() -> None:
                value = action()
                if value:
                    variable.set(value)
            ttk.Button(parent, text="…", width=4, command=browse).grid(row=row, column=2, pady=6)

        def _build_pack(self) -> None:
            frame = self.pages["Pakowanie"]
            self._title(frame, "Pakowanie", "Wybierz źródło, profil i transport. Operacja zachowuje kanoniczne kontrakty paczki.")
            form = ttk.Frame(frame)
            form.pack(fill="x")
            self.source_var = tk.StringVar(value=str(self.settings.get("source_root") or Path.cwd()))
            self.output_var = tk.StringVar(value=str(self.settings.get("output_root") or ""))
            self.memory_var = tk.StringVar(value=str(self.settings.get("memory_root") or ""))
            self.content_var = tk.StringVar(value="system")
            self.split_var = tk.BooleanVar(value=False)
            self.part_var = tk.IntVar(value=int(self.settings.get("part_size_mib") or 450))
            self.compression_var = tk.IntVar(value=int(self.settings.get("compression_level") or 6))
            self._row(form, 0, "Folder Jaźni", self.source_var)
            self._row(form, 1, "Folder wynikowy", self.output_var)
            self._row(form, 2, "Folder pamięci", self.memory_var)
            ttk.Label(form, text="Zawartość").grid(row=3, column=0, sticky="w", pady=6)
            ttk.Combobox(form, values=("system", "memory", "system+memory"), state="readonly", textvariable=self.content_var, width=22).grid(row=3, column=1, sticky="w", pady=6)
            ttk.Checkbutton(form, text="Dziel ZIP na części transportowe", variable=self.split_var).grid(row=4, column=1, sticky="w", pady=6)
            ttk.Label(form, text="Rozmiar części MiB").grid(row=5, column=0, sticky="w", pady=6)
            ttk.Spinbox(form, from_=1, to=102400, textvariable=self.part_var, width=12).grid(row=5, column=1, sticky="w")
            ttk.Label(form, text="Kompresja 0..9").grid(row=6, column=0, sticky="w", pady=6)
            ttk.Spinbox(form, from_=0, to=9, textvariable=self.compression_var, width=12).grid(row=6, column=1, sticky="w")
            ttk.Button(form, text="URUCHOM PAKOWANIE", command=self.start_pack).grid(row=7, column=1, sticky="w", pady=16)
            self.pack_output = tk.Text(frame, height=14, state="disabled", wrap="word")
            self.pack_output.pack(fill="both", expand=True, pady=(10, 0))

        def start_pack(self) -> None:
            source = Path(self.source_var.get()).expanduser()
            output = Path(self.output_var.get()).expanduser() if self.output_var.get().strip() else source.parent / "jazn_packages"
            memory = Path(self.memory_var.get()).expanduser() if self.memory_var.get().strip() else None
            request = PackRequest(
                source_root=source,
                output_root=output,
                content=ContentMode(self.content_var.get()),
                memory_root=memory,
                transport=TransportMode.SPLIT if self.split_var.get() else TransportMode.SINGLE,
                part_size_mib=int(self.part_var.get()),
                compression_level=int(self.compression_var.get()),
            )
            self._start(lambda: pack(request, callback=self._progress, cancel_event=self.cancel_event).to_dict(), self.pack_output)

        def _build_unpack(self) -> None:
            frame = self.pages["Rozpakowanie"]
            self._title(frame, "Rozpakowanie", "Bezpiecznie rozpakuj ZIP lub pierwszą część .zip.001.")
            form = ttk.Frame(frame); form.pack(fill="x")
            self.unpack_source = tk.StringVar(); self.unpack_target = tk.StringVar(value=str(Path.cwd() / "jazn_unpacked"))
            self._row(form, 0, "Paczka", self.unpack_source, directory=False)
            self._row(form, 1, "Katalog docelowy", self.unpack_target)
            ttk.Button(form, text="ROZPAKUJ", command=self.start_unpack).grid(row=2, column=1, sticky="w", pady=16)
            self.unpack_output = tk.Text(frame, state="disabled", wrap="word"); self.unpack_output.pack(fill="both", expand=True)

        def start_unpack(self) -> None:
            source = Path(self.unpack_source.get()).expanduser(); target = Path(self.unpack_target.get()).expanduser()
            self._start(lambda: {"ok": True, "destination": str(unpack_package(source, target, callback=self._progress, cancel_event=self.cancel_event))}, self.unpack_output)

        def _build_verify(self) -> None:
            frame = self.pages["Weryfikacja"]
            self._title(frame, "Weryfikacja", "Sprawdź SHA-256, strukturę ZIP, CRC i kontrakty paczki.")
            form = ttk.Frame(frame); form.pack(fill="x")
            self.verify_source = tk.StringVar(); self._row(form, 0, "Paczka", self.verify_source, directory=False)
            ttk.Button(form, text="SPRAWDŹ", command=self.start_verify).grid(row=1, column=1, sticky="w", pady=16)
            self.verify_output = tk.Text(frame, state="disabled", wrap="word"); self.verify_output.pack(fill="both", expand=True)

        def start_verify(self) -> None:
            source = Path(self.verify_source.get()).expanduser()
            self._start(lambda: verify_package(source, callback=self._progress, cancel_event=self.cancel_event), self.verify_output)

        def _build_settings(self) -> None:
            frame = self.pages["Ustawienia"]
            self._title(frame, "Ustawienia", "Lokalna konfiguracja interfejsu, splashscreenu i diagnostyki.")
            form = ttk.Frame(frame); form.pack(fill="x")
            form.columnconfigure(1, weight=1)
            self.ui_var = tk.StringVar(value=str(self.settings.get("ui_mode") or "window"))
            self.splash_var = tk.BooleanVar(value=bool(self.settings.get("splash_enabled", True)))
            self.diag_var = tk.BooleanVar(value=bool(self.settings.get("diagnostics_enabled", True)))
            self.level_var = tk.StringVar(value=str(self.settings.get("log_level") or "INFO"))
            ttk.Label(form, text="Domyślny interfejs").grid(row=0, column=0, sticky="w", pady=6)
            ttk.Combobox(form, values=("text", "tui", "window"), state="readonly", textvariable=self.ui_var).grid(row=0, column=1, sticky="w")
            ttk.Checkbutton(form, text="Splashscreen", variable=self.splash_var).grid(row=1, column=1, sticky="w", pady=6)
            ttk.Checkbutton(form, text="Diagnostyka / log", variable=self.diag_var).grid(row=2, column=1, sticky="w", pady=6)
            ttk.Label(form, text="Poziom logu").grid(row=3, column=0, sticky="w", pady=6)
            ttk.Combobox(form, values=("DEBUG", "INFO", "WARNING", "ERROR"), state="readonly", textvariable=self.level_var).grid(row=3, column=1, sticky="w")
            ttk.Button(form, text="Zapisz", command=self.save_user_settings).grid(row=4, column=1, sticky="w", pady=16)

        def save_user_settings(self) -> None:
            self.settings.update({"ui_mode": self.ui_var.get(), "splash_enabled": bool(self.splash_var.get()), "diagnostics_enabled": bool(self.diag_var.get()), "log_level": self.level_var.get()})
            self.settings = save_settings(self.settings)
            if diagnostics is not None:
                diagnostics.reconfigure(enabled=bool(self.settings.get("diagnostics_enabled", True)), limit=int(self.settings.get("diagnostics_limit", 500)), minimum_level=str(self.settings.get("log_level") or "INFO"))
                diagnostics.record("INFO", "Zapisano ustawienia Pack Generator", settings=self.settings)
            self.status_var.set("Ustawienia zapisane")

        def _build_diagnostics(self) -> None:
            frame = self.pages["Diagnostyka"]
            self._title(frame, "Diagnostyka / log", "Bieżące zdarzenia aplikacji oraz trwały log JSONL.")
            self.diag_text = tk.Text(frame, state="disabled", wrap="word")
            self.diag_text.pack(fill="both", expand=True)
            ttk.Button(frame, text="Odśwież", command=self.refresh_diagnostics).pack(anchor="e", pady=8)

        def refresh_diagnostics(self) -> None:
            text = "Diagnostyka wyłączona dla tej sesji." if diagnostics is None else f"Plik: {diagnostics.log_path}\n\n{diagnostics.text(limit=200)}"
            self._set_text(self.diag_text, text)

        def _progress(self, event: ProgressEvent) -> None:
            self.events.put(("progress", event))

        def _start(self, operation: Callable[[], Any], target: Any) -> None:
            if self.worker is not None and self.worker.is_alive():
                messagebox.showwarning(GENERATOR_TITLE, "Inna operacja jest aktywna.")
                return
            self.cancel_event = threading.Event(); self.progress_var.set(0); self.status_var.set("Praca..."); self.stop_button.configure(state="normal")
            def worker() -> None:
                try: self.events.put(("done", (operation(), target)))
                except Exception as exc: self.events.put(("error", f"{type(exc).__name__}: {exc}"))
            self.worker = threading.Thread(target=worker, name="jazn-pack-worker", daemon=True); self.worker.start()
            if diagnostics is not None: diagnostics.record("INFO", "Uruchomiono operację Pack Generator", worker=self.worker.name)

        def stop(self) -> None:
            self.cancel_event.set(); self.status_var.set("Anulowanie...")
            if diagnostics is not None: diagnostics.record("WARNING", "Zażądano anulowania Pack Generator")

        @staticmethod
        def _set_text(widget: Any, text: str) -> None:
            widget.configure(state="normal"); widget.delete("1.0", "end"); widget.insert("1.0", text); widget.configure(state="disabled")

        def _poll(self) -> None:
            try:
                while True:
                    kind, payload = self.events.get_nowait()
                    if kind == "progress":
                        event: ProgressEvent = payload; self.progress_var.set(event.fraction * 100); self.status_var.set(event.message)
                    elif kind == "done":
                        result, target = payload; self.stop_button.configure(state="disabled"); self.progress_var.set(100); self.status_var.set("Gotowe"); self._set_text(target, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
                        if diagnostics is not None: diagnostics.record("INFO", "Operacja Pack Generator zakończona")
                    elif kind == "error":
                        self.stop_button.configure(state="disabled"); self.status_var.set("Błąd");
                        if diagnostics is not None: diagnostics.record("ERROR", "Błąd Pack Generator", error=str(payload))
                        messagebox.showerror(GENERATOR_TITLE, str(payload))
            except queue.Empty:
                pass
            self.root.after(100, self._poll)

        def close(self) -> None:
            if self.worker is not None and self.worker.is_alive(): self.cancel_event.set()
            if diagnostics is not None: diagnostics.record("INFO", "Zamknięto okno Pack Generator")
            try: self.root.destroy()
            except tk.TclError: pass

        def run(self) -> int:
            try:
                self.root.mainloop(); return 0
            except KeyboardInterrupt:
                self.close(); return 130

    return StudioApp().run()
