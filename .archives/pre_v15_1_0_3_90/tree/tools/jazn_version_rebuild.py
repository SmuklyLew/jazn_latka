from __future__ import annotations

"""Jaźń Version Rebuild v0.1 — graficzna przebudowa wersji bez tworzenia branchy."""

import ast
import difflib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Callable, Iterable, Mapping

APP_NAME = "Jaźń Version Rebuild"
APP_VERSION = "0.1"
SETTINGS_NAME = "jazn_version_rebuild.settings.json"
BACKUP_PREFIX = "jazn_version_rebuild_backup"
VERSION_PATH = Path("latka_jazn/version.py")
PYPROJECT_PATH = Path("pyproject.toml")
PROVENANCE_PATH = Path("SOURCE_PROVENANCE.json")
MANIFEST_PATH = Path("PACKAGE_INTEGRITY_MANIFEST.json")
GENERATED_PATHS = (PROVENANCE_PATH, MANIFEST_PATH)
VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+)+$")
DIST_PATTERN = re.compile(r"^\d+(?:\.\d+)*$")


class RebuildError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VersionData:
    version: str
    package: str
    name: str

    @property
    def full(self) -> str:
        return f"{self.package}-{self.name}" if self.name else self.package

    @property
    def distribution(self) -> str:
        prefix = f"v{self.version}"
        return self.package[len(prefix) + 1 :] if self.package.startswith(prefix + ".") else ""


@dataclass(slots=True)
class Settings:
    root: str
    python: str
    base_branch: str = "master"
    backup_prefix: str = BACKUP_PREFIX
    allow_unrelated_changes: bool = False


def app_dir() -> Path:
    return Path(__file__).resolve().parent


def discover_root(start: Path) -> Path:
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / VERSION_PATH).is_file() and ((candidate / "run.py").is_file() or (candidate / "main.py").is_file()):
            return candidate
    return start.parent if start.name.lower() == "tools" else start


def project_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if not (root / VERSION_PATH).is_file():
        raise RebuildError(f"Brak kanonicznego pliku: {root / VERSION_PATH}")
    if not ((root / "run.py").is_file() or (root / "main.py").is_file()):
        raise RebuildError(f"To nie wygląda na root projektu Jaźń: {root}")
    return root


