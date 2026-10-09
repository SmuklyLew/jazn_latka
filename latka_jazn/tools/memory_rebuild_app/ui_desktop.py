from __future__ import annotations

"""Native Windows-oriented cockpit for the canonical Jaźń Memory Rebuild service.

The desktop window is a presentation surface for the same StudioState,
StudioWorkflows, ProjectStore and MemoryRebuildApplicationService that are used
by the TUI. No alternate database or restore engine is introduced.
"""

from collections.abc import Callable, Sequence
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread, current_thread, main_thread
from typing import Any
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from latka_jazn.version import PACKAGE_VERSION_FULL

from .models import DEFAULT_SETTINGS
from .project_store import ProjectStore, default_project_root
from .studio import STUDIO_VERSION, StudioState, _run_test
from .studio_workflows import StudioWorkflows
from .test_spec import TEST_SPECS
from .unified_memory import CANONICAL_DATABASE_NAME, UnifiedMemoryDatabase

BG = "#eef3f8"
SIDEBAR = "#162b40"
SIDEBAR_ACCENT = "#243e55"
INK = "#17324b"
MUTED = "#587083"
WHITE = "#ffffff"
TEAL = "#087e78"
BORDER = "#d9e5ed"

PAGES: tuple[tuple[str, str, str], ...] = (
    ("home", "Pulpit", "Przegląd projektu, wymagane kroki i stan operacyjny"),
    ("projects", "Projekt i źródła", "Projekty, eksporty ChatGPT, dzienniki i pochodzenie danych"),
    ("paths", "Ścieżki i zapis", "Wszystkie wejścia, wyjścia i ustawienia ścieżek w jednym miejscu"),
    ("database", "Baza pamięci", "Jedna baza memory_jazn.sqlite3 i jej weryfikacja"),
    ("import", "Import i migracja", "Kontrolowany import źródeł i legacy SQLite"),
    ("affect", "Ślady afektywne", "Źródłowe deklaracje i modelowane stany z lineage"),
    ("candidates", "Kandydaci L1", "Ręczny przegląd bez automatycznego L2/L3"),
    ("tests", "Testy 00–Final", "Pełny łańcuch protokołów odbudowy"),
    ("rebuild", "Odbudowa", "Preflight, plan, jawnie potwierdzony zapis"),
    ("export", "Finalny eksport", "Eksport ze sprawdzeniem wymaganych dowodów"),
    ("settings", "Ustawienia", "Zasady walidacji, retrieval i bezpieczeństwa"),
    ("diagnostics", "Diagnostyka", "Ścieżki techniczne, status i log operacji"),
)
PAGE_BY_ID = {key: (label, hint) for key, label, hint in PAGES}

PATH_FIELDS = (
    ("source_directory", "Katalog źródeł", "directory", "project"),
    ("target_root", "Katalog odbudowy / staging", "directory", "project"),
    ("database", "Kanoniczna baza memory_jazn.sqlite3", "savefile", "database"),
    ("test04_benchmark", "Prywatny benchmark Test04", "file", "setting"),
    ("test04_acceptance_report", "Raport akceptacji Test04", "file", "setting"),
    ("restart_continuity_report", "Raport ciągłości po restarcie", "file", "setting"),
    ("final_output", "Katalog końcowego eksportu", "directory", "setting"),
)


def project_path_values(project: Any | None, database: Path) -> dict[str, str]:
    """Pure, predictable map between UI fields and canonical project settings."""
    if project is None:
        return {"database": str(database), **{key: "" for key, *_ in PATH_FIELDS if key != "database"}}
    values = {
        "source_directory": str(project.source_directory or ""),
        "target_root": str(project.target_root or ""),
        "database": str(database),
    }
    for key in ("test04_benchmark", "test04_acceptance_report",
                "restart_continuity_report", "final_output"):
        values[key] = str(project.settings.get(key) or "")
    return values


