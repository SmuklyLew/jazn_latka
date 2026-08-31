from __future__ import annotations

from pathlib import Path
import re
import textwrap

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "tools" / "jazn_pack_generator.py"
VERSION = ROOT / "latka_jazn" / "version.py"
OLD_TEST = ROOT / "tests" / "test_jazn_pack_generator_two_file_bundle_v86.py"
NEW_TEST = ROOT / "tests" / "test_jazn_pack_generator_two_file_bundle_v87.py"
REG_TEST = ROOT / "tests" / "test_jazn_pack_generator_v87_studio_portability.py"
DOC = ROOT / "docs" / "runtime" / "JAZN_PACK_GENERATOR_V87_STUDIO_PORTABILITY.md"

OVERLAY = r'''
# -----------------------------------------------------------------------------
# v8.7 portability + Studio overlay (kept in the single-file/two-file bundle)
# -----------------------------------------------------------------------------
import json as _v87_json
import os as _v87_os
import queue as _v87_queue
import re as _v87_re
import shutil as _v87_shutil
import tempfile as _v87_tempfile
import threading as _v87_threading
import unicodedata as _v87_unicodedata
from dataclasses import replace as _v87_replace

_V87_INTEROP_CONTRACT = "jazn_pack_generator_interoperability/v1"
_V87_MANAGED_NAME_RE = _v87_re.compile(
    r"^jazn_latka_v\d+(?:\.\d+){2,6}(?:-[0-9A-Za-z][0-9A-Za-z._-]*)?$",
    _v87_re.IGNORECASE,
)
_V87_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_V87_WINDOWS_FORBIDDEN_CHARS = frozenset('<>:"|?*')


def _v87_core_module():
    return getattr(_impl, "_core", None)


def _v87_pack_error(message: str):
    error_cls = getattr(_impl, "PackError", ValueError)
    return error_cls(message)


def _v87_is_generator_managed_name(value: str | None) -> bool:
    raw = str(value or "").strip()
    return not raw or raw.casefold() == "jazn_latka" or bool(_V87_MANAGED_NAME_RE.fullmatch(raw))


def refresh_archive_basename_for_current_release(state, *, force: bool = False) -> bool:
    """Refresh an empty/stale generator-owned package name from version.py.

    Custom names are preserved. A canonical name produced by an older Jaźń
    release is treated as generator-owned and is refreshed automatically.
    """
    core = _v87_core_module()
    if core is None:
        return False
    try:
        version = core.read_version_info(state.source.expanduser().resolve())
        canonical = core.canonical_archive_basename(version)
    except (OSError, ValueError, getattr(_impl, "PackError", ValueError)):
        return False
    current = str(getattr(state, "archive_basename", "") or "").strip()
    if not force and not _v87_is_generator_managed_name(current):
        return False
    if current == canonical:
        return False
    state.archive_basename = canonical
    marker = getattr(core, "mark_interactive_state_changed", None)
    if callable(marker):
        marker(state)
    return True


def validate_portable_member_names(plan) -> None:
    """Fail closed on archive names that are unsafe/ambiguous on Windows."""
    folded: dict[str, str] = {}
    for entry in plan.entries:
        raw = str(entry.relative or "").replace("\\", "/")
        if not raw or raw.startswith("/"):
            raise _v87_pack_error(f"Nieprzenośna ścieżka ZIP: {raw!r}")
        parts = raw.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise _v87_pack_error(f"Nieprzenośna ścieżka ZIP: {raw!r}")
        for part in parts:
            if part.endswith(" ") or part.endswith("."):
                raise _v87_pack_error(f"Nazwa niezgodna z Windows (końcowa spacja/kropka): {raw}")
            if any(ord(ch) < 32 or ch in _V87_WINDOWS_FORBIDDEN_CHARS for ch in part):
                raise _v87_pack_error(f"Nazwa zawiera znak niedozwolony w Windows: {raw}")
            stem = part.split(".", 1)[0].upper()
            if stem in _V87_WINDOWS_RESERVED:
                raise _v87_pack_error(f"Nazwa zarezerwowana przez Windows: {raw}")
        key = _v87_unicodedata.normalize("NFC", raw).casefold()
        previous = folded.get(key)
        if previous is not None and previous != raw:
            raise _v87_pack_error(
                "Kolizja nazw bez rozróżniania wielkości liter (Windows): "
                f"{previous!r} vs {raw!r}"
            )
        folded[key] = raw


def interoperability_profile(container_format: str, volume_format: str) -> dict[str, object]:
    container = str(container_format or "zip").strip().lower()
    volume = str(volume_format or "independent").strip().lower()
    if container in {"pyzip", "pyzipfile", "zip64"}:
        container = "zip"
    standard_zip = container == "zip"
    direct = bool(standard_zip and volume == "independent")
    requires_join = bool(standard_zip and volume == "binary")
    if direct:
        windows = "direct"
        note = "Standard ZIP/DEFLATE: bezpośrednie otwieranie i rozpakowanie."
    elif requires_join:
        windows = "join_required"
        note = "Części .zip.001/.002 są transportem binarnym; najpierw połącz je do pełnego .zip."
    elif container == "7z":
        windows = "windows_11_24h2_or_newer_unencrypted"
        note = "7z nie jest uniwersalnym profilem ZIP; użyj standard ZIP dla maksymalnej zgodności."
    elif container == "aes_zip":
        windows = "not_supported_by_builtin_explorer"
        note = "Szyfrowany AES ZIP wymaga narzędzia obsługującego WinZip AES."
    else:
        windows = "specialized"
        note = "Kontener specjalistyczny; nie deklaruj uniwersalnej zgodności ZIP."
    return {
        "contract": _V87_INTEROP_CONTRACT,
        "container_format": container,
        "volume_format": volume,
        "portable_standard_zip": direct,
        "direct_open_without_join": direct,
        "requires_join": requires_join,
        "compression_profile": "ZIP_DEFLATED" if standard_zip else "container-specific",
        "targets": {
            "windows_11_file_explorer": windows,
            "7_zip": "direct" if direct else ("after_join" if requires_join else "container-dependent"),
            "winzip": "direct" if direct else ("after_join" if requires_join else "container-dependent"),
            "winrar": "direct" if direct else ("after_join" if requires_join else "container-dependent"),
        },
        "note": note,
    }


def _v87_extend_compatibility(report: dict, archive_format: str) -> dict:
    result = dict(report)
    profile = interoperability_profile("zip", archive_format)
    rows = list(result.get("results") or [])
    rows.append({
        "tool": "Windows/ZIP interoperability profile",
        "status": "passed" if profile["portable_standard_zip"] else "join_required",
        "detail": profile["note"],
    })
    result["results"] = rows
    result["distribution_interoperability"] = profile
    result["portable_standard_zip"] = bool(profile["portable_standard_zip"])
    return result


def _v87_install_overrides() -> None:
    core = _v87_core_module()
    if core is None:
        return
    core.GENERATOR_VERSION = GENERATOR_VERSION
    core.SETTINGS_SCHEMA = SETTINGS_SCHEMA
    _impl.GENERATOR_VERSION = GENERATOR_VERSION
    _impl.SETTINGS_SCHEMA = SETTINGS_SCHEMA

    original_ensure = getattr(core, "ensure_interactive_archive_basename", None)
    if callable(original_ensure):
        def ensure_interactive_archive_basename(state):
            refresh_archive_basename_for_current_release(state)
            return None
        core.ensure_interactive_archive_basename = ensure_interactive_archive_basename
        _impl.ensure_interactive_archive_basename = ensure_interactive_archive_basename
        globals()["ensure_interactive_archive_basename"] = ensure_interactive_archive_basename

    original_matrix = getattr(core, "run_compatibility_matrix", None)
    if callable(original_matrix):
        def run_compatibility_matrix(temp_dir, outputs, archive_format):
            return _v87_extend_compatibility(
                original_matrix(temp_dir, outputs, archive_format), archive_format
            )
        core.run_compatibility_matrix = run_compatibility_matrix
        _impl.run_compatibility_matrix = run_compatibility_matrix
        globals()["run_compatibility_matrix"] = run_compatibility_matrix

    original_package_one = getattr(_impl, "package_one", None)
    if callable(original_package_one):
        def package_one(plan, options, base_zip_name):
            validate_portable_member_names(plan)
            result = original_package_one(plan, options, base_zip_name)
            # Non-ZIP extensions perform their own verification path. Add an
            # explicit interoperability scope to the committed sidecar without
            # changing archive bytes or the package-set hash.
            try:
                sidecar = _bundle_Path(result.sidecar_path)
                payload = _v87_json.loads(sidecar.read_text(encoding="utf-8-sig"))
                container = str(payload.get("container_format") or "zip")
                volume = str(payload.get("archive_format") or result.archive_format)
                payload["generator_version"] = GENERATOR_VERSION
                payload["interoperability"] = interoperability_profile(container, volume)
                verification = payload.get("verification")
                if isinstance(verification, dict):
                    compatibility = verification.get("compatibility")
                    if isinstance(compatibility, dict):
                        compatibility["distribution_interoperability"] = payload["interoperability"]
                temp = sidecar.with_name(sidecar.name + ".v87.tmp")
                temp.write_text(
                    _v87_json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                _v87_os.replace(temp, sidecar)
            except (OSError, UnicodeError, ValueError, TypeError, _v87_json.JSONDecodeError):
                # The archive and original verified sidecar remain valid. This
                # annotation is informative; never corrupt a package to add it.
                pass
            return result
        core.package_one = package_one
        _impl.package_one = package_one
        globals()["package_one"] = package_one


class _V87StudioUnavailable(RuntimeError):
    pass


def _v87_studio_settings_payload() -> dict:
    core = _v87_core_module()
    if core is None:
        return {}
    try:
        path = _bundle_Path(core.settings_path())
        if path.is_file():
            payload = _v87_json.loads(path.read_text(encoding="utf-8-sig"))
            return payload if isinstance(payload, dict) else {}
    except (OSError, UnicodeError, _v87_json.JSONDecodeError):
        pass
    return {}


def _v87_store_studio_preferences(*, portable_mode: bool, auto_start: bool) -> None:
    core = _v87_core_module()
    if core is None:
        return
    path = _bundle_Path(core.settings_path())
    payload = _v87_studio_settings_payload()
    payload["schema_version"] = SETTINGS_SCHEMA
    payload["generator_version"] = GENERATOR_VERSION
    payload["studio_v87"] = {
        "portable_mode": bool(portable_mode),
        "auto_start": bool(auto_start),
    }
    temp = path.with_name(path.name + ".studio.tmp")
    temp.write_text(_v87_json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _v87_os.replace(temp, path)


def _v87_saved_studio_preferences() -> dict:
    raw = _v87_studio_settings_payload().get("studio_v87")
    return dict(raw) if isinstance(raw, dict) else {}


def _v87_studio_should_autostart() -> bool:
    if _v87_os.environ.get("JAZN_PACK_GENERATOR_NO_STUDIO") == "1":
        return False
    pref = _v87_saved_studio_preferences().get("auto_start")
    if pref is not None:
        return bool(pref)
    return _v87_os.name == "nt"


def run_studio(argv=None) -> int:
    """Launch the v8.7 desktop Studio using only tkinter/ttk from stdlib."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise _V87StudioUnavailable("Tkinter nie jest dostępny w tej instalacji Pythona.") from exc

    core = _v87_core_module()
    if core is None:
        raise _V87StudioUnavailable("Nie wczytano rdzenia generatora.")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise _V87StudioUnavailable(f"Brak sesji graficznej: {exc}") from exc

    state = _impl.load_interactive_state()
    refresh_archive_basename_for_current_release(state)
    prefs = _v87_saved_studio_preferences()
    portable_default = bool(prefs.get("portable_mode", True))
    auto_default = bool(prefs.get("auto_start", _v87_os.name == "nt"))

    root.title(f"Jaźń / Łatka — Pack Generator Studio v{GENERATOR_VERSION}")
    root.geometry("1180x780")
    root.minsize(960, 650)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("StudioTitle.TLabel", font=("Segoe UI", 16, "bold"))
    style.configure("StudioSection.TLabel", font=("Segoe UI", 10, "bold"))
    style.configure("StudioStatus.TLabel", font=("Segoe UI", 9))

    source_var = tk.StringVar(value=str(state.source))
    out_var = tk.StringVar(value=str(state.out_dir))
    name_var = tk.StringVar(value=str(state.archive_basename))
    profile_var = tk.StringVar(value=str(state.profile))
    volume_var = tk.StringVar(value=str(state.archive_format))
    compression_var = tk.IntVar(value=int(state.compression_level))
    part_var = tk.IntVar(value=int(state.part_size_mb))
    compatibility_var = tk.BooleanVar(value=bool(state.compatibility_checks))
    portable_var = tk.BooleanVar(value=portable_default)
    auto_start_var = tk.BooleanVar(value=auto_default)
    container_var = tk.StringVar(value="zip")
    status_var = tk.StringVar(value="Gotowe. Ustaw źródło i wybierz operację.")
    name_is_manual = {"value": not _v87_is_generator_managed_name(name_var.get())}
    event_queue = _v87_queue.SimpleQueue()
    worker_busy = {"value": False}

    try:
        archive_settings = _impl.current_archive_settings()
        container_var.set(str(archive_settings.container_format))
    except Exception:
        archive_settings = None

    header = ttk.Frame(root, padding=(18, 14))
    header.pack(fill="x")
    ttk.Label(header, text="Jaźń Pack Generator Studio", style="StudioTitle.TLabel").pack(side="left")
    ttk.Label(header, text=f"v{GENERATOR_VERSION}  •  {SETTINGS_SCHEMA}").pack(side="right")

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=14, pady=(0, 10))
    pack_tab = ttk.Frame(notebook, padding=14)
    verify_tab = ttk.Frame(notebook, padding=14)
    settings_tab = ttk.Frame(notebook, padding=14)
    notebook.add(pack_tab, text="PAKOWANIE")
    notebook.add(verify_tab, text="WERYFIKACJA")
    notebook.add(settings_tab, text="USTAWIENIA")

    pack_tab.columnconfigure(1, weight=1)
    pack_tab.rowconfigure(9, weight=1)

    def row(label, variable, index, browse=None):
        ttk.Label(pack_tab, text=label, style="StudioSection.TLabel").grid(row=index, column=0, sticky="w", pady=5)
        entry = ttk.Entry(pack_tab, textvariable=variable)
        entry.grid(row=index, column=1, sticky="ew", padx=8, pady=5)
        if browse:
            ttk.Button(pack_tab, text="Wybierz…", command=browse).grid(row=index, column=2, pady=5)
        return entry

    def refresh_name(force=False):
        try:
            state.source = _bundle_Path(source_var.get()).expanduser().resolve()
            state.archive_basename = name_var.get().strip() or "jazn_latka"
            changed = refresh_archive_basename_for_current_release(
                state, force=bool(force or not name_is_manual["value"])
            )
            if changed or force:
                name_var.set(state.archive_basename)
                name_is_manual["value"] = False
            status_var.set(f"Nazwa paczki: {state.archive_basename}")
        except Exception as exc:
            status_var.set(f"Nie można odświeżyć nazwy: {exc}")

    def choose_source():
        selected = filedialog.askdirectory(initialdir=source_var.get() or str(_bundle_Path.cwd()))
        if selected:
            source_var.set(selected)
            name_is_manual["value"] = False
            refresh_name(force=True)

    def choose_out():
        selected = filedialog.askdirectory(initialdir=out_var.get() or str(_bundle_Path.cwd()))
        if selected:
            out_var.set(selected)

    source_entry = row("System Jaźni", source_var, 0, choose_source)
    row("Zapis archiwum", out_var, 1, choose_out)
    name_entry = row("Nazwa paczki", name_var, 2)
    ttk.Button(pack_tab, text="Odśwież z version.py", command=lambda: refresh_name(force=True)).grid(row=2, column=2, pady=5)
    name_entry.bind("<KeyRelease>", lambda _event: name_is_manual.__setitem__("value", True))
    source_entry.bind("<FocusOut>", lambda _event: refresh_name(force=False))

    options = ttk.LabelFrame(pack_tab, text="Format i kompatybilność", padding=10)
    options.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 8))
    for col in range(8):
        options.columnconfigure(col, weight=1 if col in {1, 3, 5, 7} else 0)
    ttk.Label(options, text="Profil").grid(row=0, column=0, sticky="w")
    ttk.Combobox(options, textvariable=profile_var, values=tuple(getattr(_impl, "PROFILE_CHOICES", ("system", "memory", "combined", "dual"))), state="readonly", width=14).grid(row=0, column=1, sticky="ew", padx=5)
    ttk.Label(options, text="Kontener").grid(row=0, column=2, sticky="w")
    ttk.Combobox(options, textvariable=container_var, values=("zip", "7z", "aes_zip"), state="readonly", width=12).grid(row=0, column=3, sticky="ew", padx=5)
    ttk.Label(options, text="Woluminy").grid(row=0, column=4, sticky="w")
    ttk.Combobox(options, textvariable=volume_var, values=("independent", "auto", "binary"), state="readonly", width=14).grid(row=0, column=5, sticky="ew", padx=5)
    ttk.Label(options, text="MiB/część").grid(row=0, column=6, sticky="w")
    ttk.Spinbox(options, from_=1, to=65536, textvariable=part_var, width=9).grid(row=0, column=7, sticky="ew", padx=5)
    ttk.Label(options, text="DEFLATE 0–9").grid(row=1, column=0, sticky="w", pady=(8, 0))
    ttk.Spinbox(options, from_=0, to=9, textvariable=compression_var, width=9).grid(row=1, column=1, sticky="w", padx=5, pady=(8, 0))
    ttk.Checkbutton(options, text="Testy zgodności", variable=compatibility_var).grid(row=1, column=2, columnspan=2, sticky="w", pady=(8, 0))
    ttk.Checkbutton(options, text="Portable ZIP (Windows/7-Zip/WinZip/WinRAR)", variable=portable_var).grid(row=1, column=4, columnspan=4, sticky="w", pady=(8, 0))

    compatibility_label = ttk.Label(pack_tab, text="", wraplength=980, style="StudioStatus.TLabel")
    compatibility_label.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(2, 8))

    def update_compatibility(*_args):
        container = "zip" if portable_var.get() else container_var.get()
        volume = "independent" if portable_var.get() else volume_var.get()
        profile = interoperability_profile(container, volume)
        compatibility_label.configure(text=(
            "Zgodność: " + str(profile["note"]) +
            "  Windows 11=" + str(profile["targets"]["windows_11_file_explorer"]) +
            "  7-Zip=" + str(profile["targets"]["7_zip"]) +
            "  WinZip=" + str(profile["targets"]["winzip"]) +
            "  WinRAR=" + str(profile["targets"]["winrar"])
        ))

    for variable in (container_var, volume_var, portable_var):
        variable.trace_add("write", update_compatibility)
    update_compatibility()

    actions = ttk.Frame(pack_tab)
    actions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=8)

    log = tk.Text(pack_tab, height=18, wrap="word", state="disabled", font=("Consolas", 9))
    log.grid(row=9, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
    scroll = ttk.Scrollbar(pack_tab, orient="vertical", command=log.yview)
    scroll.grid(row=9, column=3, sticky="ns")
    log.configure(yscrollcommand=scroll.set)

    def log_line(value):
        log.configure(state="normal")
        log.insert("end", str(value).rstrip() + "\n")
        log.see("end")
        log.configure(state="disabled")

    def sync_state():
        state.source = _bundle_Path(source_var.get()).expanduser().resolve()
        state.out_dir = _bundle_Path(out_var.get()).expanduser().resolve()
        state.profile = profile_var.get()
        state.archive_format = "independent" if portable_var.get() else volume_var.get()
        state.archive_basename = name_var.get().strip() or "jazn_latka"
        state.part_size_mb = max(1, int(part_var.get()))
        state.compression_level = max(0, min(9, int(compression_var.get())))
        state.compatibility_checks = bool(compatibility_var.get())
        if portable_var.get():
            container_var.set("zip")
        return state.to_options()

    def archive_settings_for_worker():
        settings = _impl.current_archive_settings()
        return _v87_replace(settings, container_format=container_var.get()).normalized()

    def save_state():
        sync_state()
        _impl.save_interactive_state(state)
        try:
            _impl.save_archive_settings(archive_settings_for_worker())
        except Exception:
            pass
        _v87_store_studio_preferences(
            portable_mode=portable_var.get(), auto_start=auto_start_var.get()
        )

    def worker(task_name, func):
        if worker_busy["value"]:
            messagebox.showinfo("Generator", "Inna operacja jest już wykonywana.")
            return
        worker_busy["value"] = True
        status_var.set(f"{task_name}…")
        log_line(f"\n== {task_name} ==")

        def target():
            sink = getattr(core, "_set_operation_output_sink", None)
            try:
                if callable(sink):
                    sink(lambda line: event_queue.put(("log", line)))
                result = func()
                event_queue.put(("ok", result))
            except Exception as exc:
                event_queue.put(("error", f"{type(exc).__name__}: {exc}"))
            finally:
                if callable(sink):
                    sink(None)
        _v87_threading.Thread(target=target, daemon=True, name="jazn-pack-studio-worker").start()

    def pack_now():
        try:
            save_state()
            options_value = sync_state()
            settings_value = archive_settings_for_worker()
        except Exception as exc:
            messagebox.showerror("Błąd konfiguracji", str(exc))
            return
        def task():
            with _impl.archive_settings_override(settings_value):
                results = _impl.run_pack(options_value)
            return "\n".join(str(path) for result in results for path in result.committed_paths)
        worker("Pakowanie", task)

    def preview_plan():
        try:
            options_value = sync_state()
        except Exception as exc:
            messagebox.showerror("Błąd konfiguracji", str(exc))
            return
        def task():
            plans = _impl.build_plans_for_options(options_value)
            return "\n\n".join(
                f"{p.profile}: {p.file_count} plików, {p.total_size} B, plan={p.plan_sha256()}"
                for p in plans
            )
        worker("Podgląd planu", task)

    ttk.Button(actions, text="PODGLĄD PLANU", command=preview_plan).pack(side="left")
    ttk.Button(actions, text="PAKUJ", command=pack_now).pack(side="left", padx=8)
    ttk.Button(actions, text="ZAPISZ USTAWIENIA", command=save_state).pack(side="left")

    # Verification page -------------------------------------------------------
    verify_tab.columnconfigure(1, weight=1)
    sidecar_var = tk.StringVar()
    destination_var = tk.StringVar()
    ttk.Label(verify_tab, text="Sidecar *.package.json", style="StudioSection.TLabel").grid(row=0, column=0, sticky="w", pady=6)
    ttk.Entry(verify_tab, textvariable=sidecar_var).grid(row=0, column=1, sticky="ew", padx=8)
    ttk.Button(verify_tab, text="Wybierz…", command=lambda: sidecar_var.set(filedialog.askopenfilename(filetypes=(("Package sidecar", "*.package.json"), ("JSON", "*.json"), ("Wszystkie", "*.*"))) or sidecar_var.get())).grid(row=0, column=2)
    ttk.Label(verify_tab, text="Katalog rozpakowania", style="StudioSection.TLabel").grid(row=1, column=0, sticky="w", pady=6)
    ttk.Entry(verify_tab, textvariable=destination_var).grid(row=1, column=1, sticky="ew", padx=8)
    ttk.Button(verify_tab, text="Wybierz…", command=lambda: destination_var.set(filedialog.askdirectory() or destination_var.get())).grid(row=1, column=2)

    def verify_existing():
        path = _bundle_Path(sidecar_var.get()).expanduser().resolve()
        worker("Weryfikacja paczki", lambda: _v87_json.dumps(_impl.verify_package_sidecar(path), ensure_ascii=False, indent=2, default=str))

    def extract_existing():
        sidecar = _bundle_Path(sidecar_var.get()).expanduser().resolve()
        destination = _bundle_Path(destination_var.get()).expanduser().resolve()
        worker("Bezpieczne rozpakowanie", lambda: _v87_json.dumps(_impl.extract_package_sidecar(sidecar, destination, clean=False, force=False), ensure_ascii=False, indent=2, default=str))

    ttk.Button(verify_tab, text="ZWERYFIKUJ", command=verify_existing).grid(row=2, column=0, pady=12, sticky="w")
    ttk.Button(verify_tab, text="ROZPAKUJ BEZPIECZNIE", command=extract_existing).grid(row=2, column=1, pady=12, sticky="w")

    # Settings page -----------------------------------------------------------
    ttk.Checkbutton(settings_tab, text="Uruchamiaj Studio domyślnie przy starcie bez argumentów", variable=auto_start_var).pack(anchor="w", pady=8)
    ttk.Checkbutton(settings_tab, text="Portable ZIP jako domyślny profil Studio", variable=portable_var).pack(anchor="w", pady=8)
    ttk.Label(settings_tab, text=(
        "Portable ZIP = standardowy ZIP/DEFLATE + kompletne, samodzielne woluminy. "
        "Tryb binary (.zip.001/.002) pozostaje obsługiwanym transportem Jaźni, "
        "ale wymaga połączenia przed użyciem Windows Explorer/WinZip jako jednego ZIP-a."
    ), wraplength=900).pack(anchor="w", pady=12)
    ttk.Button(settings_tab, text="ZAPISZ USTAWIENIA STUDIO", command=save_state).pack(anchor="w", pady=8)

    footer = ttk.Frame(root, padding=(14, 8))
    footer.pack(fill="x")
    ttk.Label(footer, textvariable=status_var, style="StudioStatus.TLabel").pack(side="left", fill="x", expand=True)
    ttk.Button(footer, text="Zamknij", command=root.destroy).pack(side="right")

    def poll_events():
        while True:
            try:
                kind, value = event_queue.get_nowait()
            except _v87_queue.Empty:
                break
            if kind == "log":
                log_line(value)
            elif kind == "ok":
                worker_busy["value"] = False
                status_var.set("Operacja zakończona poprawnie.")
                log_line(value)
            elif kind == "error":
                worker_busy["value"] = False
                status_var.set("Operacja zakończona błędem.")
                log_line("BŁĄD: " + str(value))
                messagebox.showerror("Generator", str(value))
        root.after(120, poll_events)

    def on_close():
        try:
            save_state()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(120, poll_events)
    refresh_name(force=False)
    root.mainloop()
    return 0


_v87_install_overrides()
'''

