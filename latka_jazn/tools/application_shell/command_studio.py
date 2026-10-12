from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import shlex
import subprocess
import sys
import threading
from typing import Any, Sequence

from .diagnostics import DiagnosticsHub
from .settings import ShellSettings, load_shell_settings, save_shell_settings


@dataclass(frozen=True, slots=True)
class CommandItem:
    name: str
    label: str
    description: str
    example_args: str = ""


@dataclass(frozen=True, slots=True)
class CommandStudioSpec:
    app_id: str
    app_name: str
    version: str
    description: str
    command_prefix: tuple[str, ...]
    commands: tuple[CommandItem, ...]
    state_dir: Path
    working_dir: Path | None = None
    settings_filename: str = "local_ui_settings.json"
    default_ui: str = "window"

    @property
    def settings_path(self) -> Path:
        return Path(self.state_dir) / self.settings_filename


def _split_args(raw: str) -> list[str]:
    if not raw.strip():
        return []
    if os.name == "nt":
        values = shlex.split(raw, posix=False)
        return [
            value[1:-1]
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}
            else value
            for value in values
        ]
    return shlex.split(raw, posix=True)


def _command(spec: CommandStudioSpec, item: CommandItem, raw_args: str) -> list[str]:
    return [*spec.command_prefix, item.name, *_split_args(raw_args)]


