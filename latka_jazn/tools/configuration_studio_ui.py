"""Native Tk configuration cockpit. All UI operations run on the Tk thread."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from latka_jazn.memory.memory_root import resolve_memory_root

from .configuration_studio import (
    SETTINGS, ConfigValidationError, describe_profile, inspect_system,
    profile_file, profile_snapshot, read_profile, save_profile, restore_previous_profile, system_root,
    validate_values,
)

BG = "#edf3f8"
NAV = "#162c41"
FG = "#193850"
ACCENT = "#087f77"
WHITE = "#ffffff"
SUBTLE = "#5a7286"

PAGES = (("overview", "Pulpit"), ("paths", "Mapa ścieżek"),
         ("settings", "Konfiguracja"), ("diagnostics", "Diagnostyka"))


class ConfigurationStudio:
    def __init__(self, root: tk.Tk, *, system: Path):
        self.root = root
        self.system = system_root(system)
        self._current_page = "overview"
        self._entries: dict[str, tk.StringVar] = {}
        self._known_hash: str | None = None
        self._page_loaded_values: dict[str, str] = {}
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._set_theme()
        self.root.title("Jaźń — Studio konfiguracji")
        self.root.geometry("1210x790")
        self.root.minsize(930, 610)
        self.root.configure(bg=BG)
        self.frame = ttk.Frame(root)
        self.frame.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(self.frame, bg=NAV, width=220)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text="JAŹŃ", bg=NAV, fg=WHITE,
                 font=("Segoe UI", 21, "bold")).pack(anchor="w", padx=22, pady=(25, 3))
        tk.Label(self.sidebar, text="Studio konfiguracji 1.0", bg=NAV,
                 fg="#b7cedb", font=("Segoe UI", 10)).pack(anchor="w", padx=22, pady=(0, 22))
        for key, label in PAGES:
            tk.Button(self.sidebar, text=label, anchor="w", bg=NAV, fg=WHITE,
                      activebackground="#294862", activeforeground=WHITE,
                      relief="flat", font=("Segoe UI", 11), padx=20, pady=12,
                      command=lambda page=key: self.open_page(page)).pack(fill="x")
        self.content = ttk.Frame(self.frame, padding=24)
        self.content.pack(side="left", fill="both", expand=True)
        self.status = tk.StringVar(value="Tryb bezpieczny: profil nie jest aktywną konfiguracją daemona")
        ttk.Label(root, textvariable=self.status, style="Status.TLabel",
                  anchor="w", padding=(15, 8)).pack(fill="x")
        self.open_page("overview")

    def _set_theme(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=WHITE)
        style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=BG, foreground=FG,
                        font=("Segoe UI", 22, "bold"))
        style.configure("Note.TLabel", background=BG, foreground=SUBTLE, font=("Segoe UI", 10))
        style.configure("Status.TLabel", background=NAV, foreground=WHITE, font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 10), padding=8)
        style.configure("Accent.TButton", background=ACCENT, foreground=WHITE)
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=27)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", padding=5)

    def _clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def _heading(self, name: str, note: str) -> None:
        ttk.Label(self.content, text=name, style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.content, text=note, style="Note.TLabel",
                  wraplength=800).pack(anchor="w", pady=(6, 20))

    def _dirty(self) -> bool:
        return self._current_page == "settings" and bool(self._entries) and (
            self._values() != self._page_loaded_values
        )

    def _may_discard(self) -> bool:
        return not self._dirty() or messagebox.askyesno(
            "Niezapisane zmiany",
            "Niezapisane ustawienia zostaną utracone. Odrzucić je?",
            parent=self.root,
        )

    def _close(self) -> None:
        if self._may_discard():
            self.root.destroy()

    def open_page(self, page: str) -> None:
        if page != self._current_page and not self._may_discard():
            return
        if page not in {key for key, _ in PAGES}:
            raise ValueError(f"Nieznana strona: {page}")
        self._current_page = page
        self._clear()
        getattr(self, "_page_" + page)()

    def _page_overview(self) -> None:
        self._heading("Centrum konfiguracji", "System, workspace, pamięć i ustawienia bez mieszania danych.")
        details = describe_profile(self.system)
        for label, value in (
            ("Zweryfikowany katalog SYSTEM", str(self.system)),
            ("Plik profilu operatorskiego", str(details["profile_path"])),
            ("Liczba nadpisań w profilu", str(len(details["values"]))),
            ("Stan zastosowania", "Tylko przy przyszłym, jawnym uruchomieniu"),
        ):
            panel = ttk.Frame(self.content, style="Panel.TFrame", padding=16)
            panel.pack(fill="x", pady=5)
            ttk.Label(panel, text=label, foreground=SUBTLE).pack(anchor="w")
            ttk.Label(panel, text=value, font=("Segoe UI", 11, "bold"),
                      wraplength=740).pack(anchor="w", pady=(5, 0))
        actions = ttk.Frame(self.content)
        actions.pack(fill="x", pady=18)
        ttk.Button(actions, text="Mapa ścieżek",
                   command=lambda: self.open_page("paths")).pack(side="left", padx=(0, 10))
        ttk.Button(actions, text="Edytuj profil", style="Accent.TButton",
                   command=lambda: self.open_page("settings")).pack(side="left")
        ttk.Label(self.content, text="Zmiany w Studio nie aktualizują działającego daemona ani pamięci.",
                  style="Note.TLabel").pack(anchor="w", pady=12)

    def _page_paths(self) -> None:
        self._heading("Mapa ścieżek", "Rzeczywiste ścieżki wyliczone przez runtime (odczyt bez modyfikacji).")
        frame = ttk.Frame(self.content)
        frame.pack(fill="both", expand=True)
        table = ttk.Treeview(frame, columns=("location", "found", "description"),
                             show="headings", selectmode="browse")
        for col, label, width in (
            ("location", "Lokalizacja", 460), ("found", "Istnieje", 80),
            ("description", "Znaczenie", 250),
        ):
            table.heading(col, text=label)
            table.column(col, width=width, minwidth=70, stretch=(col != "found"))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for item in inspect_system(self.system):
            table.insert("", "end", iid=item["name"],
                         values=(item["path"], "tak" if item["exists"] == "true" else "nie", item["note"]))
        actions = ttk.Frame(self.content)
        actions.pack(anchor="w", pady=12)
        ttk.Button(actions, text="Odśwież", command=lambda: self.open_page("paths")).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Kopiuj wybraną ścieżkę",
                   command=lambda: self._copy_selection(table)).pack(side="left")

    def _copy_selection(self, table: ttk.Treeview) -> None:
        selection = table.selection()
        if selection:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(table.item(selection[0], "values")[0]))
            self.status.set("Skopiowano ścieżkę do schowka.")

    def _page_settings(self) -> None:
        self._heading("Profil uruchomieniowy", "Edytuj tylko zatwierdzone klucze. Puste pole oznacza brak nadpisania.")
        try:
            stored, self._known_hash = profile_snapshot(self.system)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Nie można odczytać profilu", str(exc), parent=self.root)
            stored = {}
            self._known_hash = None
        self._page_loaded_values = {spec.key: stored.get(spec.key, "") for spec in SETTINGS}
        outer = ttk.Frame(self.content)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, borderwidth=0, highlightthickness=0)
        bar = ttk.Scrollbar(outer, command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        rows = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=rows, anchor="nw")
        rows.bind("<Configure>", lambda _ev: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda ev: canvas.itemconfigure(window, width=ev.width))
        self._entries = {}
        for section in ("Ścieżki", "Runtime"):
            ttk.Label(rows, text=section, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(9, 6))
            for spec in (x for x in SETTINGS if x.section == section):
                line = ttk.Frame(rows)
                line.pack(fill="x", pady=5)
                ttk.Label(line, text=spec.title, width=25).pack(side="left")
                variable = tk.StringVar(value=stored.get(spec.key, ""))
                self._entries[spec.key] = variable
                ttk.Entry(line, textvariable=variable).pack(side="left", fill="x", expand=True, padx=8)
                if spec.kind in {"directory", "file", "memory_database"}:
                    ttk.Button(line, text="…", width=3,
                               command=lambda v=variable, t=spec.kind: self._browse(v, t)).pack(side="right")
                ttk.Label(rows, text=f"{spec.key} — {spec.hint}", style="Note.TLabel").pack(anchor="w", padx=12)
        actions = ttk.Frame(self.content)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Sprawdź wartości", command=self._validate).pack(side="left", padx=(0, 7))
        ttk.Button(actions, text="Zapisz profil", style="Accent.TButton",
                   command=self._save).pack(side="left", padx=7)
        ttk.Button(actions, text="Wczytaj z dysku", command=self._reload_settings).pack(side="left")
        ttk.Button(actions, text="Przywróć poprzedni", command=self._restore_previous).pack(side="left", padx=6)
        ttk.Button(actions, text="Kopiuj komendę uruchomienia",
                   command=self._copy_launch_command).pack(side="right")

    def _browse(self, variable: tk.StringVar, kind: str) -> None:
        if kind == "memory_database":
            configured = self._values().get("JAZN_MEMORY_ROOT", "").strip()
            base = resolve_memory_root(self.system, configured=configured or None)
            selected = filedialog.askopenfilename(
                parent=self.root, title="Wybierz bazę wewnątrz MEMORY", initialdir=str(base),
                filetypes=[("SQLite", "*.sqlite *.sqlite3 *.db"), ("Wszystkie pliki", "*")],
            )
            if selected:
                try:
                    relative = Path(selected).resolve().relative_to(base)
                    validate_values(self.system, {**self._values(), "JAZN_MEMORY_TIER_DB": relative.as_posix()})
                except ValueError as exc:
                    messagebox.showerror("Nie wybrano bazy", str(exc), parent=self.root)
                    return
                variable.set(relative.as_posix())
            return
        if kind == "file":
            selected = filedialog.asksaveasfilename(parent=self.root, title="Wybierz ścieżkę pliku")
        else:
            selected = filedialog.askdirectory(parent=self.root, title="Wybierz folder")
        if selected:
            variable.set(str(Path(selected).resolve()))

    def _values(self) -> dict[str, str]:
        return {key: str(field.get()) for key, field in self._entries.items()}

    def _validate(self) -> None:
        try:
            result = validate_values(self.system, self._values())
        except (ConfigValidationError, OSError) as exc:
            messagebox.showerror("Nieprawidłowy profil", str(exc), parent=self.root)
            return
        messagebox.showinfo("Kontrola zakończona", f"Poprawnych nadpisań: {len(result)}.\n"
                            "Nie zmieniono żadnego pliku.", parent=self.root)

    def _reload_settings(self) -> None:
        if self._may_discard():
            self._clear()
            self._page_settings()

    def _restore_previous(self) -> None:
        if not messagebox.askyesno(
            "Przywróć profil", "Zastąpić obecny profil ostatnią kopią? Zmiana jest zapisywana.",
            parent=self.root,
        ):
            return
        try:
            restored = restore_previous_profile(self.system, expected_sha256=self._known_hash)
            self.status.set("Przywrócono profil: " + str(restored))
            self._clear()
            self._page_settings()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Nie przywrócono profilu", str(exc), parent=self.root)

    def _save(self) -> None:
        try:
            result = validate_values(self.system, self._values())
            old = read_profile(self.system)
            changed = sorted(key for key in (set(old) | set(result)) if old.get(key) != result.get(key))
            if not changed:
                self.status.set("Brak zmian do zapisania.")
                return
            if not messagebox.askyesno("Zapis profilu",
                                       "Zmiany: " + ", ".join(changed) +
                                       "\n\nZapiszę wyłącznie profil dla przyszłych uruchomień. Kontynuować?",
                                       parent=self.root):
                return
            destination = save_profile(self.system, result, expected_sha256=self._known_hash)
            _, self._known_hash = profile_snapshot(self.system)
            self._page_loaded_values = self._values()
            self.status.set("Profil zapisany: " + str(destination))
        except (ValueError, OSError) as exc:
            messagebox.showerror("Nie zapisano profilu", str(exc), parent=self.root)

    def _copy_launch_command(self) -> None:
        config = profile_file(self.system)
        launcher = self.system / "tools" / "windows" / "Start-JaznWithConfig.ps1"
        command = f'pwsh -File "{launcher}" -Profile "{config}"'
        self.root.clipboard_clear()
        self.root.clipboard_append(command)
        self.status.set("Skopiowano polecenie startu Jaźni z profilem — wykonanie jest ręczne.")

    def _page_diagnostics(self) -> None:
        self._heading("Diagnostyka", "Odczyt konfiguracji i śladów, bez automatycznej aktywacji runtime.")
        panel = tk.Text(self.content, bg=WHITE, fg=FG, wrap="word", relief="flat",
                        font=("Consolas", 10), padx=15, pady=15)
        panel.pack(fill="both", expand=True)
        for item in inspect_system(self.system):
            panel.insert("end", f'{item["name"]}: {item["path"]} (istnieje: {item["exists"]})\n')
        panel.insert("end", "\nSamo istnienie PID/markera nie dowodzi gotowości daemona.\n")
        panel.insert("end", "Nie wyświetlam sekretów, tokenów ani zawartości pamięci.\n")
        panel.configure(state="disabled")


def run_window(system: Path) -> int:
    root = tk.Tk()
    ConfigurationStudio(root, system=system)
    root.mainloop()
    return 0