NEW_MAIN = r'''
def main(argv: _bundle_Sequence[str] | None = None) -> int:
    raw = list(_bundle_sys.argv[1:] if argv is None else argv)
    explicit_studio = bool(raw and raw[0] in {"studio", "--studio"})
    if explicit_studio:
        try:
            return int(run_studio(raw[1:]))
        except _V87StudioUnavailable as exc:
            print(f"Studio niedostępne: {exc}", file=_bundle_sys.stderr)
            return 2
    if not raw and _v87_studio_should_autostart():
        try:
            return int(run_studio(()))
        except _V87StudioUnavailable as exc:
            print(f"Studio niedostępne — przechodzę do interfejsu terminalowego: {exc}", file=_bundle_sys.stderr)
    try:
        return int(_impl.main(raw))
    except _impl.UserRequestedExit:
        print("Zakończono.")
        return 0
'''

REGRESSION_TEST = r'''
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import importlib
import zipfile

import pytest


def generator():
    return importlib.import_module("tools.jazn_pack_generator")


def _root(tmp_path: Path, version: str, release: str) -> Path:
    root = tmp_path / "root"
    version_py = root / "latka_jazn" / "version.py"
    version_py.parent.mkdir(parents=True)
    version_py.write_text(
        "DISTRIBUTION_VERSION = %r\nPACKAGE_VERSION = %r\nPACKAGE_RELEASE_NAME = %r\n"
        "PACKAGE_VERSION_FULL = f\"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}\" if PACKAGE_RELEASE_NAME else PACKAGE_VERSION\n"
        % (version, version, release),
        encoding="utf-8",
    )
    return root


def test_v87_version_and_studio_api_are_exposed() -> None:
    module = generator()
    assert module.GENERATOR_VERSION == "8.7"
    assert module.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.7"
    assert callable(module.run_studio)
    assert callable(module.refresh_archive_basename_for_current_release)


def test_v87_startup_refreshes_stale_generator_owned_name(tmp_path: Path) -> None:
    module = generator()
    root = _root(tmp_path, "16.3.25.3.4", "jazn-pack-generator-v87-studio-portable-zip")
    state = module.InteractiveState(
        source=root,
        out_dir=tmp_path / "out",
        archive_basename="jazn_latka_v16.3.25.3.3-chatgpt-package-discovery-bootstrap",
    )
    assert module.refresh_archive_basename_for_current_release(state) is True
    assert state.archive_basename == "jazn_latka_v16.3.25.3.4-jazn-pack-generator-v87-studio-portable-zip"


def test_v87_preserves_explicit_custom_current_name(tmp_path: Path) -> None:
    module = generator()
    root = _root(tmp_path, "16.3.25.3.4", "jazn-pack-generator-v87-studio-portable-zip")
    custom = "backup_K_v16.3.25.3.4-jazn-pack-generator-v87-studio-portable-zip"
    state = module.InteractiveState(source=root, out_dir=tmp_path / "out", archive_basename=custom)
    assert module.refresh_archive_basename_for_current_release(state) is False
    assert state.archive_basename == custom


def test_v87_rejects_windows_reserved_member_name() -> None:
    module = generator()
    plan = SimpleNamespace(entries=[SimpleNamespace(relative="docs/CON.txt")])
    with pytest.raises(module.PackError, match="zarezerwowana"):
        module.validate_portable_member_names(plan)


def test_v87_rejects_windows_casefold_collision() -> None:
    module = generator()
    plan = SimpleNamespace(entries=[
        SimpleNamespace(relative="Latka/File.txt"),
        SimpleNamespace(relative="latka/file.TXT"),
    ])
    with pytest.raises(module.PackError, match="Kolizja nazw"):
        module.validate_portable_member_names(plan)


def test_v87_binary_transport_is_not_claimed_as_direct_windows_zip() -> None:
    module = generator()
    profile = module.interoperability_profile("zip", "binary")
    assert profile["portable_standard_zip"] is False
    assert profile["requires_join"] is True
    assert profile["targets"]["windows_11_file_explorer"] == "join_required"


def test_v87_independent_deflate_profile_is_portable_standard_zip() -> None:
    module = generator()
    profile = module.interoperability_profile("zip", "independent")
    assert profile["portable_standard_zip"] is True
    assert profile["requires_join"] is False
    assert profile["targets"]["windows_11_file_explorer"] == "direct"


def test_v87_standard_writer_uses_deflate_and_unicode_names(tmp_path: Path) -> None:
    module = generator()
    raw = "zażółć gęślą jaźń".encode("utf-8")
    entry = module.PlanEntry(
        relative="docs/zażółć.txt",
        source=None,
        size_bytes=len(raw),
        sha256=module.sha256_bytes(raw),
        classification="test",
        virtual_bytes=raw,
    )
    target = tmp_path / "portable.zip"
    module.write_zip_file(target, [entry], 6)
    with zipfile.ZipFile(target, "r") as archive:
        info = archive.getinfo("docs/zażółć.txt")
        assert info.compress_type == zipfile.ZIP_DEFLATED
        assert archive.read(info) == raw
        assert archive.testzip() is None
'''

