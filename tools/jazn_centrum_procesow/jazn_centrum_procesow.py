
from __future__ import annotations

import base64
import json
import os
import queue
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import (
    Tk, Toplevel, Text, StringVar, END, BOTH, X, LEFT, RIGHT,
    messagebox, filedialog, simpledialog
)
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

WIN = os.name == "nt"
CONFIG_PATH = Path.home() / ".jazn_centrum_procesow.json"


@dataclass(frozen=True)
class Job:
    key: str
    group: str
    title: str
    kind: str
    args: tuple[str, ...] = ()


JOBS = [
    Job("status", "Jaźń", "Status runtime", "jazn",
        ("status", "--json")),
    Job("preflight", "Jaźń", "Host preflight", "jazn",
        ("host-preflight", "--json")),
    Job("daemon", "Jaźń", "Uruchom daemon", "jazn",
        ("start",)),
    Job("adapter", "Jaźń", "Status adaptera LLM", "jazn",
        ("--model-adapter-status",)),
    Job("ollama_app", "Ollama", "Uruchom aplikację", "app"),
    Job("ollama_serve", "Ollama", "Uruchom serwer CLI", "ollama",
        ("serve",)),
    Job("ollama_list", "Ollama", "Lista modeli", "ollama",
        ("list",)),
    Job("ollama_api", "Ollama", "Sprawdź API / modele", "api"),
    Job("ollama_generate", "Ollama", "Test generowania", "generate"),
    Job("ollama_app_log", "Ollama", "Log aplikacji", "tail",
        ("app.log",)),
    Job("ollama_server_log", "Ollama", "Log serwera", "tail",
        ("server.log",)),
    Job("mcp_check", "MCP", "Sprawdź punkt wejścia", "mcp_check"),
    Job("mcp_help", "MCP", "Pomoc tunnel_bootstrap", "mcp_help"),
]

SECRET_PATTERNS = [
    re.compile(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"
    ),
    re.compile(
        r'(?i)((?:token|password|secret|api[_-]?key)'
        r'["\']?\s*[:=]\s*["\']?)[^\s,;"\']{8,}'
    ),
]


def redact(value: str) -> str:
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(r"\1[UKRYTO]", value)
    return value


def quote_ps(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def ps_call(argv: list[str]) -> str:
    return "& " + " ".join(quote_ps(v) for v in argv)


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port),
                                      timeout=0.35):
            return True
    except OSError:
        return False


def defaults() -> dict[str, str]:
    if WIN:
        root = Path(r"D:\.AI\jazn_latka_master")
        preferred = Path(r"D:\.AI\.venv\Scripts\python.exe")
        python = str(preferred if preferred.is_file()
                     else shutil.which("python") or sys.executable)
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        ollama = local / "Programs" / "Ollama" / "ollama.exe"
        app = local / "Programs" / "Ollama" / "ollama app.exe"
        logs = local / "Ollama"
    else:
        root = Path.home() / "jazn_latka_master"
        python = sys.executable
        ollama = Path(shutil.which("ollama") or "ollama")
        app = Path("ollama")
        logs = Path.home() / ".ollama" / "logs"

    return {
        "root": str(root),
        "python": python,
        "ollama": str(ollama),
        "ollama_app": str(app),
        "ollama_logs": str(logs),
        "model": "gemma3:latest",
    }


def load_config() -> dict[str, str]:
    config = defaults()
    if CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            config.update({
                key: value for key, value in data.items()
                if key in config and isinstance(value, str)
            })
        except (OSError, ValueError):
            pass
    return config