def clean_prefix(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
    return value or BACKUP_PREFIX


def load_settings(path: Path) -> Settings:
    default = Settings(str(discover_root(path.parent)), sys.executable)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return default
    if not isinstance(payload, dict):
        return default
    return Settings(
        root=str(payload.get("root") or default.root),
        python=str(payload.get("python") or default.python),
        base_branch=str(payload.get("base_branch") or "master"),
        backup_prefix=clean_prefix(str(payload.get("backup_prefix") or BACKUP_PREFIX)),
        allow_unrelated_changes=bool(payload.get("allow_unrelated_changes", False)),
    )


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def save_settings(path: Path, settings: Settings) -> None:
    payload = {
        "schema_version": "jazn_version_rebuild_settings/v0.1",
        "app_version": APP_VERSION,
        "root": settings.root,
        "python": settings.python,
        "base_branch": settings.base_branch,
        "backup_prefix": clean_prefix(settings.backup_prefix),
        "allow_unrelated_changes": settings.allow_unrelated_changes,
    }
    atomic_write(path, (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def assignments(path: Path) -> dict[str, str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError as exc:
        raise RebuildError(f"Błędna składnia {path}: {exc}") from exc
    result: dict[str, str] = {}
    for node in tree.body:
        targets: list[str] = []
        value = None
        if isinstance(node, ast.Assign):
            targets = [item.id for item in node.targets if isinstance(item, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for target in targets:
                result[target] = value.value.strip()
    return result


def validate(data: VersionData) -> None:
    if not VERSION_PATTERN.fullmatch(data.version):
        raise RebuildError("Numer wersji musi mieć format liczbowy, np. 15.1.0.3.89.")
    if not data.package.startswith("v") or not VERSION_PATTERN.fullmatch(data.package[1:]):
        raise RebuildError("PACKAGE_VERSION musi mieć format, np. vX.Y.Z.N.")
    if "\n" in data.name or "\r" in data.name:
        raise RebuildError("Nazwa wersji nie może zawierać nowej linii.")


def read_version(root: Path) -> VersionData:
    values = assignments(project_root(root) / VERSION_PATH)
    missing = [key for key in ("DISTRIBUTION_VERSION", "PACKAGE_VERSION", "PACKAGE_RELEASE_NAME") if key not in values]
    if missing:
        raise RebuildError("Brak pól w version.py: " + ", ".join(missing))
    data = VersionData(values["DISTRIBUTION_VERSION"], values["PACKAGE_VERSION"], values["PACKAGE_RELEASE_NAME"])
    validate(data)
    return data


def build_version(version: str, distribution: str, name: str) -> VersionData:
    version = version.strip().lstrip("vV")
    distribution = distribution.strip().strip(".")
    if not VERSION_PATTERN.fullmatch(version):
        raise RebuildError("Numer wersji musi mieć format liczbowy, np. 15.1.0.3.89.")
    if distribution and not DIST_PATTERN.fullmatch(distribution):
        raise RebuildError("Numer dystrybucji musi być liczbą, np. 88 albo 88.1.")
    package = f"v{version}" + (f".{distribution}" if distribution else "")
    data = VersionData(version, package, name.strip())
    validate(data)
    return data


def render_version(path: Path, data: VersionData) -> bytes:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8-sig")
    values = {
        "DISTRIBUTION_VERSION": data.version,
        "PACKAGE_VERSION": data.package,
        "PACKAGE_RELEASE_NAME": data.name,
    }
    for key, value in values.items():
        pattern = re.compile(rf"(?m)^(?P<prefix>\s*{re.escape(key)}\s*=\s*)(?P<q>['\"])(?P<old>.*?)(?P=q)(?P<suffix>\s*(?:#.*)?)$")
        found = list(pattern.finditer(text))
        if len(found) != 1:
            raise RebuildError(f"Oczekiwano jednego przypisania {key}; znaleziono {len(found)}.")
        match = found[0]
        literal = json.dumps(value, ensure_ascii=False)
        replacement = match.group("prefix") + literal + match.group("suffix")
        text = text[: match.start()] + replacement + text[match.end() :]
    ast.parse(text, filename=str(path))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    encoded = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + encoded) if bom else encoded


def command(args: list[str], root: Path, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RebuildError(f"Nie znaleziono programu: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RebuildError("Przekroczono limit czasu: " + " ".join(args)) from exc


def git(root: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return command(["git", *args], root, timeout)


def is_git(root: Path) -> bool:
    result = git(root, "rev-parse", "--is-inside-work-tree", timeout=20)
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_lines(root: Path) -> list[str]:
    result = git(root, "status", "--porcelain", "--untracked-files=all")
    if result.returncode:
        raise RebuildError(result.stderr.strip() or "Nie można odczytać stanu Git.")
    return [line for line in result.stdout.splitlines() if line.strip()]


def unrelated_changes(root: Path, allowed: Iterable[Path]) -> list[str]:
    allowed_names = {item.as_posix() for item in allowed}
    result: list[str] = []
    for line in git_lines(root):
        name = line[3:].strip().split(" -> ")[-1].strip('"').replace("\\", "/")
        if name not in allowed_names:
            result.append(line)
    return result


def snapshot(root: Path, paths: Iterable[Path]) -> dict[Path, bytes | None]:
    return {item: ((root / item).read_bytes() if (root / item).is_file() else None) for item in paths}


def restore(root: Path, data: Mapping[Path, bytes | None]) -> None:
    for relative, raw in data.items():
        path = root / relative
        if raw is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, raw)


def unified_diff(before: Mapping[Path, bytes | None], after: Mapping[Path, bytes | None]) -> str:
    output: list[str] = []
    for relative in sorted(set(before) | set(after), key=lambda item: item.as_posix()):
        old = before.get(relative)
        new = after.get(relative)
        if old == new:
            continue
        output.extend(
            difflib.unified_diff(
                "" if old is None else old.decode("utf-8-sig").splitlines(keepends=True),
                "" if new is None else new.decode("utf-8-sig").splitlines(keepends=True),
                fromfile="/dev/null" if old is None else f"a/{relative.as_posix()}",
                tofile="/dev/null" if new is None else f"b/{relative.as_posix()}",
                lineterm="\n",
            )
        )
    text = "".join(output)
    return text if not text or text.endswith("\n") else text + "\n"


def diff_backup(folder: Path, prefix: str, label: str, old: str, new: str, before: Mapping[Path, bytes | None], after: Mapping[Path, bytes | None]) -> Path:
    patch = unified_diff(before, after)
    if not patch:
        raise RebuildError("Nie wykryto zmian do zapisania w kopii diff.")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    safe = lambda value: re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:80]
    path = folder / f"{clean_prefix(prefix)}_{stamp}_{safe(label)}_{safe(old)}_to_{safe(new)}.diff"
    header = (
        f"# {APP_NAME} v{APP_VERSION}\n"
        f"# Utworzono: {datetime.now().astimezone().isoformat()}\n"
        f"# Operacja: {label}\n"
        "# Cofnięcie: git apply --reverse --check plik.diff; git apply --reverse plik.diff\n"
    )
    atomic_write(path, (header + patch).encode("utf-8"))
    return path


def apply_patch(root: Path, path: Path, reverse: bool) -> str:
    if not is_git(root):
        raise RebuildError("Zastosowanie diff wymaga repozytorium Git.")
    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    if not lines:
        raise RebuildError("Plik diff nie zawiera zmian.")
    fd, name = tempfile.mkstemp(prefix="jazn_version_", suffix=".diff")
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("".join(lines))
        args = ["apply"] + (["--reverse"] if reverse else [])
        check = git(root, *args, "--check", str(temp))
        if check.returncode:
            raise RebuildError(check.stderr.strip() or check.stdout.strip() or "git apply --check nie powiódł się")
        result = git(root, *args, str(temp))
        if result.returncode:
            raise RebuildError(result.stderr.strip() or result.stdout.strip() or "git apply nie powiódł się")
        return result.stdout.strip() or "Diff zastosowany poprawnie."
    finally:
        temp.unlink(missing_ok=True)


def json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def metadata_current(root: Path, path: Path, version: VersionData) -> bool:
    value = json_object(root / path)
    if path == PROVENANCE_PATH:
        expected = {
            "schema_version": f"source_provenance/{version.package}",
            "runtime_version": version.full,
            "update_version": version.full,
            "version_source": "latka_jazn/version.py",
        }
    else:
        expected = {
            "schema_version": f"package_integrity_manifest/{version.package}",
            "version": version.full,
            "runtime_version": version.full,
            "package_version": version.full,
        }
    return bool(value) and all(value.get(key) == expected_value for key, expected_value in expected.items())


def pyproject_ok(root: Path) -> bool:
    try:
        text = (root / PYPROJECT_PATH).read_text(encoding="utf-8-sig")
    except OSError:
        return False
    return 'dynamic = ["version"]' in text and 'version = {attr = "latka_jazn.version.DISTRIBUTION_VERSION"}' in text


def compile_version(root: Path, python: str) -> str:
    result = command([python, "-X", "utf8", "-m", "py_compile", str(root / VERSION_PATH)], root, 60)
    if result.returncode:
        raise RebuildError(result.stderr.strip() or result.stdout.strip() or "Kompilacja version.py nie powiodła się.")
    return result.stdout.strip() or "Kompilacja version.py: OK"


def audit(root: Path, python: str) -> tuple[bool, str]:
    result = command(
        [python, "-X", "utf8", "-m", "latka_jazn.tools.version_consistency_audit", "--root", str(root), "--no-progress"],
        root,
        360,
    )
    output = "\n".join(item for item in (result.stdout.strip(), result.stderr.strip()) if item)
    return result.returncode == 0, output or "Audyt nie zwrócił tekstu."


def sync_metadata(root: Path, python: str, branch: str) -> str:
    status = git_lines(root)
    if status:
        raise RebuildError("Synchronizacja wymaga czystego drzewa Git. Najpierw zatwierdź version.py.\n\n" + "\n".join(status[:20]))
    result = command(
        [python, "-X", "utf8", "-m", "latka_jazn.tools.release_metadata_sync", "--root", str(root), "--base-branch", branch or "master", "--write", "--json", "--no-progress"],
        root,
        900,
    )
    output = "\n".join(item for item in (result.stdout.strip(), result.stderr.strip()) if item)
    if result.returncode:
        raise RebuildError(output or "Synchronizacja metadanych nie powiodła się.")
    return output or "Synchronizacja metadanych: OK"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.folder = app_dir()
        self.settings_path = self.folder / SETTINGS_NAME
        self.settings = load_settings(self.settings_path)
        self.busy = False
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1160x780")
        self.minsize(1000, 680)
        self._vars()
        self._ui()
        self.after(80, self.refresh)

    def _vars(self) -> None:
        self.root_var = tk.StringVar(value=self.settings.root)
        self.python_var = tk.StringVar(value=self.settings.python)
        self.branch_var = tk.StringVar(value=self.settings.base_branch)
        self.prefix_var = tk.StringVar(value=self.settings.backup_prefix)
        self.allow_dirty_var = tk.BooleanVar(value=self.settings.allow_unrelated_changes)
        self.version_var = tk.StringVar()
        self.dist_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.preview_var = tk.StringVar(value="—")
        self.repo_var = tk.StringVar(value="Repozytorium: sprawdzanie…")
        self.status_var = tk.StringVar(value="Gotowe")
        for variable in (self.version_var, self.dist_var, self.name_var):
            variable.trace_add("write", lambda *_: self.preview())

    def _ui(self) -> None:
        header = ttk.Frame(self, padding=(14, 12, 14, 8))
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, font=("Segoe UI", 17, "bold")).pack(side="left")
        ttk.Label(header, text=f"v{APP_VERSION}").pack(side="left", padx=8, pady=(7, 0))
        ttk.Label(header, textvariable=self.repo_var).pack(side="right", pady=(7, 0))
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        self.version_page = ttk.Frame(self.tabs, padding=12)
        self.diff_page = ttk.Frame(self.tabs, padding=12)
        self.settings_page = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.version_page, text="Wersja i pliki")
        self.tabs.add(self.diff_page, text="Kopie diff")
        self.tabs.add(self.settings_page, text="Ustawienia")
        self._version_ui()
        self._diff_ui()
        self._settings_ui()
        footer = ttk.Frame(self, padding=(14, 3, 14, 10))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=180)
        self.progress.pack(side="right")

    def _version_ui(self) -> None:
        form = ttk.LabelFrame(self.version_page, text="Nowa wersja", padding=10)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        ttk.Label(form, text="Numer wersji:").grid(row=0, column=0, sticky="w", padx=(0, 7), pady=5)
        ttk.Entry(form, textvariable=self.version_var).grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(form, text="Numer dystrybucji:").grid(row=0, column=2, sticky="w", padx=(18, 7), pady=5)
        ttk.Entry(form, textvariable=self.dist_var).grid(row=0, column=3, sticky="ew", pady=5)
        ttk.Label(form, text="Nazwa wersji:").grid(row=1, column=0, sticky="w", padx=(0, 7), pady=5)
        ttk.Entry(form, textvariable=self.name_var).grid(row=1, column=1, columnspan=3, sticky="ew", pady=5)
        ttk.Label(form, text="Podgląd:").grid(row=2, column=0, sticky="w", pady=(8, 2))
        ttk.Label(form, textvariable=self.preview_var, font=("Consolas", 10, "bold")).grid(row=2, column=1, columnspan=3, sticky="w", pady=(8, 2))
        buttons = ttk.Frame(self.version_page)
        buttons.pack(fill="x", pady=9)
        for label, callback in (
            ("Odśwież", self.refresh),
            ("Zapisz zmianę wersji", self.save_version),
            ("Synchronizuj metadane", self.synchronize),
            ("Sprawdź spójność", self.run_audit),
        ):
            ttk.Button(buttons, text=label, command=callback).pack(side="left", padx=(0, 8))
        box = ttk.LabelFrame(self.version_page, text="Pliki objęte edycją, synchronizacją i kontrolą", padding=7)
        box.pack(fill="both", expand=True)
        self.files = ttk.Treeview(box, columns=("state", "path", "role", "action"), show="headings", height=9)
        for key, label, width in (
            ("state", "Stan", 115),
            ("path", "Plik", 300),
            ("role", "Rola", 250),
            ("action", "Sposób obsługi", 330),
        ):
            self.files.heading(key, text=label)
            self.files.column(key, width=width, stretch=key != "state")
        self.files.pack(fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(self.version_page, height=11, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(8, 0))

    def _diff_ui(self) -> None:
        ttk.Label(
            self.diff_page,
            text="Kopie unified diff są zapisywane w tym samym folderze co aplikacja. Można je zastosować lub cofnąć bez tworzenia brancha.",
            wraplength=980,
        ).pack(fill="x", pady=(0, 9))
        buttons = ttk.Frame(self.diff_page)
        buttons.pack(fill="x", pady=(0, 8))
        ttk.Button(buttons, text="Odśwież", command=self.refresh_diffs).pack(side="left")
        ttk.Button(buttons, text="Zastosuj diff", command=lambda: self.patch(False)).pack(side="left", padx=8)
        ttk.Button(buttons, text="Cofnij diff", command=lambda: self.patch(True)).pack(side="left")
        ttk.Button(buttons, text="Wybierz inny diff…", command=self.pick_diff).pack(side="left", padx=8)
        self.diffs = ttk.Treeview(self.diff_page, columns=("name", "date", "size"), show="headings")
        self.diffs.heading("name", text="Plik")
        self.diffs.heading("date", text="Zmodyfikowano")
        self.diffs.heading("size", text="Rozmiar")
        self.diffs.column("name", width=700, stretch=True)
        self.diffs.column("date", width=180, stretch=False)
        self.diffs.column("size", width=110, stretch=False)
        self.diffs.pack(fill="both", expand=True)

    def _settings_ui(self) -> None:
        frame = ttk.LabelFrame(self.settings_page, text="Ustawienia aplikacji", padding=12)
        frame.pack(fill="x")
        frame.columnconfigure(1, weight=1)
        rows = (
            ("Root projektu:", self.root_var, self.pick_root),
            ("Interpreter Python:", self.python_var, self.pick_python),
        )
        for row, (label, variable, callback) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=6)
            ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=6)
            ttk.Button(frame, text="Wybierz…", command=callback).grid(row=row, column=2, padx=(8, 0), pady=6)
        ttk.Label(frame, text="Bazowy branch metadanych:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(frame, textvariable=self.branch_var).grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(frame, text="Prefiks kopii diff:").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(frame, textvariable=self.prefix_var).grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Checkbutton(
            frame,
            text="Zezwalaj na zapis version.py przy innych niezwiązanych zmianach Git",
            variable=self.allow_dirty_var,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 5))
        ttk.Label(
            frame,
            text=f"Ustawienia i kopie diff są zapisywane obok aplikacji:\n{self.folder}\n\nAplikacja nie tworzy ani nie przełącza branchy i nie dotyka memory/, workspace_runtime/ ani SQLite.",
            wraplength=900,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 8))
        ttk.Button(frame, text="Zapisz ustawienia", command=self.save_config).grid(row=6, column=0, sticky="w")

    def root(self) -> Path:
        return project_root(self.root_var.get())

    def preview(self) -> None:
        try:
            self.preview_var.set(build_version(self.version_var.get(), self.dist_var.get(), self.name_var.get()).full)
        except RebuildError:
            self.preview_var.set("—")

    def write_log(self, text: str, clear: bool = False) -> None:
        if clear:
            self.log.delete("1.0", "end")
        self.log.insert("end", f"[{datetime.now():%H:%M:%S}] {text.rstrip()}\n")
        self.log.see("end")

    def background(self, label: str, worker: Callable[[], object], done: Callable[[object], None]) -> None:
        if self.busy:
            return
        self.busy = True
        self.status_var.set(label)
        self.progress.start(12)

        def run() -> None:
            try:
                result = worker()
            except Exception as exc:
                self.after(0, lambda: self.failed(exc))
            else:
                self.after(0, lambda: self.succeeded(result, done))

        threading.Thread(target=run, daemon=True).start()

    def failed(self, exc: Exception) -> None:
        self.busy = False
        self.progress.stop()
        self.status_var.set("Błąd")
        self.write_log("BŁĄD: " + str(exc))
        messagebox.showerror(APP_NAME, str(exc), parent=self)

    def succeeded(self, result: object, done: Callable[[object], None]) -> None:
        self.busy = False
        self.progress.stop()
        self.status_var.set("Gotowe")
        done(result)

    def refresh(self) -> None:
        try:
            root = self.root()
            version = read_version(root)
            self.version_var.set(version.version)
            self.dist_var.set(version.distribution)
            self.name_var.set(version.name)
            if is_git(root):
                branch = git(root, "branch", "--show-current").stdout.strip() or "(detached)"
                head = git(root, "rev-parse", "HEAD").stdout.strip()[:12]
                self.repo_var.set(f"Branch: {branch} | HEAD: {head}")
            else:
                self.repo_var.set("Repozytorium: Git niedostępny")
            self.files.delete(*self.files.get_children())
            rows = (
                ("ŹRÓDŁO", VERSION_PATH, "kanoniczne źródło wersji", "edycja atomowa"),
                ("POWIĄZANY" if pyproject_ok(root) else "BŁĄD", PYPROJECT_PATH, "wersja pakietu Python", "kontrola bez edycji"),
                ("AKTUALNY" if metadata_current(root, PROVENANCE_PATH, version) else "NIEAKTUALNY", PROVENANCE_PATH, "proweniencja Git", "kanoniczna synchronizacja po commicie"),
                ("AKTUALNY" if metadata_current(root, MANIFEST_PATH, version) else "NIEAKTUALNY", MANIFEST_PATH, "manifest integralności", "kanoniczna synchronizacja po commicie"),
            )
            for state, path, role, action in rows:
                self.files.insert("", "end", values=(state, path.as_posix(), role, action))
            self.refresh_diffs()
            self.write_log(f"Wczytano {version.full}", clear=True)
            self.status_var.set(f"Wczytano {version.full}")
        except Exception as exc:
            self.failed(exc)

    def save_version(self) -> None:
        try:
            root = self.root()
            current = read_version(root)
            target = build_version(self.version_var.get(), self.dist_var.get(), self.name_var.get())
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        if target == current:
            messagebox.showinfo(APP_NAME, "Dane wersji nie uległy zmianie.", parent=self)
            return
        if not messagebox.askyesno(APP_NAME, f"Zmienić wersję?\n\n{current.full}\n→ {target.full}", parent=self):
            return
        allow_dirty = self.allow_dirty_var.get()
        python = self.python_var.get().strip() or sys.executable
        prefix = self.prefix_var.get()

        def worker() -> dict[str, object]:
            if is_git(root) and not allow_dirty:
                other = unrelated_changes(root, [VERSION_PATH])
                if other:
                    raise RebuildError("Git wykrył niezwiązane zmiany:\n\n" + "\n".join(other[:20]))
            before = snapshot(root, [VERSION_PATH])
            try:
                atomic_write(root / VERSION_PATH, render_version(root / VERSION_PATH, target))
                compile_result = compile_version(root, python)
                if read_version(root) != target:
                    raise RebuildError("Kontrola odczytu nie potwierdziła nowej wersji.")
                after = snapshot(root, [VERSION_PATH])
                backup = diff_backup(self.folder, prefix, "version", current.full, target.full, before, after)
            except Exception:
                restore(root, before)
                raise
            return {"backup": backup, "compile": compile_result}

        def done(result: object) -> None:
            data = result if isinstance(result, dict) else {}
            self.write_log(f"Zapisano {target.full}")
            self.write_log(str(data.get("compile", "")))
            self.write_log(f"Kopia diff: {data.get('backup')}")
            self.write_log("Po commicie version.py uruchom synchronizację metadanych.")
            self.refresh()
            messagebox.showinfo(APP_NAME, f"Wersja zaktualizowana.\n\nKopia diff:\n{data.get('backup')}", parent=self)

        self.background("Zapisywanie wersji…", worker, done)

    def synchronize(self) -> None:
        try:
            root = self.root()
            version = read_version(root)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        if not messagebox.askyesno(APP_NAME, "Uruchomić kanoniczną synchronizację manifestu i proweniencji?\n\nGit musi być czysty.", parent=self):
            return
        python = self.python_var.get().strip() or sys.executable
        branch = self.branch_var.get().strip() or "master"
        prefix = self.prefix_var.get()

        def worker() -> dict[str, object]:
            before = snapshot(root, GENERATED_PATHS)
            try:
                output = sync_metadata(root, python, branch)
                after = snapshot(root, GENERATED_PATHS)
                backup = diff_backup(self.folder, prefix, "metadata", version.full, version.full, before, after)
            except Exception:
                restore(root, before)
                raise
            return {"output": output, "backup": backup}

        def done(result: object) -> None:
            data = result if isinstance(result, dict) else {}
            self.write_log("Metadane zsynchronizowane.")
            self.write_log(str(data.get("output", "")))
            self.write_log(f"Kopia diff: {data.get('backup')}")
            self.refresh()
            messagebox.showinfo(APP_NAME, f"Metadane zsynchronizowane.\n\nKopia diff:\n{data.get('backup')}", parent=self)

        self.background("Synchronizowanie metadanych…", worker, done)

    def run_audit(self) -> None:
        try:
            root = self.root()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        python = self.python_var.get().strip() or sys.executable

        def done(result: object) -> None:
            ok, output = result if isinstance(result, tuple) else (False, str(result))
            self.write_log(("AUDYT OK\n" if ok else "AUDYT: NIESPÓJNOŚCI\n") + output, clear=True)
            messagebox.showinfo(APP_NAME, "Audyt poprawny." if ok else "Audyt wykrył niespójności. Szczegóły są w logu.", parent=self)

        self.background("Uruchamianie audytu…", lambda: audit(root, python), done)

    def refresh_diffs(self) -> None:
        self.diffs.delete(*self.diffs.get_children())
        for path in sorted(self.folder.glob("*.diff"), key=lambda item: item.stat().st_mtime, reverse=True):
            stat = path.stat()
            self.diffs.insert("", "end", iid=str(path), values=(path.name, datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"), f"{stat.st_size / 1024:.1f} KiB"))

    def selected_diff(self) -> Path | None:
        selected = self.diffs.selection()
        return Path(selected[0]) if selected else None

    def patch(self, reverse: bool, path: Path | None = None) -> None:
        path = path or self.selected_diff()
        if path is None:
            messagebox.showinfo(APP_NAME, "Wybierz plik diff.", parent=self)
            return
        try:
            root = self.root()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        action = "cofnąć" if reverse else "zastosować"
        if not messagebox.askyesno(APP_NAME, f"Czy {action} diff?\n\n{path.name}", parent=self):
            return

        def done(result: object) -> None:
            self.write_log(str(result))
            self.refresh()
            messagebox.showinfo(APP_NAME, "Operacja diff zakończona poprawnie.", parent=self)

        self.background("Przetwarzanie diff…", lambda: apply_patch(root, path, reverse), done)

    def pick_diff(self) -> None:
        value = filedialog.askopenfilename(parent=self, initialdir=self.folder, filetypes=(("Diff", "*.diff"), ("Wszystkie", "*.*")))
        if value:
            reverse = messagebox.askyesno(APP_NAME, "Tak = cofnij diff\nNie = zastosuj diff do przodu", parent=self)
            self.patch(reverse, Path(value))

    def save_config(self) -> None:
        try:
            settings = Settings(
                root=str(self.root()),
                python=self.python_var.get().strip() or sys.executable,
                base_branch=self.branch_var.get().strip() or "master",
                backup_prefix=clean_prefix(self.prefix_var.get()),
                allow_unrelated_changes=self.allow_dirty_var.get(),
            )
            save_settings(self.settings_path, settings)
            self.settings = settings
            self.prefix_var.set(settings.backup_prefix)
            self.refresh()
            messagebox.showinfo(APP_NAME, f"Ustawienia zapisano:\n{self.settings_path}", parent=self)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)

    def pick_root(self) -> None:
        value = filedialog.askdirectory(parent=self, initialdir=self.root_var.get())
        if value:
            self.root_var.set(value)

    def pick_python(self) -> None:
        value = filedialog.askopenfilename(parent=self, initialdir=str(Path(self.python_var.get()).expanduser().parent))
        if value:
            self.python_var.set(value)


def main() -> int:
    try:
        App().mainloop()
        return 0
    except tk.TclError as exc:
        print(f"{APP_NAME} v{APP_VERSION}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