def _run_once(
    spec: CommandStudioSpec,
    command: Sequence[str],
    diagnostics: DiagnosticsHub,
    *,
    timeout: int | None = None,
) -> tuple[int, str]:
    args = [*map(str, command)]
    diagnostics.record("INFO", "Start komendy", command=args)
    try:
        completed = subprocess.run(
            args,
            cwd=Path(spec.working_dir or Path.cwd()).resolve(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        output = f"{stdout}{stderr}\nTIMEOUT po {timeout}s\n"
        diagnostics.record("ERROR", "Timeout komendy", command=args, timeout=timeout)
        return 124, output
    diagnostics.record(
        "INFO" if completed.returncode == 0 else "ERROR",
        "Koniec komendy",
        command=args,
        returncode=completed.returncode,
    )
    return int(completed.returncode), completed.stdout


def load_command_studio_settings(spec: CommandStudioSpec) -> ShellSettings:
    return load_shell_settings(spec.settings_path, defaults=ShellSettings(ui_mode=spec.default_ui))


def _save_settings(spec: CommandStudioSpec, value: ShellSettings) -> ShellSettings:
    return save_shell_settings(spec.settings_path, value)


def _settings_menu(spec: CommandStudioSpec, diagnostics: DiagnosticsHub) -> ShellSettings:
    current = load_command_studio_settings(spec)
    while True:
        print("\nUSTAWIENIA")
        print(f"1. Domyślny UI: {current.ui_mode}")
        print(f"2. Splash: {current.splash_enabled}")
        print(f"3. Diagnostyka: {current.diagnostics_enabled}")
        print(f"4. Limit diagnostyki: {current.diagnostics_limit}")
        print(f"5. Log level: {current.log_level}")
        print("0. Powrót")
        raw = input("Wybór: ").strip()
        if raw in {"", "0"}:
            return current
        payload = current.to_dict()
        if raw == "1":
            value = input("text / tui / window: ").strip().lower()
            if value in {"text", "tui", "window"}:
                payload["ui_mode"] = value
        elif raw == "2":
            payload["splash_enabled"] = not current.splash_enabled
        elif raw == "3":
            payload["diagnostics_enabled"] = not current.diagnostics_enabled
        elif raw == "4":
            try:
                payload["diagnostics_limit"] = int(input("Limit 50..5000: ").strip())
            except ValueError:
                print("Niepoprawna liczba.")
                continue
        elif raw == "5":
            value = input("DEBUG / INFO / WARNING / ERROR: ").strip().upper()
            if value in {"DEBUG", "INFO", "WARNING", "ERROR"}:
                payload["log_level"] = value
        current = _save_settings(spec, ShellSettings.from_mapping(payload, defaults=current))
        diagnostics.reconfigure(
            enabled=current.diagnostics_enabled,
            limit=current.diagnostics_limit,
            minimum_level=current.log_level,
        )
        diagnostics.record("INFO", "Zmieniono ustawienia aplikacji", settings=current.to_dict())


def run_text_studio(spec: CommandStudioSpec, diagnostics: DiagnosticsHub) -> int:
    diagnostics.record("INFO", "Uruchomiono tryb text")
    while True:
        print(f"\n{spec.app_name} {spec.version}")
        print("=" * 76)
        print("STRONA GŁÓWNA")
        print(spec.description)
        print("\n1. Operacje")
        print("2. Ustawienia")
        print("3. Diagnostyka / log")
        print("0. Wyjście")
        choice = input("\nWybór: ").strip()
        if choice == "0":
            return 0
        if choice == "2":
            _settings_menu(spec, diagnostics)
            continue
        if choice == "3":
            print(f"\nLog: {diagnostics.log_path}\n")
            print(diagnostics.text(limit=100))
            input("\nEnter — powrót...")
            continue
        if choice != "1":
            continue
        print("\nOPERACJE")
        for idx, item in enumerate(spec.commands, 1):
            print(f"{idx}. {item.label} — {item.description}")
        print("0. Powrót")
        raw_index = input("Wybór: ").strip()
        if not raw_index.isdigit():
            continue
        index = int(raw_index)
        if index == 0:
            continue
        if not (1 <= index <= len(spec.commands)):
            continue
        item = spec.commands[index - 1]
        suffix = f" [{item.example_args}]" if item.example_args else ""
        raw_args = input(f"Argumenty po '{item.name}'{suffix}: ").strip() or item.example_args
        command = _command(spec, item, raw_args)
        code, output = _run_once(spec, command, diagnostics)
        print(f"\nRETURN CODE: {code}\n{output}")
        input("\nEnter — powrót...")


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _read_key() -> str:
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in {"\x00", "\xe0"}:
            code = msvcrt.getwch()
            return {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT"}.get(code, code)
        if ch in {"\r", "\n"}:
            return "ENTER"
        if ch == "\x03":
            return "CTRL_C"
        if ch == "\x1b":
            return "ESC"
        return ch

    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x03":
            return "CTRL_C"
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            return {"[A": "UP", "[B": "DOWN", "[D": "LEFT", "[C": "RIGHT"}.get(seq, "ESC")
        if ch in {"\r", "\n"}:
            return "ENTER"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _box(text: str, width: int) -> str:
    return "║ " + text.replace("\t", "    ")[: width - 4].ljust(width - 4) + " ║"


def run_tui_studio(spec: CommandStudioSpec, diagnostics: DiagnosticsHub) -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        diagnostics.record("WARNING", "Brak TTY; przejście TUI -> text")
        return run_text_studio(spec, diagnostics)

    pages = ("GŁÓWNA", "OPERACJE", "USTAWIENIA", "DIAGNOSTYKA")
    page = 0
    selected = 0
    status = "Gotowe"
    last = "Brak wyniku."
    width = 112
    diagnostics.record("INFO", "Uruchomiono TUI")

    while True:
        _clear()
        print("╔" + "═" * (width - 2) + "╗")
        print(_box(f"{spec.app_name} {spec.version}", width))
        print(_box("  ".join(f"[{'●' if i == page else ' '}] {p}" for i, p in enumerate(pages)), width))
        print("╠" + "═" * (width - 2) + "╣")
        if page == 0:
            lines = ["STRONA GŁÓWNA", "", spec.description, "", "2 / → — operacje", "3 — ustawienia", "4 — diagnostyka"]
        elif page == 1:
            lines = ["OPERACJE", ""]
            lines += [
                ("▶ " if i == selected else "  ") + f"{i + 1}. {item.label} — {item.description}"
                for i, item in enumerate(spec.commands)
            ]
            lines += ["", "Enter — uruchom zaznaczoną operację", "", "Ostatni wynik:", *last.splitlines()[-12:]]
        elif page == 2:
            value = load_command_studio_settings(spec)
            lines = ["USTAWIENIA", "", *json.dumps(value.to_dict(), ensure_ascii=False, indent=2).splitlines(), "", "Enter / E — edytuj"]
        else:
            lines = ["DIAGNOSTYKA / LOG", "", f"Plik: {diagnostics.log_path}", "", *diagnostics.text(limit=25).splitlines()]

        for line in lines[:26]:
            print(_box(line, width))
        for _ in range(max(0, 26 - len(lines))):
            print(_box("", width))
        print("╠" + "═" * (width - 2) + "╣")
        print(_box(f"{status} | 1-4 strony • ←/→ • ↑/↓ • q/Ctrl+C", width))
        print("╚" + "═" * (width - 2) + "╝")

        key = _read_key()
        if key in {"q", "Q", "ESC", "CTRL_C"}:
            diagnostics.record("INFO", "Zamknięto TUI", reason=key)
            return 130 if key == "CTRL_C" else 0
        if key in {"1", "2", "3", "4"}:
            page = int(key) - 1
            continue
        if key == "RIGHT":
            page = (page + 1) % len(pages)
            continue
        if key == "LEFT":
            page = (page - 1) % len(pages)
            continue
        if page == 1 and spec.commands:
            if key in {"UP", "k", "K"}:
                selected = (selected - 1) % len(spec.commands)
            elif key in {"DOWN", "j", "J"}:
                selected = (selected + 1) % len(spec.commands)
            elif key == "ENTER":
                item = spec.commands[selected]
                _clear()
                print(f"{spec.app_name} — {item.label}\n{'=' * 72}")
                suffix = f" [{item.example_args}]" if item.example_args else ""
                raw = input(f"Argumenty po '{item.name}'{suffix}: ").strip() or item.example_args
                command = _command(spec, item, raw)
                try:
                    code, last = _run_once(spec, command, diagnostics)
                    status = f"{item.name}: returncode={code}"
                except KeyboardInterrupt:
                    status = f"{item.name}: przerwano"
                    diagnostics.record("WARNING", "Przerwano komendę TUI", command=item.name)
        elif page == 2 and key in {"ENTER", "e", "E"}:
            _clear()
            _settings_menu(spec, diagnostics)
            status = "Ustawienia zapisane"


def run_window_studio(spec: CommandStudioSpec, diagnostics: DiagnosticsHub) -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError as exc:
        raise RuntimeError("Tryb window wymaga tkinter/Tk") from exc

    class App:
        def __init__(self) -> None:
            self.root = tk.Tk()
            self.root.title(f"{spec.app_name} {spec.version}")
            self.root.geometry("1100x720")
            self.root.minsize(900, 600)
            self.pages: dict[str, ttk.Frame] = {}
            self.process: subprocess.Popen[str] | None = None
            self.events: queue.Queue[tuple[str, str]] = queue.Queue()
            self.worker: threading.Thread | None = None
            self.status = tk.StringVar(value="Gotowe")
            self._build()
            self.root.protocol("WM_DELETE_WINDOW", self.close)
            self.root.after(100, self._poll)
            diagnostics.record("INFO", "Uruchomiono okno")

        def _build(self) -> None:
            outer = ttk.Frame(self.root, padding=10)
            outer.pack(fill="both", expand=True)
            sidebar = ttk.Frame(outer, width=190)
            sidebar.pack(side="left", fill="y", padx=(0, 10))
            content = ttk.Frame(outer)
            content.pack(side="left", fill="both", expand=True)
            ttk.Label(sidebar, text=spec.app_name.upper(), font=("Segoe UI", 14, "bold"), wraplength=180).pack(anchor="w", pady=(4, 16))
            for name in ("Główna", "Operacje", "Ustawienia", "Diagnostyka"):
                ttk.Button(sidebar, text=name, command=lambda n=name: self.show(n)).pack(fill="x", pady=3)
                frame = ttk.Frame(content, padding=14)
                frame.grid(row=0, column=0, sticky="nsew")
                self.pages[name] = frame
            content.rowconfigure(0, weight=1)
            content.columnconfigure(0, weight=1)
            self._home()
            self._operations()
            self._settings_page()
            self._diagnostics_page()
            ttk.Label(self.root, textvariable=self.status, anchor="w", padding=(10, 4)).pack(side="bottom", fill="x")
            self.show("Główna")

        def _title(self, frame: Any, title: str, subtitle: str) -> None:
            ttk.Label(frame, text=title, font=("Segoe UI", 19, "bold")).pack(anchor="w")
            ttk.Label(frame, text=subtitle, wraplength=800).pack(anchor="w", pady=(2, 14))
            ttk.Separator(frame).pack(fill="x", pady=(0, 14))

        def _home(self) -> None:
            frame = self.pages["Główna"]
            self._title(frame, spec.app_name, spec.description)
            ttk.Label(
                frame,
                text=f"Wersja: {spec.version}\nTryby: text / tui / window\nKomendy domenowe: {len(spec.commands)}",
                justify="left",
            ).pack(anchor="w")
            ttk.Button(frame, text="Przejdź do operacji", command=lambda: self.show("Operacje")).pack(anchor="w", pady=18)

        def _operations(self) -> None:
            frame = self.pages["Operacje"]
            self._title(frame, "Operacje", "Uruchamianie komend w izolowanym subprocessie z widocznym wyjściem i przyciskiem STOP.")
            top = ttk.Frame(frame)
            top.pack(fill="x")
            first = spec.commands[0] if spec.commands else CommandItem("", "", "")
            self.command_var = tk.StringVar(value=first.name)
            self.args_var = tk.StringVar(value=first.example_args)
            self.combo = ttk.Combobox(top, state="readonly", values=[item.name for item in spec.commands], textvariable=self.command_var, width=28)
            self.combo.pack(side="left")
            self.combo.bind("<<ComboboxSelected>>", self._selection_changed)
            ttk.Entry(top, textvariable=self.args_var).pack(side="left", fill="x", expand=True, padx=8)
            self.run_button = ttk.Button(top, text="URUCHOM", command=self.start)
            self.run_button.pack(side="left")
            self.stop_button = ttk.Button(top, text="STOP", command=self.stop, state="disabled")
            self.stop_button.pack(side="left", padx=(6, 0))
            self.description = ttk.Label(frame, wraplength=820)
            self.description.pack(anchor="w", pady=8)
            self.output = tk.Text(frame, wrap="none", state="disabled")
            self.output.pack(fill="both", expand=True)
            self._selection_changed()

        def _selection_changed(self, _event: Any = None) -> None:
            item = next((x for x in spec.commands if x.name == self.command_var.get()), None)
            if item is not None:
                self.description.configure(text=item.description)
                self.args_var.set(item.example_args)

        def _settings_page(self) -> None:
            frame = self.pages["Ustawienia"]
            self._title(frame, "Ustawienia", "Lokalne ustawienia powłoki aplikacji; nie są danymi runtime Jaźni.")
            value = load_command_studio_settings(spec)
            self.ui_var = tk.StringVar(value=value.ui_mode)
            self.splash_var = tk.BooleanVar(value=value.splash_enabled)
            self.diag_var = tk.BooleanVar(value=value.diagnostics_enabled)
            self.level_var = tk.StringVar(value=value.log_level)
            self.limit_var = tk.StringVar(value=str(value.diagnostics_limit))
            grid = ttk.Frame(frame)
            grid.pack(fill="x")
            grid.columnconfigure(1, weight=1)
            ttk.Label(grid, text="Domyślny interfejs").grid(row=0, column=0, sticky="w", pady=6)
            ttk.Combobox(grid, values=("text", "tui", "window"), state="readonly", textvariable=self.ui_var).grid(row=0, column=1, sticky="w")
            ttk.Checkbutton(grid, text="Ekran startowy", variable=self.splash_var).grid(row=1, column=1, sticky="w", pady=6)
            ttk.Checkbutton(grid, text="Diagnostyka / log", variable=self.diag_var).grid(row=2, column=1, sticky="w", pady=6)
            ttk.Label(grid, text="Limit diagnostyki").grid(row=3, column=0, sticky="w", pady=6)
            ttk.Entry(grid, textvariable=self.limit_var, width=10).grid(row=3, column=1, sticky="w")
            ttk.Label(grid, text="Log level").grid(row=4, column=0, sticky="w", pady=6)
            ttk.Combobox(grid, values=("DEBUG", "INFO", "WARNING", "ERROR"), state="readonly", textvariable=self.level_var).grid(row=4, column=1, sticky="w")
            ttk.Button(grid, text="Zapisz", command=self.save_settings).grid(row=5, column=1, sticky="w", pady=14)

        def save_settings(self) -> None:
            try:
                limit = int(self.limit_var.get())
            except ValueError:
                messagebox.showerror(spec.app_name, "Limit diagnostyki musi być liczbą.")
                return
            saved = _save_settings(
                spec,
                ShellSettings(
                    ui_mode=self.ui_var.get(),
                    splash_enabled=self.splash_var.get(),
                    diagnostics_enabled=self.diag_var.get(),
                    diagnostics_limit=limit,
                    log_level=self.level_var.get(),
                ),
            )
            diagnostics.reconfigure(
                enabled=saved.diagnostics_enabled,
                limit=saved.diagnostics_limit,
                minimum_level=saved.log_level,
            )
            self.status.set(f"Zapisano: {spec.settings_path}")
            diagnostics.record("INFO", "Zapisano ustawienia GUI", settings=saved.to_dict())

        def _diagnostics_page(self) -> None:
            frame = self.pages["Diagnostyka"]
            self._title(frame, "Diagnostyka / log", f"Plik JSONL: {diagnostics.log_path}")
            self.diag_text = tk.Text(frame, state="disabled", wrap="word")
            self.diag_text.pack(fill="both", expand=True)
            ttk.Button(frame, text="Odśwież", command=self.refresh_diagnostics).pack(anchor="e", pady=8)

        def refresh_diagnostics(self) -> None:
            self._set_text(self.diag_text, diagnostics.text(limit=200))

        def show(self, name: str) -> None:
            self.pages[name].tkraise()
            if name == "Diagnostyka":
                self.refresh_diagnostics()

        @staticmethod
        def _set_text(widget: Any, text: str) -> None:
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
            widget.configure(state="disabled")

        def _append(self, text: str) -> None:
            self.output.configure(state="normal")
            self.output.insert("end", text)
            self.output.see("end")
            self.output.configure(state="disabled")

        def start(self) -> None:
            if self.process is not None and self.process.poll() is None:
                messagebox.showwarning(spec.app_name, "Operacja jest już aktywna.")
                return
            item = next((x for x in spec.commands if x.name == self.command_var.get()), None)
            if item is None:
                return
            try:
                command = _command(spec, item, self.args_var.get())
            except ValueError as exc:
                messagebox.showerror(spec.app_name, str(exc))
                return
            self._set_text(self.output, "START: " + " ".join(command) + "\n\n")
            self.status.set("Uruchamianie...")
            self.run_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            diagnostics.record("INFO", "Start komendy GUI", command=command)

            def worker() -> None:
                try:
                    proc = subprocess.Popen(
                        command,
                        cwd=Path(spec.working_dir or Path.cwd()).resolve(),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        shell=False,
                    )
                    self.process = proc
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        self.events.put(("output", line))
                    self.events.put(("done", str(proc.wait())))
                except Exception as exc:
                    self.events.put(("error", f"{type(exc).__name__}: {exc}"))

            self.worker = threading.Thread(target=worker, name=f"{spec.app_id}-worker", daemon=True)
            self.worker.start()

        def stop(self) -> None:
            proc = self.process
            if proc is not None and proc.poll() is None:
                diagnostics.record("WARNING", "Zatrzymanie komendy GUI", pid=proc.pid)
                proc.terminate()
                self.status.set("Zatrzymywanie...")

        def _poll(self) -> None:
            try:
                while True:
                    kind, payload = self.events.get_nowait()
                    if kind == "output":
                        self._append(payload)
                    elif kind == "done":
                        code = int(payload)
                        self.status.set(f"Zakończono: returncode={code}")
                        self.run_button.configure(state="normal")
                        self.stop_button.configure(state="disabled")
                        diagnostics.record("INFO" if code == 0 else "ERROR", "Koniec komendy GUI", returncode=code)
                    else:
                        self.status.set(payload)
                        self._append("\nBŁĄD: " + payload + "\n")
                        self.run_button.configure(state="normal")
                        self.stop_button.configure(state="disabled")
                        diagnostics.record("ERROR", "Błąd workera GUI", error=payload)
            except queue.Empty:
                pass
            self.root.after(100, self._poll)

        def close(self) -> None:
            self.stop()
            diagnostics.record("INFO", "Zamknięto okno")
            try:
                self.root.destroy()
            except tk.TclError:
                pass

        def run(self) -> int:
            try:
                self.root.mainloop()
                return 0
            except KeyboardInterrupt:
                self.close()
                return 130

    return App().run()


def build_diagnostics(spec: CommandStudioSpec) -> DiagnosticsHub:
    settings = load_command_studio_settings(spec)
    return DiagnosticsHub(
        spec.app_id,
        spec.state_dir,
        enabled=settings.diagnostics_enabled,
        limit=settings.diagnostics_limit,
        minimum_level=settings.log_level,
    )