def make_script(job: Job, cfg: dict[str, str]) -> str:
    root = Path(cfg["root"])
    python = cfg["python"]
    mcp = root / "latka_jazn" / "mcp" / "tunnel_bootstrap.py"

    if job.kind == "jazn":
        argv = [python, "-X", "utf8",
                str(root / "run.py"), *job.args]
    elif job.kind == "ollama":
        argv = [cfg["ollama"], *job.args]
    elif job.kind == "mcp_help":
        argv = [python, "-X", "utf8", str(mcp), "--help"]
    elif job.kind == "custom":
        argv = list(job.args)
    else:
        argv = []

    if argv:
        if WIN:
            return ps_call(argv) + (
                "; if ($LASTEXITCODE -ne 0) "
                "{ exit $LASTEXITCODE }"
            )
        return "exec " + shlex.join(argv)

    if job.kind == "mcp_check":
        if WIN:
            return (
                f"Test-Path -LiteralPath {quote_ps(str(mcp))}; "
                f"Get-Item -LiteralPath {quote_ps(str(mcp))} "
                "| Select-Object FullName,Length,LastWriteTime"
            )
        return f"test -f {shlex.quote(str(mcp))} && ls -l " \
               + shlex.quote(str(mcp))

    if job.kind == "app":
        if WIN:
            return (
                f"Start-Process -FilePath "
                f"{quote_ps(cfg['ollama_app'])}; "
                "Write-Output 'Wysłano polecenie uruchomienia Ollama.'"
            )
        return "echo 'Użyj profilu Ollama: Serwer CLI'"

    if job.kind == "tail":
        path = Path(cfg["ollama_logs"]) / job.args[0]
        if WIN:
            return (
                f"Get-Content -LiteralPath "
                f"{quote_ps(str(path))} -Tail 80 -Wait"
            )
        return "exec tail -n 80 -F " + shlex.quote(str(path))

    if job.kind == "api":
        if WIN:
            return (
                "Invoke-RestMethod -TimeoutSec 7 "
                "-Uri 'http://127.0.0.1:11434/api/tags' "
                "| ConvertTo-Json -Depth 7"
            )
        return "curl -fsS http://127.0.0.1:11434/api/tags"

    if job.kind == "generate":
        payload = json.dumps({
            "model": cfg["model"],
            "prompt": "Odpowiedz jednym zdaniem po polsku: czy działasz?",
            "stream": False,
        }, ensure_ascii=False)

        if WIN:
            return (
                f"$body = {quote_ps(payload)}; "
                "$result = Invoke-RestMethod "
                "-Uri 'http://127.0.0.1:11434/api/generate' "
                "-Method Post -TimeoutSec 180 "
                "-ContentType 'application/json; charset=utf-8' "
                "-Body ([Text.Encoding]::UTF8.GetBytes($body)); "
                "$result | Select-Object model,response,done "
                "| Format-List | Out-String"
            )
        return (
            "curl -fsS --max-time 180 "
            "-H 'Content-Type: application/json' "
            "-d " + shlex.quote(payload) + " "
            "http://127.0.0.1:11434/api/generate"
        )

    raise ValueError(f"Nieobsługiwane zadanie: {job.kind}")


def shell_argv(script: str) -> list[str]:
    if WIN:
        encoding = base64.b64encode(
            script.encode("utf-16le")
        ).decode("ascii")
        header = (
            "$ErrorActionPreference='Stop'; "
            "[Console]::OutputEncoding="
            "[Text.UTF8Encoding]::new($false); "
            "$OutputEncoding=[Console]::OutputEncoding; "
        )
        encoding = base64.b64encode(
            (header + script).encode("utf-16le")
        ).decode("ascii")
        return [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoding,
        ]
    return ["/bin/bash", "--noprofile", "--norc", "-lc", script]


