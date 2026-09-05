from __future__ import annotations

import json
from pathlib import Path
import queue
import threading
from typing import Any, Callable

from .constants import GENERATOR_TITLE, GENERATOR_VERSION
from .models import ContentMode, PackRequest, ProgressEvent, TransportMode
from .service import config_report, pack, plan_pack, unpack_package, verify_package
from .settings import load_settings, save_settings


def run_studio_ui() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise RuntimeError("UI Studio wymaga tkinter/Tk.") from exc

    class StudioApp:
        def __init__(self) -> None:
            self.root = tk.Tk()
            self.root.title(f"{GENERATOR_TITLE} {GENERATOR_VERSION}")
            self.root.geometry("1120x720")
            self.root.minsize(980, 640)
            self.settings = load_settings()
            self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
            self.cancel_event = threading.Event()
            self.worker: threading.Thread | None = None
            self.pages: dict[str, ttk.Frame] = {}
            self.status_var = tk.StringVar(value="Gotowy")
            self.progress_var = tk.DoubleVar(value=0.0)
            self._build_shell()
            self._build_pages()
            self.show_page("Start")
            self.root.after(100, self._poll_events)

        def _build_shell(self) -> None:
            style = ttk.Style(self.root)
            try:
                style.theme_use("vista")
            except tk.TclError:
                pass
            outer = ttk.Frame(self.root, padding=10)
            outer.pack(fill="both", expand=True)
            self.sidebar = ttk.Frame(outer, width=190)
            self.sidebar.pack(side="left", fill="y", padx=(0, 10))
            self.content = ttk.Frame(outer)
            self.content.pack(side="left", fill="both", expand=True)

            ttk.Label(
                self.sidebar,
                text="JAŹŃ\nPACK STUDIO",
                font=("Segoe UI", 15, "bold"),
                justify="left",
            ).pack(anchor="w", pady=(4, 16))

            for name in ("Start", "Pakowanie", "Rozpakowywanie", "Weryfikacja", "Ustawienia", "Konfiguracja", "Informacje"):
                ttk.Button(self.sidebar, text=name, command=lambda n=name: self.show_page(n)).pack(fill="x", pady=3)

            ttk.Separator(self.sidebar).pack(fill="x", pady=12)
            ttk.Label(self.sidebar, text=f"Generator\n{GENERATOR_VERSION}", justify="left").pack(anchor="w")
            ttk.Label(
                self.sidebar,
                text="Archiwizacja SYSTEM /\nMEMORY / SYSTEM+MEMORY",
                justify="left",
            ).pack(anchor="w", pady=(8, 0))

            status = ttk.Frame(self.root, padding=(10, 4))
            status.pack(side="bottom", fill="x")
            ttk.Label(status, textvariable=self.status_var).pack(side="left")
            ttk.Progressbar(status, variable=self.progress_var, maximum=100, length=280).pack(side="right")
            self.cancel_button = ttk.Button(status, text="Anuluj", command=self.cancel_current, state="disabled")
            self.cancel_button.pack(side="right", padx=(0, 8))

        def _build_pages(self) -> None:
            for name in ("Start", "Pakowanie", "Rozpakowywanie", "Weryfikacja", "Ustawienia", "Konfiguracja", "Informacje"):
                frame = ttk.Frame(self.content, padding=14)
                frame.grid(row=0, column=0, sticky="nsew")
                self.pages[name] = frame
            self.content.rowconfigure(0, weight=1)
            self.content.columnconfigure(0, weight=1)
            self._build_start()
            self._build_pack()
            self._build_unpack()
            self._build_verify()
            self._build_settings()
            self._build_config()
            self._build_info()

        def show_page(self, name: str) -> None:
            self.pages[name].tkraise()
            if name == "Konfiguracja":
                self._refresh_config()

        def _title(self, frame: Any, title: str, subtitle: str) -> None:
            ttk.Label(frame, text=title, font=("Segoe UI", 19, "bold")).pack(anchor="w")
            ttk.Label(frame, text=subtitle, wraplength=800).pack(anchor="w", pady=(2, 16))
            ttk.Separator(frame).pack(fill="x", pady=(0, 16))

        def _build_start(self) -> None:
            frame = self.pages["Start"]
            self._title(
                frame,
                "Jaźń Pack Studio",
                "Jedno narzędzie do pakowania, dzielenia, weryfikacji i rozpakowywania folderu Jaźni.",
            )
            cards = ttk.Frame(frame)
            cards.pack(fill="x")
            for col, (label, content) in enumerate(
                (
                    ("SYSTEM", "Folder Jaźni bez pamięci"),
                    ("MEMORY", "Tylko kanoniczna pamięć"),
                    ("SYSTEM + MEMORY", "Jedna logiczna paczka"),
                )
            ):
                card = ttk.LabelFrame(cards, text=label, padding=16)
                card.grid(row=0, column=col, sticky="nsew", padx=6)
                cards.columnconfigure(col, weight=1)
                ttk.Label(card, text=content, wraplength=200).pack(anchor="w")
                ttk.Button(card, text="Przejdź do pakowania", command=lambda: self.show_page("Pakowanie")).pack(anchor="w", pady=(16, 0))
            ttk.Label(
                frame,
                text=(
                    "Generator nie buduje wheelhouse, dependency bundle ani środowiska Python. "
                    "Tworzy zwykły ZIP64 i opcjonalnie dzieli go na części transportowe."
                ),
                wraplength=820,
            ).pack(anchor="w", pady=24)

        def _browse_dir(self, variable: Any) -> None:
            value = filedialog.askdirectory(initialdir=variable.get() or None)
            if value:
                variable.set(value)

        def _browse_file(self, variable: Any) -> None:
            value = filedialog.askopenfilename(
                initialdir=str(Path(variable.get()).parent) if variable.get() else None,
                filetypes=[("Jaźń ZIP", "*.zip *.zip.001"), ("Wszystkie pliki", "*.*")],
            )
            if value:
                variable.set(value)

        def _labeled_entry(self, parent: Any, row: int, label: str, variable: Any, browse: bool = False) -> None:
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
            if browse:
                ttk.Button(parent, text="…", width=4, command=lambda: self._browse_dir(variable)).grid(row=row, column=2, pady=6)

        def _build_pack(self) -> None:
            frame = self.pages["Pakowanie"]
            self._title(frame, "Pakowanie", "Wybierz zawartość i sposób transportu. Resztą zajmuje się jeden wspólny core.")
            form = ttk.Frame(frame)
            form.pack(fill="x")
            form.columnconfigure(1, weight=1)
            cwd = str(Path.cwd())
            self.source_var = tk.StringVar(value=str(self.settings.get("source_root") or cwd))
            self.output_var = tk.StringVar(value=str(self.settings.get("output_root") or ""))
            self.memory_var = tk.StringVar(value=str(self.settings.get("memory_root") or ""))
            self.content_var = tk.StringVar(value="system")
            self.split_var = tk.BooleanVar(value=False)
            self.part_var = tk.IntVar(value=int(self.settings.get("part_size_mib") or 450))
            self.compression_var = tk.IntVar(value=int(self.settings.get("compression_level") or 6))
            self.plan_text = tk.Text(frame, height=13, wrap="word", state="disabled")

            self._labeled_entry(form, 0, "Folder Jaźni", self.source_var, True)
            self._labeled_entry(form, 1, "Folder wynikowy", self.output_var, True)
            self._labeled_entry(form, 2, "Folder pamięci (opcjonalnie)", self.memory_var, True)

            ttk.Label(form, text="Zawartość").grid(row=3, column=0, sticky="w", pady=8)
            choices = ttk.Frame(form)
            choices.grid(row=3, column=1, sticky="w", pady=8)
            for value, label in (("system", "SYSTEM"), ("memory", "MEMORY"), ("system+memory", "SYSTEM + MEMORY")):
                ttk.Radiobutton(choices, text=label, value=value, variable=self.content_var, command=self._sync_pack_controls).pack(side="left", padx=(0, 14))

            ttk.Checkbutton(
                form,
                text="Podziel duży ZIP na części transportowe",
                variable=self.split_var,
                command=self._sync_pack_controls,
            ).grid(row=4, column=1, sticky="w", pady=8)
            ttk.Label(form, text="Rozmiar części [MiB]").grid(row=5, column=0, sticky="w")
            self.part_spin = ttk.Spinbox(form, from_=1, to=102400, textvariable=self.part_var, width=12)
            self.part_spin.grid(row=5, column=1, sticky="w", pady=6)
            ttk.Label(form, text="Kompresja ZIP [0..9]").grid(row=6, column=0, sticky="w")
            ttk.Spinbox(form, from_=0, to=9, textvariable=self.compression_var, width=12).grid(row=6, column=1, sticky="w", pady=6)

            actions = ttk.Frame(form)
            actions.grid(row=7, column=1, sticky="w", pady=(14, 8))
            ttk.Button(actions, text="Sprawdź plan", command=self.preview_plan).pack(side="left")
            ttk.Button(actions, text="SPAKUJ", command=self.start_pack).pack(side="left", padx=8)
            self.plan_text.pack(fill="both", expand=True, pady=(14, 0))
            self._sync_pack_controls()

        def _sync_pack_controls(self) -> None:
            self.part_spin.configure(state="normal" if self.split_var.get() else "disabled")

        def _request(self) -> PackRequest:
            output = self.output_var.get().strip()
            if not output:
                source = Path(self.source_var.get()).expanduser()
                output = str(source.parent / "jazn_packages")
                self.output_var.set(output)
            memory_raw = self.memory_var.get().strip()
            return PackRequest(
                source_root=Path(self.source_var.get()).expanduser(),
                output_root=Path(output).expanduser(),
                content=ContentMode(self.content_var.get()),
                memory_root=Path(memory_raw).expanduser() if memory_raw else None,
                transport=TransportMode.SPLIT if self.split_var.get() else TransportMode.SINGLE,
                part_size_mib=int(self.part_var.get()),
                compression_level=int(self.compression_var.get()),
            )

        def _set_text(self, widget: Any, text: str) -> None:
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
            widget.configure(state="disabled")

        def preview_plan(self) -> None:
            try:
                plan = plan_pack(self._request())
                self._set_text(self.plan_text, json.dumps(plan.summary(), ensure_ascii=False, indent=2))
                self.status_var.set("Plan poprawny")
            except Exception as exc:
                messagebox.showerror("Plan pakowania", f"{type(exc).__name__}: {exc}")

        def start_pack(self) -> None:
            request = self._request()
            self._start_worker(lambda: pack(request, callback=self._progress_from_worker, cancel_event=self.cancel_event).to_dict())

        def _build_unpack(self) -> None:
            frame = self.pages["Rozpakowywanie"]
            self._title(frame, "Rozpakowywanie", "ZIP albo pierwsza część .zip.001; preflight integralności jest wykonywany przed ekstrakcją.")
            form = ttk.Frame(frame)
            form.pack(fill="x")
            form.columnconfigure(1, weight=1)
            self.unpack_archive_var = tk.StringVar()
            self.unpack_dest_var = tk.StringVar(value=str(Path.cwd() / "jazn_unpacked"))
            ttk.Label(form, text="Paczka").grid(row=0, column=0, sticky="w", pady=6)
            ttk.Entry(form, textvariable=self.unpack_archive_var).grid(row=0, column=1, sticky="ew", padx=8)
            ttk.Button(form, text="…", width=4, command=lambda: self._browse_file(self.unpack_archive_var)).grid(row=0, column=2)
            self._labeled_entry(form, 1, "Katalog docelowy", self.unpack_dest_var, True)
            ttk.Button(form, text="ROZPAKUJ", command=self.start_unpack).grid(row=2, column=1, sticky="w", pady=16)

        def start_unpack(self) -> None:
            source = Path(self.unpack_archive_var.get()).expanduser()
            destination = Path(self.unpack_dest_var.get()).expanduser()
            self._start_worker(lambda: {"ok": True, "destination": str(unpack_package(source, destination, callback=self._progress_from_worker, cancel_event=self.cancel_event))})

        def _build_verify(self) -> None:
            frame = self.pages["Weryfikacja"]
            self._title(frame, "Weryfikacja", "Sprawdza części, SHA-256, strukturę ZIP i CRC.")
            row = ttk.Frame(frame)
            row.pack(fill="x")
            row.columnconfigure(0, weight=1)
            self.verify_var = tk.StringVar()
            ttk.Entry(row, textvariable=self.verify_var).grid(row=0, column=0, sticky="ew")
            ttk.Button(row, text="…", width=4, command=lambda: self._browse_file(self.verify_var)).grid(row=0, column=1, padx=6)
            ttk.Button(row, text="SPRAWDŹ", command=self.start_verify).grid(row=0, column=2)
            self.verify_text = tk.Text(frame, height=22, state="disabled")
            self.verify_text.pack(fill="both", expand=True, pady=14)

        def start_verify(self) -> None:
            source = Path(self.verify_var.get()).expanduser()
            self._start_worker(lambda: verify_package(source, callback=self._progress_from_worker, cancel_event=self.cancel_event), result_widget=self.verify_text)

        def _build_settings(self) -> None:
            frame = self.pages["Ustawienia"]
            self._title(frame, "Ustawienia", "Ustawienia użytkownika są zapisywane obok modułów narzędzia i nie należą do paczki Jaźni.")
            form = ttk.Frame(frame)
            form.pack(fill="x")
            form.columnconfigure(1, weight=1)
            self.settings_ui_var = tk.StringVar(value=str(self.settings.get("ui_mode") or "studio"))
            self.settings_output_var = tk.StringVar(value=str(self.settings.get("output_root") or ""))
            self.settings_part_var = tk.IntVar(value=int(self.settings.get("part_size_mib") or 450))
            self.settings_compression_var = tk.IntVar(value=int(self.settings.get("compression_level") or 6))
            ttk.Label(form, text="Domyślny interfejs").grid(row=0, column=0, sticky="w", pady=6)
            ttk.Combobox(form, values=("text", "tui", "studio"), state="readonly", textvariable=self.settings_ui_var).grid(row=0, column=1, sticky="w")
            self._labeled_entry(form, 1, "Domyślny output", self.settings_output_var, True)
            ttk.Label(form, text="Rozmiar części MiB").grid(row=2, column=0, sticky="w", pady=6)
            ttk.Spinbox(form, from_=1, to=102400, textvariable=self.settings_part_var, width=12).grid(row=2, column=1, sticky="w")
            ttk.Label(form, text="Kompresja 0..9").grid(row=3, column=0, sticky="w", pady=6)
            ttk.Spinbox(form, from_=0, to=9, textvariable=self.settings_compression_var, width=12).grid(row=3, column=1, sticky="w")
            ttk.Button(form, text="Zapisz ustawienia", command=self.save_user_settings).grid(row=4, column=1, sticky="w", pady=18)

        def save_user_settings(self) -> None:
            self.settings.update(
                {
                    "ui_mode": self.settings_ui_var.get(),
                    "output_root": self.settings_output_var.get().strip(),
                    "part_size_mib": int(self.settings_part_var.get()),
                    "compression_level": int(self.settings_compression_var.get()),
                }
            )
            self.settings = save_settings(self.settings)
            self.status_var.set("Ustawienia zapisane")

        def _build_config(self) -> None:
            frame = self.pages["Konfiguracja"]
            self._title(frame, "Konfiguracja", "Stan techniczny generatora i dostępne funkcje.")
            self.config_text = tk.Text(frame, state="disabled")
            self.config_text.pack(fill="both", expand=True)

        def _refresh_config(self) -> None:
            self._set_text(self.config_text, json.dumps(config_report(), ensure_ascii=False, indent=2))

        def _build_info(self) -> None:
            frame = self.pages["Informacje"]
            self._title(frame, "Informacje", f"{GENERATOR_TITLE} v{GENERATOR_VERSION}")
            ttk.Label(
                frame,
                text=(
                    "Cel: wierne pakowanie folderu Jaźni w trzech profilach: SYSTEM, MEMORY i SYSTEM+MEMORY.\n\n"
                    "Transport: jeden standardowy ZIP64 albo jeden logiczny ZIP podzielony binarnie na części "
                    "np. po 450 MiB. Każda część oraz cały logiczny ZIP mają SHA-256.\n\n"
                    "Trzy interfejsy korzystają z tego samego core: tekstowy, terminalowy TUI i okienkowe UI Studio.\n\n"
                    "Poza zakresem: dependency bundle, wheelhouse, wybór platformy i przenośny Python."
                ),
                wraplength=820,
                justify="left",
            ).pack(anchor="w")

        def _progress_from_worker(self, event: ProgressEvent) -> None:
            self.events.put(("progress", event))

        def _start_worker(self, operation: Callable[[], Any], result_widget: Any | None = None) -> None:
            if self.worker is not None and self.worker.is_alive():
                messagebox.showwarning("Generator", "Inna operacja jest jeszcze aktywna.")
                return
            self.cancel_event = threading.Event()
            self.cancel_button.configure(state="normal")
            self.progress_var.set(0)
            self.status_var.set("Praca...")
            def target() -> None:
                try:
                    result = operation()
                    self.events.put(("done", (result, result_widget)))
                except Exception as exc:
                    self.events.put(("error", f"{type(exc).__name__}: {exc}"))
            self.worker = threading.Thread(target=target, name="jazn-pack-worker", daemon=True)
            self.worker.start()

        def cancel_current(self) -> None:
            self.cancel_event.set()
            self.status_var.set("Anulowanie...")

        def _poll_events(self) -> None:
            try:
                while True:
                    kind, payload = self.events.get_nowait()
                    if kind == "progress":
                        event: ProgressEvent = payload
                        self.progress_var.set(event.fraction * 100)
                        self.status_var.set(f"{event.message}: {event.path or ''}".strip())
                    elif kind == "done":
                        result, widget = payload
                        self.cancel_button.configure(state="disabled")
                        self.progress_var.set(100)
                        self.status_var.set("Gotowe")
                        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                        if widget is not None:
                            self._set_text(widget, rendered)
                        messagebox.showinfo("Generator", "Operacja zakończona poprawnie.")
                    elif kind == "error":
                        self.cancel_button.configure(state="disabled")
                        self.status_var.set("Błąd")
                        messagebox.showerror("Generator", str(payload))
            except queue.Empty:
                pass
            self.root.after(100, self._poll_events)

        def run(self) -> int:
            self.root.mainloop()
            return 0

    return StudioApp().run()