def proposed_path_changes(values: dict[str, str]) -> dict[str, str]:
    """Normalize non-empty paths without creating destinations or deleting source data."""
    normalized: dict[str, str] = {}
    for key, *_ in PATH_FIELDS:
        if key not in values:
            continue
        raw = str(values[key]).strip()
        if key in {"target_root", "database"} and not raw:
            raise ValueError(f"{key}: nie może być pusty.")
        normalized[key] = str(Path(raw).expanduser().resolve()) if raw else ""
    if normalized.get("source_directory") and normalized.get("target_root"):
        source = Path(normalized["source_directory"])
        target = Path(normalized["target_root"])
        if source == target or source in target.parents or target in source.parents:
            raise ValueError("Folder źródeł i katalog odbudowy muszą być rozdzielone.")
    return normalized


class TkStudioDialogs:
    """DialogBackend adapter. Every Tk call is marshalled to the UI thread."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self._requests: Queue[tuple[Callable[[], Any], Event, dict[str, Any]]] = Queue()
        self.root.after(60, self._drain)

    def _drain(self) -> None:
        try:
            for _ in range(15):
                fn, event, result = self._requests.get_nowait()
                try:
                    result["value"] = fn()
                except BaseException as exc:
                    result["exception"] = exc
                finally:
                    event.set()
        except Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(60, self._drain)

    def _on_ui(self, fn: Callable[[], Any]) -> Any:
        if current_thread() is main_thread():
            return fn()
        done, output = Event(), {}
        self._requests.put((fn, done, output))
        done.wait()
        if "exception" in output:
            raise output["exception"]
        return output.get("value")

    def choice(self, title: str, text: str, values: Sequence[tuple[Any, str]], *,
               default: Any = None) -> Any:
        return self._on_ui(lambda: self._pick(title, text, values, default=default, multiple=False))

    def checklist(self, title: str, text: str, values: Sequence[tuple[str, str]], *,
                  default_values: Sequence[str] = ()) -> list[str] | None:
        return self._on_ui(lambda: self._pick(title, text, values, default=list(default_values), multiple=True))

    def _pick(self, title: str, text: str, values: Sequence[tuple[Any, str]], *,
              default: Any, multiple: bool) -> Any:
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("760x540")
        window.minsize(520, 360)
        window.transient(self.root)
        window.configure(bg=WHITE)
        ttk.Label(window, text=title, style="Heading.TLabel").pack(anchor="w", padx=20, pady=(18, 6))
        if text:
            ttk.Label(window, text=text[:2000], style="Note.TLabel", wraplength=690).pack(
                anchor="w", padx=20, pady=(0, 12))
        items = tk.Listbox(window, activestyle="none", font=("Segoe UI", 10),
                           selectmode=(tk.EXTENDED if multiple else tk.BROWSE),
                           borderwidth=0, highlightthickness=1, highlightbackground=BORDER)
        items.pack(expand=True, fill="both", padx=20, pady=4)
        for index, (value, label) in enumerate(values):
            items.insert(tk.END, str(label))
            selected = (value in default) if multiple else (value == default)
            if selected:
                items.selection_set(index)
        response: dict[str, Any] = {"value": None}

        def close(accept: bool) -> None:
            indices = list(items.curselection()) if accept else []
            if accept and indices:
                response["value"] = ([values[i][0] for i in indices] if multiple else values[indices[0]][0])
            elif accept and multiple:
                response["value"] = []
            window.destroy()

        controls = ttk.Frame(window, padding=14)
        controls.pack(fill="x")
        ttk.Button(controls, text="Anuluj", command=lambda: close(False)).pack(side="right", padx=4)
        ttk.Button(controls, text="Wybierz", style="Accent.TButton",
                   command=lambda: close(True)).pack(side="right", padx=4)
        items.bind("<Double-1>", lambda _ev: close(True) if not multiple else None)
        window.protocol("WM_DELETE_WINDOW", lambda: close(False))
        window.grab_set()
        window.wait_window()
        return response["value"]

    def input(self, title: str, text: str, default: str = "") -> str:
        result = self._on_ui(lambda: simpledialog.askstring(title, text, initialvalue=default, parent=self.root))
        return str(result) if result is not None else ""

    def confirm(self, title: str, text: str) -> bool:
        return bool(self._on_ui(lambda: messagebox.askyesno(title, text, parent=self.root)))

    def message(self, title: str, text: str) -> None:
        def display() -> None:
            window = tk.Toplevel(self.root)
            window.title(title)
            window.geometry("820x560")
            window.transient(self.root)
            ttk.Label(window, text=title, style="Heading.TLabel").pack(
                anchor="w", padx=16, pady=12)
            viewer = tk.Text(window, font=("Consolas", 10), wrap="word",
                             bg=WHITE, fg=INK, relief="flat", padx=12, pady=12)
            viewer.insert("1.0", str(text))
            viewer.configure(state="disabled")
            viewer.pack(fill="both", expand=True, padx=16, pady=4)
            ttk.Button(window, text="Zamknij", command=window.destroy).pack(
                anchor="e", padx=16, pady=12)
            window.grab_set()
            window.wait_window()
        self._on_ui(display)


class DesktopWorkspace:
    """All operator views in one Tk window, backed by the canonical service."""

    def __init__(self, root: tk.Tk, *, tool_root: Path, diagnostics: Any,
                 project_root: Path | None = None, project: str | None = None,
                 settings_path: Path | None = None):
        self.root = root
        self.tool_root = tool_root.resolve()
        self.diagnostics = diagnostics
        self._busy = False
        self._updates: Queue[tuple[bool, Any, str]] = Queue()
        self._page = "home"
        self._fields: dict[str, tk.StringVar] = {}
        self._settings_fields: dict[str, tk.Variable] = {}
        self.state = StudioState(
            database=Path.home() / ".jazn" / CANONICAL_DATABASE_NAME,
            project_root=project_root, project=project, tool_root=self.tool_root,
            settings_path=settings_path,
        )
        self.dialogs = TkStudioDialogs(root)
        self.state.bind_dialogs(self.dialogs)
        self.workflows = StudioWorkflows(self.state, self.dialogs)
        self._configure_theme()
        self.root.title("Jaźń — Studio pamięci")
        self.root.geometry("1280x820")
        self.root.minsize(990, 620)
        self.root.configure(bg=BG)
        self._layout()
        self.open_page("home")
        self.root.after(80, self._check_updates)

    def _configure_theme(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=BG, foreground=INK)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=WHITE)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("Heading.TLabel", background=BG, foreground=INK, font=("Segoe UI Semibold", 19))
        style.configure("Section.TLabel", background=BG, foreground=INK, font=("Segoe UI Semibold", 12))
        style.configure("Note.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=WHITE, foreground=INK)
        style.configure("CardNote.TLabel", background=WHITE, foreground=MUTED)
        style.configure("TButton", padding=(12, 9))
        style.configure("Accent.TButton", background=TEAL, foreground=WHITE, padding=(15, 10))
        style.map("Accent.TButton", background=[("active", "#096861")])
        style.configure("TEntry", padding=6)
        style.configure("Treeview", rowheight=30)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))
        style.configure("Horizontal.TProgressbar", troughcolor=BORDER, background=TEAL)

    def _layout(self) -> None:
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(body, width=235, bg=SIDEBAR)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text="JAŹŃ", bg=SIDEBAR, fg="#c4fff2",
                 font=("Segoe UI Semibold", 23), anchor="w").pack(fill="x", padx=20, pady=(22, 0))
        tk.Label(self.sidebar, text="STUDIO PAMIĘCI", bg=SIDEBAR, fg="#a7c5d4",
                 font=("Segoe UI Semibold", 11), anchor="w").pack(fill="x", padx=20, pady=(0, 18))
        self.nav_buttons: dict[str, tk.Button] = {}
        for key, name, _desc in PAGES:
            button = tk.Button(self.sidebar, text=name, anchor="w", font=("Segoe UI", 10),
                               bg=SIDEBAR, fg="#e1f0f6", activebackground=SIDEBAR_ACCENT,
                               activeforeground=WHITE, relief="flat", borderwidth=0,
                               padx=22, pady=9, cursor="hand2",
                               command=lambda selected=key: self.open_page(selected))
            button.pack(fill="x", padx=8, pady=1)
            self.nav_buttons[key] = button
        tk.Label(self.sidebar, text=f"SYSTEM {PACKAGE_VERSION_FULL.split('-')[0]}",
                 bg=SIDEBAR, fg="#8db5c6", font=("Segoe UI", 9),
                 wraplength=200).pack(side="bottom", anchor="w", padx=20, pady=20)

        self.main = ttk.Frame(body, padding=(26, 22))
        self.main.pack(fill="both", expand=True)
        self.heading = ttk.Label(self.main, text="", style="Heading.TLabel")
        self.heading.pack(anchor="w")
        self.subtitle = ttk.Label(self.main, text="", style="Note.TLabel")
        self.subtitle.pack(anchor="w", pady=(4, 14))
        self.meta = ttk.Label(self.main, text="", style="Note.TLabel")
        self.meta.pack(anchor="w", pady=(0, 14))
        self.content = ttk.Frame(self.main)
        self.content.pack(fill="both", expand=True)
        bottom = ttk.Frame(self.main)
        bottom.pack(fill="x", pady=(14, 0))
        self.progress = ttk.Progressbar(bottom, length=160, mode="indeterminate")
        self.progress.pack(side="right")
        self.status = ttk.Label(bottom, text="Gotowe", style="Note.TLabel")
        self.status.pack(side="left")

    def _label(self, frame: Any, text: str, *, note: bool = False) -> None:
        ttk.Label(frame, text=text, style="Note.TLabel" if note else "Section.TLabel",
                  wraplength=830, justify="left").pack(anchor="w", pady=(6, 9))

    def _button(self, frame: Any, name: str, fn: Callable[[], Any], *,
                threaded: bool = False, emphasis: bool = False) -> None:
        ttk.Button(frame, text=name, style="Accent.TButton" if emphasis else "TButton",
                   command=lambda: self._execute(name, fn, threaded=threaded)).pack(
                       side="left", padx=(0, 10), pady=7)

    def _action_row(self, *actions: tuple[str, Callable[[], Any], bool]) -> ttk.Frame:
        row = ttk.Frame(self.content)
        row.pack(fill="x", pady=8)
        for name, fn, threaded in actions:
            self._button(row, name, fn, threaded=threaded)
        return row

    def _card(self, title: str, detail: str) -> None:
        frame = ttk.Frame(self.content, style="Card.TFrame", padding=18)
        frame.pack(fill="x", pady=6)
        ttk.Label(frame, text=title, style="Card.TLabel",
                  font=("Segoe UI Semibold", 12)).pack(anchor="w")
        ttk.Label(frame, text=detail, style="CardNote.TLabel",
                  wraplength=800).pack(anchor="w", pady=(5, 0))

    def _execute(self, title: str, fn: Callable[[], Any], *, threaded: bool) -> None:
        if self._busy:
            self.dialogs.message("Operacja trwa", "Zaczekaj na zakończenie bieżącej operacji. Nie uruchamiamy dwóch zapisów jednocześnie.")
            return
        self._busy = True
        self.status.configure(text=f"W toku: {title}")
        self.progress.start(15)
        try:
            self.diagnostics.record("INFO", f"Desktop Studio: {title}")
        except Exception:
            pass

        def job() -> None:
            try:
                result = fn()
                self._updates.put((True, result, title))
            except Exception as exc:
                self._updates.put((False, exc, title))

        if threaded:
            Thread(target=job, name="JaznMemoryStudioWorker", daemon=True).start()
        else:
            # Source/path pickers inside existing workflows use Tk file dialogs.
            # Keep these workflows on the UI thread; long canonical protocols
            # use a worker and marshal all Tk dialogs back via TkStudioDialogs.
            job()
            self._check_updates()

    def _check_updates(self) -> None:
        try:
            while True:
                ok, result, title = self._updates.get_nowait()
                self._busy = False
                self.progress.stop()
                self.status.configure(text=f"{'Zakończono' if ok else 'Błąd'}: {title}")
                if not ok:
                    try:
                        self.diagnostics.record("ERROR", f"Desktop Studio: {title}: {type(result).__name__}: {result}")
                    except Exception:
                        pass
                    self.dialogs.message("Operacja nie powiodła się", f"{type(result).__name__}: {result}")
                self.state.refresh()
                self.open_page(self._page)
        except Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(80, self._check_updates)

    def _project(self) -> Any | None:
        if not self.state.project:
            return None
        return ProjectStore(self.state.project_root).load(self.state.project)

    def _require_project(self) -> Any:
        project = self._project()
        if project is None:
            raise ValueError("Najpierw wybierz lub utwórz projekt w sekcji »Projekt i źródła«.")
        return project

    def open_page(self, page: str) -> None:
        if self._busy and page != self._page:
            return
        self._page = page
        title, desc = PAGE_BY_ID[page]
        self.heading.configure(text=title)
        self.subtitle.configure(text=desc)
        self.state.refresh()
        project = self.state.project_snapshot
        self.meta.configure(text=f"Projekt: {(project or {}).get('name') or 'nie wybrano'}"
                            f"   •   Baza: {self.state.database}")
        for key, button in self.nav_buttons.items():
            button.configure(bg=SIDEBAR_ACCENT if key == page else SIDEBAR,
                             fg=WHITE if key == page else "#e1f0f6")
        for widget in self.content.winfo_children():
            widget.destroy()
        getattr(self, f"_page_{page}")()

    def _page_home(self) -> None:
        project = self._project()
        self._card("Stan konfiguracji", "Projekt jest wybrany." if project else
                   "Brak wybranego projektu. Zacznij od utworzenia projektu i wskazania źródeł.")
        self._card("Kanoniczna baza", str(self.state.database) +
                   (" • istnieje" if self.state.database.is_file() else " • jeszcze nie istnieje"))
        self._card("Bezpieczna kolejność",
                   "1. Projekt i źródła → 2. Ścieżki → 3. Preflight/plan → "
                   "4. Test00–Test04 → 5. Final i eksport. Nigdy nie wybieraj aktywnej bazy jako celu eksperymentu.")
        self._card("Afekt i rozmowy",
                   "Jawne identyfikatory conversation_id/message_id/turn_id/trace_id; "
                   "brak źródłowego związku oznacza source_only. Modelowany afekt ≠ przeżycie biologiczne.")
        self._action_row(
            ("Otwórz projekt", lambda: self.open_page("projects"), False),
            ("Skonfiguruj ścieżki", lambda: self.open_page("paths"), False),
            ("Plan bez zapisu", lambda: self.workflows.plan(compare=False), True),
        )

    def _page_projects(self) -> None:
        self._label(self.content, "Projekty i rejestr źródeł")
        self._action_row(
            ("Wybierz / utwórz projekt", self.workflows.project_hub, False),
            ("Przeskanuj / dodaj / edytuj źródła", self.workflows.sources_hub, False),
            ("Baseline’y Testów 01–04", self.workflows.baselines_hub, False),
        )
        project = self._project()
        if not project:
            self._card("Pusta lista", "Utwórz projekt w nowym katalogu poza repozytorium Jaźni.")
            return
        self._card("Projekt", f"{project.name}    •    tryb: {project.mode}    •    źródła: {len(project.sources)}")
        table = ttk.Treeview(self.content, columns=("role", "pipeline", "status"), show="headings", height=14)
        for col, label, width in (("role", "Rola / źródło", 440),
                                  ("pipeline", "Sposób użycia", 210),
                                  ("status", "Status", 140)):
            table.heading(col, text=label)
            table.column(col, width=width, minwidth=90)
        for source in project.sources:
            table.insert("", "end", values=(f"{source.role}: {Path(source.path).name}",
                                              source.pipeline, source.status))
        table.pack(fill="both", expand=True, pady=10)

    def _page_paths(self) -> None:
        project = self._project()
        self._label(self.content, "Mapa ścieżek — co jest czytane, a co jest zapisywane")
        self._card("Pliki operatora (bez zapisu do pamięci)",
                   f"Projekty: {self.state.project_root or default_project_root()}\n"
                   f"Ustawienia: {self.state.settings_file}\n"
                   f"Artefakty protokołów: {self.tool_root / 'memory' / 'rebuild_tests' / 'protocols'}")
        if not project:
            self._label(self.content, "Utwórz lub wybierz projekt, aby konfigurować ścieżki.", note=True)
            return
        values = project_path_values(project, self.state.database)
        self._fields = {}
        grid = ttk.Frame(self.content)
        grid.pack(fill="x", pady=10)
        for index, (key, caption, kind, _owner) in enumerate(PATH_FIELDS):
            ttk.Label(grid, text=caption).grid(row=index, column=0, sticky="w", padx=(0, 8), pady=7)
            var = tk.StringVar(value=values.get(key, ""))
            self._fields[key] = var
            ttk.Entry(grid, textvariable=var, width=72).grid(row=index, column=1, sticky="ew", padx=8)
            ttk.Button(grid, text="Wybierz…",
                       command=lambda k=key, t=kind: self._browse_path(k, t)).grid(
                           row=index, column=2, padx=4)
        grid.columnconfigure(1, weight=1)
        self._action_row(
            ("Zapisz ścieżki projektu", self._save_paths, False),
            ("Sprawdź preflight", lambda: self.workflows._controller().preflight() and
             self.dialogs.message("PREFLIGHT", _pretty(self.workflows._controller().preflight())), True),
        )
        self._label(self.content,
                    "Źródła i katalog odbudowy muszą być rozdzielone. Zapis ścieżek nie uruchamia importu ani aktywacji.",
                    note=True)

    def _browse_path(self, key: str, kind: str) -> None:
        if kind == "directory":
            selected = filedialog.askdirectory(parent=self.root, title="Wybierz katalog")
        elif kind == "savefile":
            selected = filedialog.asksaveasfilename(parent=self.root, title="Wskaż plik bazy",
                initialfile=CANONICAL_DATABASE_NAME, defaultextension=".sqlite3",
                filetypes=[("SQLite", "*.sqlite3"), ("Wszystkie pliki", "*.*")])
        else:
            selected = filedialog.askopenfilename(parent=self.root, title="Wybierz plik")
        if selected:
            self._fields[key].set(selected)

    def _save_paths(self) -> None:
        project = self._require_project()
        changes = proposed_path_changes({key: var.get() for key, var in self._fields.items()})
        if changes["database"] != str(self.state.database):
            db = Path(changes["database"])
            if db.is_file() and db.name != CANONICAL_DATABASE_NAME:
                raise ValueError("Wybierz kanoniczną nazwę memory_jazn.sqlite3.")
        if project.mode == "developer":
            target = Path(changes["target_root"])
            if target == self.tool_root or self.tool_root in target.parents:
                raise ValueError("Katalog developer staging musi leżeć poza repozytorium.")
        project.source_directory = changes["source_directory"]
        project.target_root = changes["target_root"]
        for key in ("test04_benchmark", "test04_acceptance_report",
                    "restart_continuity_report", "final_output"):
            if changes[key]:
                project.settings[key] = changes[key]
            else:
                project.settings.pop(key, None)
        project.settings["unified_database_path"] = changes["database"]
        ProjectStore(self.state.project_root).save(project)
        self.state.select_project(project.project_id)
        self.state.set_database(changes["database"], remember=True)
        self.dialogs.message("Zapisano", "Ścieżki projektu zapisane. Nie przebudowano ani nie aktywowano pamięci.")

    def _page_database(self) -> None:
        self._card("Docelowa SQLite", str(self.state.database))
        self._action_row(
            ("Wybierz / utwórz bazę", self.workflows.database_hub, False),
            ("Pełna walidacja", lambda: self.dialogs.message("WALIDACJA",
                _pretty(UnifiedMemoryDatabase(self.state.database).validate(full=True))), True),
            ("Recall / benchmark", self.workflows.recall_hub, True),
        )
        self._label(self.content, "Baza eksperymentalna nie może być tą samą bazą, którą zapisuje aktywny daemon.", note=True)

    def _page_import(self) -> None:
        self._card("Źródła ChatGPT, dzienniki, muzyka, stare bazy",
                   "Import zachowuje dane źródłowe i proweniencję, nie aktywuje L2/L3.")
        self._action_row(
            ("Import z projektu / plików", self.workflows.import_hub, False),
            ("Sprawdź i edytuj źródła", self.workflows.sources_hub, False),
            ("Plan odbudowy bez zapisu", lambda: self.workflows.plan(compare=False), True),
        )

    def _page_affect(self) -> None:
        self._card("Emocje — źródła i modelowane stany",
                   "Historia wiadomości i afektu jest łączona wyłącznie poprzez jawne identyfikatory. "
                   "Widok jest tylko do odczytu, bez automatycznego przypisywania uczuć.")
        self._action_row(("Otwórz przegląd śladów afektywnych", self.workflows.affect_hub, True),)

    def _page_candidates(self) -> None:
        self._card("Kandydaci doświadczeń L1",
                   "Generowanie kandydatów i ich ręczny przegląd; żadne automatyczne przejście do L2/L3.")
        self._action_row(("Otwórz kandydatów pamięci", self.workflows.candidates_hub, True),)

    def _page_tests(self) -> None:
        self._label(self.content, "Test00 → Test01 → Test02 → Test03 → Test04 → Final")
        self._card("Wymagane dowody", "Uruchamiaj po kolei w tej samej sesji Studio. "
                   "Test04 wymaga prywatnego benchmarku z sekcji Ścieżki. "
                   "Final wymaga pozytywnego Test04 dla tego samego kandydata.")
        frame = ttk.Frame(self.content)
        frame.pack(fill="x")
        for index, item in enumerate(TEST_SPECS):
            row = ttk.Frame(frame, padding=(5, 6))
            row.pack(fill="x")
            ttk.Label(row, text=item.label, font=("Segoe UI Semibold", 10),
                      width=40).pack(side="left", padx=5)
            result = self.state.test_results.get(item.profile)
            ttk.Label(row, text=str(result.get("outcome") if result else "NIE URUCHOMIONO"),
                      width=20).pack(side="left", padx=4)
            ttk.Button(row, text="Uruchom", command=lambda p=item.profile:
                       self._execute(f"Protokół {p}", lambda: _run_test(self.state, self.dialogs, p),
                                     threaded=True)).pack(side="right", padx=4)

    def _page_rebuild(self) -> None:
        self._card("Kontrolowana odbudowa",
                   "Najpierw wymagany jest preflight, następnie plan. Każda operacja zapisująca "
                   "wymaga osobnego tokenu potwierdzenia. Zabezpieczeń nie można wyłączyć.")
        self._action_row(
            ("Sprawdź preflight", lambda: self.dialogs.message("PREFLIGHT",
                _pretty(self.workflows._controller().preflight())), True),
            ("Pokaż plan bez zapisu", lambda: self.workflows.plan(compare=False), True),
            ("Porównaj z baseline", lambda: self.workflows.plan(compare=True), True),
        )
        self._action_row(("Wykonaj odbudowę (wymaga tokenu)", self.workflows.rebuild, True),)

    def _page_export(self) -> None:
        self._card("Publikacja finalna jest osobną decyzją",
                   "Nie jest równoznaczna z włączeniem pamięci w działającej Jaźni. "
                   "Wymaga raportu akceptacji oraz integralnej bazy.")
        self._action_row(("Zweryfikuj bazę", lambda: self.dialogs.message("WALIDACJA",
            _pretty(UnifiedMemoryDatabase(self.state.database).validate(full=True))), True),
            ("Finalny eksport", self.workflows.export, True))

    def _page_settings(self) -> None:
        project = self._project()
        self._label(self.content, "Opcje projektu i walidacji")
        self._settings_fields = {}
        if project:
            pane = ttk.Frame(self.content)
            pane.pack(fill="x")
            for index, (key, default) in enumerate(DEFAULT_SETTINGS.items()):
                if not isinstance(default, bool):
                    continue
                value = tk.BooleanVar(value=bool(project.settings.get(key, default)))
                self._settings_fields[key] = value
                ttk.Checkbutton(pane, text=key.replace("_", " "), variable=value,
                    state="disabled" if key in {"automatic_experience_approval", "automatic_l2", "automatic_l3"} else "normal"
                ).grid(row=index // 2, column=index % 2, sticky="w", padx=8, pady=4)
            self._action_row(("Zapisz opcje projektu", self._save_options, False),
                             ("Zaawansowane ustawienia", lambda: self.state.edit_project_settings(), False))
        else:
            self._label(self.content, "Najpierw wybierz projekt.", note=True)
        self._card("Kontrakt bezpieczeństwa",
                   "Wymagane są FTS5 i provenance. Automatyczne L2, L3 oraz aktywacja pozostają wyłączone.")
        self._action_row(("Retrieval i embeddingi", lambda: self.dialogs.message("USTAWIENIA",
              "Użyj pozycji Zaawansowane ustawienia lub Studio TUI dla pełnych opcji modelu."), False),)

    def _save_options(self) -> None:
        project = self._require_project()
        risky = {"continue_on_error": True, "apply_reclassification": True, "force_topics": True,
                 "verify_after_each": False, "full_validation": False,
                 "create_backup": False, "audit_classifiers": False,
                 "hash_sources_during_scan": False, "preserve_all_chat_branches": False,
                 "preserve_exact_source_text": False}
        for key, variable in self._settings_fields.items():
            proposed = bool(variable.get())
            previous = bool(project.settings.get(key, DEFAULT_SETTINGS[key]))
            if key in {"automatic_experience_approval", "automatic_l2", "automatic_l3"}:
                if proposed:
                    raise ValueError(f"Zablokowane ustawienie {key}")
                continue
            if proposed != previous and risky.get(key) == proposed and not self.dialogs.confirm(
                    "Zmiana ryzykowna", f"Potwierdzasz mniej bezpieczną wartość {key}={proposed}?"):
                return
            project.settings[key] = proposed
        ProjectStore(self.state.project_root).save(project)
        self.state.refresh()
        self.dialogs.message("Zapisano", "Opcje projektu zapisano w prywatnym pliku projektu.")

    def _page_diagnostics(self) -> None:
        self._card("Środowisko", f"Katalog kodu: {self.tool_root}\n"
                   f"Projekt: {self.state.project_root or default_project_root()}\n"
                   f"Ustawienia: {self.state.settings_file}\n"
                   f"Baza: {self.state.database}\n"
                   f"Pakiet SYSTEM: {PACKAGE_VERSION_FULL}\n"
                   f"Studio: {STUDIO_VERSION}")
        self._card("Zasady", "Gotowość prywatnej pamięci i accepted turn wymagają dowodu runtime. "
                   "Stan GUI i istnienie pliku nie potwierdzają aktywacji pamięci.")
        self._action_row(
            ("Preflight", lambda: self.dialogs.message("PREFLIGHT", _pretty(
                self.workflows._controller().preflight())), True),
            ("Waliduj bazę", lambda: self.dialogs.message("WALIDACJA",
                _pretty(UnifiedMemoryDatabase(self.state.database).validate(full=True))), True),
        )


def _pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def run_desktop(*, tool_root: Path, diagnostics: Any, project_root: Path | None = None,
                project: str | None = None, settings_path: Path | None = None) -> int:
    root = tk.Tk()
    DesktopWorkspace(root, tool_root=Path(tool_root), diagnostics=diagnostics,
                     project_root=project_root, project=project, settings_path=settings_path)
    root.mainloop()
    return 0


__all__ = ["DesktopWorkspace", "TkStudioDialogs", "PATH_FIELDS", "PAGES",
           "project_path_values", "proposed_path_changes", "run_desktop"]