class ProcessWindow:
    def __init__(self, app: "Application", job: Job):
        self.app = app
        self.job = job
        self.proc: subprocess.Popen | None = None
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.history = deque(maxlen=2500)

        self.window = Toplevel(app.root)
        self.window.title(f"Jaźń — {job.title}")
        self.window.geometry("850x540")

        top = ttk.Frame(self.window, padding=10)
        top.pack(fill=X)

        self.status_var = StringVar(value="Nieuruchomiony")
        ttk.Label(top, text=job.title,
                  font=("Segoe UI", 12, "bold")).pack(side=LEFT)
        ttk.Label(top, textvariable=self.status_var).pack(side=RIGHT)

        buttons = ttk.Frame(self.window, padding=(10, 0))
        buttons.pack(fill=X)

        ttk.Button(buttons, text="Uruchom",
                   command=self.start).pack(side=LEFT, padx=3)
        ttk.Button(buttons, text="Zatrzymaj",
                   command=self.stop).pack(side=LEFT, padx=3)
        ttk.Button(buttons, text="Zapisz log",
                   command=self.save_log).pack(side=LEFT, padx=3)
        ttk.Button(buttons, text="Wyczyść widok",
                   command=self.clear).pack(side=LEFT, padx=3)

        self.text = ScrolledText(
            self.window, font=("Consolas", 10),
            wrap="word", background="#17191d",
            foreground="#e2e7eb", insertbackground="white"
        )
        self.text.pack(fill=BOTH, expand=True, padx=10, pady=10)

        ttk.Label(
            self.window,
            text="Zamknięcie okna logów nie kończy procesu. "
                 "Zatrzymaj działa tylko na procesach uruchomionych "
                 "przez Centrum.",
            padding=(10, 0, 10, 10)
        ).pack(fill=X)

        self.window.protocol("WM_DELETE_WINDOW", self.window.withdraw)
        self.window.after(100, self.drain)

    def show(self):
        self.window.deiconify()
        self.window.lift()

    def append(self, label: str, message: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        line = redact(f"[{stamp}] [{label}] {message.rstrip()}")
        self.history.append(line)
        self.text.insert(END, line + "\n")
        self.text.see(END)

        if int(self.text.index("end-1c").split(".")[0]) > 2800:
            self.text.delete("1.0", "350.0")

    def set_state(self, state: str):
        self.status_var.set(state)
        self.app.tree.set(self.job.key, "state", state)

    def validate_start(self) -> bool:
        if not Path(self.app.cfg["root"]).is_dir():
            messagebox.showerror(
                "Nie znaleziono Jaźni",
                "Sprawdź katalog Jaźni w Ustawieniach.",
                parent=self.window
            )
            return False

        if self.job.key == "daemon" and port_open(8787):
            self.append(
                "OCHRONA",
                "Port 8787 już nasłuchuje. Nie uruchamiam "
                "drugiego daemona. Użyj Status runtime."
            )
            return False

        if self.job.key in ("ollama_app", "ollama_serve") \
                and port_open(11434):
            self.append(
                "OCHRONA",
                "API Ollamy jest już dostępne. "
                "Nie uruchamiam drugiej instancji."
            )
            return False

        if self.job.kind == "tail":
            path = Path(self.app.cfg["ollama_logs"]) / self.job.args[0]
            if not path.is_file():
                self.append("BŁĄD", f"Brak pliku logów: {path}")
                return False

        return True

    def start(self):
        if self.proc is not None and self.proc.poll() is None:
            self.append("INFO", "Ten proces już działa.")
            return

        if not self.validate_start():
            return

        try:
            command = shell_argv(make_script(self.job, self.app.cfg))
            options = {
                "cwd": self.app.cfg["root"],
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "bufsize": 1,
            }
            if WIN:
                options["creationflags"] = (
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) |
                    getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
            else:
                options["start_new_session"] = True

            self.proc = subprocess.Popen(command, **options)
        except (OSError, ValueError) as exc:
            self.append("BŁĄD", str(exc))
            self.set_state("Błąd startu")
            return

        proc = self.proc
        self.append("START", f"PID={proc.pid}; zadanie={self.job.key}")
        self.set_state(f"Działa (PID {proc.pid})")

        for name, stream in (
            ("OUT", proc.stdout),
            ("ERR", proc.stderr)
        ):
            threading.Thread(
                target=self.read_stream,
                args=(name, stream),
                daemon=True
            ).start()

        threading.Thread(
            target=self.wait_for_exit,
            args=(proc,),
            daemon=True
        ).start()

    def read_stream(self, name, stream):
        try:
            for line in stream:
                self.events.put((name, line))
        except (OSError, ValueError) as exc:
            self.events.put(("BŁĄD", str(exc)))
        finally:
            stream.close()

    def wait_for_exit(self, proc):
        code = proc.wait()
        self.events.put(("EXIT", str(code)))

    def drain(self):
        for _ in range(300):
            try:
                kind, message = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "EXIT":
                self.append("KONIEC", f"Kod zakończenia: {message}")
                self.set_state(f"Zakończony ({message})")
            else:
                self.append(kind, message)

        self.window.after(120, self.drain)

    def stop(self):
        proc = self.proc
        if proc is None or proc.poll() is not None:
            self.append("INFO", "Brak aktywnego procesu do zatrzymania.")
            return

        if not messagebox.askyesno(
            "Zatrzymać zadanie?",
            f"Zatrzymać proces {self.job.title} (PID {proc.pid})?\n"
            "Nie dotyczy to innych, wcześniej działających usług.",
            parent=self.window
        ):
            return

        try:
            if WIN:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True, timeout=8, check=False
                )
            else:
                os.killpg(proc.pid, signal.SIGTERM)
            self.append("STOP", "Wysłano żądanie zakończenia.")
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.append("BŁĄD", f"Zatrzymanie: {exc}")

    def clear(self):
        self.text.delete("1.0", END)
        self.history.clear()

    def save_log(self):
        path = filedialog.asksaveasfilename(
            parent=self.window,
            defaultextension=".log",
            filetypes=[("Dzienniki", "*.log"), ("Tekst", "*.txt")]
        )
        if path:
            try:
                Path(path).write_text(
                    "\n".join(self.history) + "\n",
                    encoding="utf-8"
                )
            except OSError as exc:
                messagebox.showerror("Błąd zapisu", str(exc))