DOC_TEXT = r'''# Jaźń Pack Generator v8.7 — Studio i przenośny ZIP

## Cel

Wersja v8.7 utrzymuje dotychczasowy kontrakt generatora i dodaje jawny profil
interoperacyjności dla paczek przeznaczonych do Windows 11 File Explorer,
7-Zip, WinZip i WinRAR. `memory_rebuild` nie jest modyfikowany.

## Standard przenośny

Najbardziej interoperacyjny wariant to:

- kontener `zip`,
- kompresja `ZIP_DEFLATED` (lub STORE dla poziomu 0 tam, gdzie stosowane),
- woluminy `independent`, czyli każdy wynik jest kompletnym ZIP-em,
- nazwy wpisów bez kolizji Windows, urządzeń `CON/PRN/AUX/NUL/COM*/LPT*`,
  końcowych kropek/spacji, znaków zabronionych i casefold collisions,
- CRC + SHA-256 + sidecar kontraktu Jaźni.

`binary` (`.zip.001/.002/...`) pozostaje poprawnym transportem Jaźni i może być
konieczny dla bardzo dużej pamięci, ale nie jest bezpośrednim ZIP-em dla
Explorer/WinZip. Najpierw trzeba go połączyć do pełnego `.zip` (np. przez
wygenerowany `join.ps1`). Raport zgodności v8.7 rozróżnia te dwa przypadki.

## Studio

`python tools/jazn_pack_generator.py studio` uruchamia GUI `tkinter/ttk` z
zakładkami PAKOWANIE, WERYFIKACJA i USTAWIENIA. Na Windows Studio może być
uruchamiane automatycznie przy starcie bez argumentów; można to wyłączyć w
ustawieniach Studio lub zmienną `JAZN_PACK_GENERATOR_NO_STUDIO=1`.

Studio domyślnie włącza Portable ZIP. Tryby 7z, AES ZIP i binary pozostają
jawnie dostępne jako tryby specjalistyczne.

## Nazwa paczki

Przy uruchomieniu generator rozpoznaje nazwy, które sam wcześniej wygenerował
w postaci `jazn_latka_v<wersja>-<release>`, i odświeża je na podstawie
`latka_jazn/version.py`. Własna nazwa użytkownika pozostaje bez zmian.
Zmiana katalogu źródłowego w Studio również odświeża nazwę kanoniczną.
'''