class Application:
    def __init__(self):
        self.root = Tk()
        self.root.title("Jaźń — Centrum Procesów 0.1")
        self.root.geometry("1000x600")
        self.cfg = load_config()
        self.jobs = {job.key: job for job in JOBS}
        self.windows: dict[str, ProcessWindow] = {}

        header = ttk.Frame(self.root, padding=15)
        header.pack(fill=X)
        ttk.Label(
            header, text="JAŹŃ  /  CENTRUM PROCESÓW",
            font=("Segoe UI", 17, "bold")
        ).pack(side=LEFT)
        ttk.Button(
            header, text="Ustawienia",
            command=self.settings
        ).pack(side=RIGHT)

        ttk.Label(
            self.root,
            text="Każdy proces ma osobne okno, strumień logów i "
                 "własny cykl uruchamiania.",
            padding=(15, 0, 15, 12)
        ).pack(fill=X)

        frame = ttk.Frame(self.root, padding=(15, 0, 15, 8))
        frame.pack(fill=BOTH, expand=True)

        self.tree = ttk.Treeview(
            frame,
            columns=("group", "title", "state"),
            show="headings", selectmode="browse"
        )
        for key, label, width in (
            ("group", "Moduł", 120),
            ("title", "Zadanie", 480),
            ("state", "Stan", 210)
        ):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")

        self.tree.pack(fill=BOTH, expand=True)

        for job in JOBS:
            self.tree.insert(
                "", END, iid=job.key,
                values=(job.group, job.title, "Nieuruchomiony")
            )

        self.tree.bind("<Double-1>", lambda _: self.open_selected())

        actions = ttk.Frame(self.root, padding=12)
        actions.pack(fill=X)

        ttk.Button(
            actions, text="Otwórz logi",
            command=self.open_selected
        ).pack(side=LEFT, padx=4)
        ttk.Button(
            actions, text="Uruchom zaznaczone",
            command=self.start_selected
        ).pack(side=LEFT, padx=4)
        ttk.Button(
            actions, text="Dodaj własne polecenie",
            command=self.add_job
        ).pack(side=LEFT, padx=4)

        ttk.Label(
            self.root,
            text="MCP stdio jest uruchamiany przez ChatGPT Desktop. "
                 "Centrum sprawdza jego punkt wejścia, ale nie "
                 "przechwytuje protokołu JSON-RPC.",
            padding=(15, 0, 15, 12)
        ).pack(fill=X)

        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

    def selected(self):
        chosen = self.tree.selection()
        return self.jobs.get(chosen[0]) if chosen else None

    def open_job(self, job: Job):
        if job.key not in self.windows:
            self.windows[job.key] = ProcessWindow(self, job)
        self.windows[job.key].show()
        return self.windows[job.key]

    def open_selected(self):
        job = self.selected()
        if job:
            self.open_job(job)

    def start_selected(self):
        job = self.selected()
        if job:
            self.open_job(job).start()

    def add_job(self):
        title = simpledialog.askstring(
            "Nowe zadanie", "Nazwa zadania:", parent=self.root
        )
        if not title:
            return

        exe = simpledialog.askstring(
            "Nowe zadanie",
            "Program (pełna ścieżka lub nazwa polecenia):",
            parent=self.root
        )
        if not exe:
            return

        raw = simpledialog.askstring(
            "Argumenty",
            'Argumenty jako lista JSON, np. ["--version"]:',
            initialvalue="[]", parent=self.root
        )
        if raw is None:
            return

        try:
            args = json.loads(raw)
            if not isinstance(args, list) or not all(
                isinstance(v, str) for v in args
            ):
                raise ValueError("Podaj tablicę napisów JSON.")
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Argumenty", str(exc))
            return

        if not messagebox.askyesno(
            "Potwierdź polecenie",
            "To polecenie będzie mogło wykonywać działania "
            "z uprawnieniami Twojego użytkownika.\n"
            "Dodawać należy wyłącznie zaufane programy.\n\n"
            f"Program: {exe}\nArgumenty: {args}",
            parent=self.root
        ):
            return

        key = f"custom_{len(self.jobs)}"
        job = Job(key, "Własne", title, "custom",
                  (exe, *args))
        self.jobs[key] = job
        self.tree.insert(
            "", END, iid=key,
            values=(job.group, job.title, "Nieuruchomiony")
        )

    def settings(self):
        window = Toplevel(self.root)
        window.title("Ustawienia Centrum")
        window.geometry("750x380")

        fields = [
            ("root", "Katalog Jaźni"),
            ("python", "Interpreter Python"),
            ("ollama", "CLI Ollama"),
            ("ollama_app", "Aplikacja Ollama"),
            ("ollama_logs", "Katalog logów Ollamy"),
            ("model", "Model Ollama"),
        ]
        vars = {}

        for i, (key, label) in enumerate(fields):
            ttk.Label(
                window, text=label
            ).grid(row=i, column=0, sticky="w", padx=12, pady=9)
            variable = StringVar(value=self.cfg[key])
            vars[key] = variable
            ttk.Entry(
                window, textvariable=variable, width=75
            ).grid(row=i, column=1, sticky="ew", padx=12)

        window.columnconfigure(1, weight=1)

        def save():
            self.cfg.update({
                key: var.get().strip()
                for key, var in vars.items()
            })
            try:
                CONFIG_PATH.write_text(
                    json.dumps(self.cfg, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
                window.destroy()
            except OSError as exc:
                messagebox.showerror("Ustawienia", str(exc))

        ttk.Button(
            window, text="Zapisz",
            command=save
        ).grid(row=len(fields), column=1, sticky="e", padx=12)

    def exit_app(self):
        active = [
            pane for pane in self.windows.values()
            if pane.proc is not None and pane.proc.poll() is None
        ]
        if active:
            messagebox.showwarning(
                "Aktywne zadania",
                "W Centrum nadal działają uruchomione zadania.\n"
                "Zatrzymaj je w ich oknach, a następnie zamknij aplikację.\n"
                "Nie zatrzymano żadnego zewnętrznego daemona."
            )
            return
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Application().run()