def patch_generator() -> None:
    text = GEN.read_text(encoding="utf-8")
    if "# v8.7 portability + Studio overlay" in text:
        return
    text = text.replace(
        '"""Jaźń / Łatka — generator paczek v8.6, two-file bundled edition.',
        '"""Jaźń / Łatka — generator paczek v8.7, two-file bundled Studio edition.',
        1,
    )
    text = text.replace('GENERATOR_VERSION = "8.6"', 'GENERATOR_VERSION = "8.7"', 1)
    text = text.replace(
        'SETTINGS_SCHEMA = "jazn_pack_generator_settings/v8.6"',
        'SETTINGS_SCHEMA = "jazn_pack_generator_settings/v8.7"',
        1,
    )
    marker = "\ndef __getattr__(name: str) -> _bundle_Any:\n"
    if marker not in text:
        raise SystemExit("generator insertion marker not found")
    text = text.replace(marker, "\n" + textwrap.dedent(OVERLAY).strip() + "\n\n" + marker.lstrip("\n"), 1)
    pattern = re.compile(
        r"def main\(argv: _bundle_Sequence\[str\] \| None = None\) -> int:\n.*?\n(?=if __name__ == \"__main__\":)",
        re.S,
    )
    text, count = pattern.subn(textwrap.dedent(NEW_MAIN).strip() + "\n\n", text, count=1)
    if count != 1:
        raise SystemExit(f"main replacement count={count}")
    GEN.write_text(text, encoding="utf-8")


def patch_version() -> None:
    text = VERSION.read_text(encoding="utf-8")
    text = re.sub(
        r"# v16\.3\.25\.3\.3.*?\n# without consuming the v16\.3\.25\.4 Memory Rebuild release slot\.\n",
        "# v16.3.25.3.4 hardens portable ZIP packaging and adds Pack Generator Studio\n# without consuming the v16.3.25.4 Memory Rebuild release slot.\n",
        text,
        count=1,
        flags=re.S,
    )
    text = text.replace('DISTRIBUTION_VERSION = "16.3.25.3.3"', 'DISTRIBUTION_VERSION = "16.3.25.3.4"', 1)
    text = text.replace('PACKAGE_VERSION = "16.3.25.3.3"', 'PACKAGE_VERSION = "16.3.25.3.4"', 1)
    text = text.replace(
        'PACKAGE_RELEASE_NAME = "chatgpt-package-discovery-bootstrap"',
        'PACKAGE_RELEASE_NAME = "jazn-pack-generator-v87-studio-portable-zip"',
        1,
    )
    VERSION.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    text = OLD_TEST.read_text(encoding="utf-8")
    text = text.replace("v86", "v87").replace('"8.6"', '"8.7"').replace(
        '"jazn_pack_generator_settings/v8.6"', '"jazn_pack_generator_settings/v8.7"'
    )
    NEW_TEST.write_text(text, encoding="utf-8")
    OLD_TEST.unlink()
    REG_TEST.write_text(textwrap.dedent(REGRESSION_TEST).lstrip(), encoding="utf-8")
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(textwrap.dedent(DOC_TEXT).lstrip(), encoding="utf-8")


if __name__ == "__main__":
    patch_generator()
    patch_version()
    patch_tests()
    print("v8.7 patch applied")
