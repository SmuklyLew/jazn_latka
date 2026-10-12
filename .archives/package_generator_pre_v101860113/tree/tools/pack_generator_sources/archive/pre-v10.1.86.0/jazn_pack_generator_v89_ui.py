from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

UI_MODE_CHOICES = (
    "tekstowy",
    "kursorowy",
    "studio-terminal",
    "studio-windows",
    "studio-linux",
)
UI_MODE_LABELS = {
    "tekstowy": "tekstowy",
    "kursorowy": "kursorowy",
    "studio-terminal": "Studio w terminalu",
    "studio-windows": "Studio dla Windows",
    "studio-linux": "Studio dla Linuksa",
}
DEFAULT_DISTRIBUTION_MODE = "system-portable"
_CORE: Any = None


def bind(core: Any) -> None:
    global _CORE
    _CORE = core


def _core() -> Any:
    if _CORE is None:
        raise RuntimeError("Pack Generator 8.9 UI overlay is not bound")
    return _CORE


def normalize_ui_mode(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw in UI_MODE_CHOICES:
        return raw
    by_label = {label.casefold(): key for key, label in UI_MODE_LABELS.items()}
    key = by_label.get(raw.casefold())
    if key:
        return key
    raise ValueError(f"unsupported UI mode: {value!r}")


def _settings_path() -> Path:
    legacy_core = _core()._legacy_core()
    if legacy_core is None or not callable(getattr(legacy_core, "settings_path", None)):
        return Path(__file__).with_name("jazn_pack_generator_settings.json")
    return Path(legacy_core.settings_path()).expanduser().resolve()


def _read_settings_payload() -> dict[str, Any]:
    path = _settings_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def studio_preferences() -> dict[str, Any]:
    payload = _read_settings_payload()
    raw = payload.get("studio_v89")
    if isinstance(raw, dict):
        prefs = dict(raw)
    else:
        old = payload.get("studio_v87")
        prefs = dict(old) if isinstance(old, dict) else {}
    fallback_ui = "studio-windows" if os.name == "nt" else ("studio-linux" if sys.platform.startswith("linux") else "studio-terminal")
    try:
        ui_mode = normalize_ui_mode(str(prefs.get("ui_mode") or fallback_ui))
    except ValueError:
        ui_mode = fallback_ui
    return {
        "ui_mode": ui_mode,
        "ui_auto_start": bool(prefs.get("ui_auto_start", prefs.get("auto_start", False))),
        "distribution_mode": str(prefs.get("distribution_mode") or DEFAULT_DISTRIBUTION_MODE),
        "target_alias": str(prefs.get("target_alias") or "current"),
        "python_version": str(prefs.get("python_version") or "current"),
        "dependency_bundle": str(prefs.get("dependency_bundle") or ""),
        "materialize_dependencies": bool(prefs.get("materialize_dependencies", False)),
    }


def save_studio_preferences(**updates: Any) -> dict[str, Any]:
    core = _core()
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_settings_payload()
    prefs = studio_preferences()
    prefs.update(updates)
    prefs["ui_mode"] = normalize_ui_mode(str(prefs.get("ui_mode") or "tekstowy"))
    if prefs["distribution_mode"] not in core.DISTRIBUTION_MODE_CHOICES:
        raise ValueError(f"unsupported distribution mode: {prefs['distribution_mode']!r}")
    if prefs["target_alias"] not in core.DISTRIBUTION_TARGET_CHOICES:
        raise ValueError(f"unsupported target: {prefs['target_alias']!r}")
    core.normalize_distribution_python_version(str(prefs["python_version"]))
    payload["schema_version"] = core.SETTINGS_SCHEMA
    payload["generator_version"] = core.GENERATOR_VERSION
    payload["studio_v89"] = prefs
    temp = path.with_name(path.name + ".v89.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return prefs


def run_terminal_studio(*, input_fn: Callable[[str], str] = input, output_fn: Callable[[str], Any] = print) -> int:
    core = _core()
    prefs = studio_preferences()
    output_fn(f"Jaźń Pack Generator Studio v{core.GENERATOR_VERSION} — terminal")
    output_fn("Polecenia: [p] pakuj, [s] ustawienia, [q] wyjście")
    while True:
        output_fn(
            f"Tryb={prefs['distribution_mode']} target={prefs['target_alias']} "
            f"Python={prefs['python_version']} bundle={prefs['dependency_bundle'] or '<auto>'}"
        )
        command = str(input_fn("studio> ")).strip().lower()
        if command in {"q", "quit", "exit"}:
            return 0
        if command in {"s", "settings"}:
            output_fn("UI: " + ", ".join(f"{key}={UI_MODE_LABELS[key]}" for key in UI_MODE_CHOICES))
            ui = str(input_fn(f"UI [{prefs['ui_mode']}]: ")).strip() or prefs["ui_mode"]
            mode = str(input_fn(f"Pakiet [{prefs['distribution_mode']}]: ")).strip() or prefs["distribution_mode"]
            target = str(input_fn(f"Target [{prefs['target_alias']}]: ")).strip() or prefs["target_alias"]
            python_version = str(input_fn(f"Python [{prefs['python_version']}]: ")).strip() or prefs["python_version"]
            prefs = save_studio_preferences(ui_mode=ui, distribution_mode=mode, target_alias=target, python_version=python_version)
            continue
        if command in {"p", "pack"}:
            source = str(input_fn("Źródło [.]: ")).strip() or "."
            out_dir = str(input_fn("Katalog wynikowy [dist]: ")).strip() or "dist"
            try:
                report = core.run_distribution_pack(
                    source=source,
                    out_dir=out_dir,
                    mode=prefs["distribution_mode"],
                    target_alias=prefs["target_alias"],
                    python_version=prefs["python_version"],
                    dependency_bundle=prefs["dependency_bundle"] or None,
                    materialize_dependencies=bool(prefs["materialize_dependencies"]),
                )
                output_fn(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            except Exception as exc:
                output_fn(f"BŁĄD: {type(exc).__name__}: {exc}")
            continue
        output_fn("Nieznane polecenie.")


def _platform_guard(platform_mode: str) -> None:
    if platform_mode == "windows" and os.name != "nt":
        raise RuntimeError("Studio dla Windows można uruchomić wyłącznie na Windows.")
    if platform_mode == "linux" and not sys.platform.startswith("linux"):
        raise RuntimeError("Studio dla Linuksa można uruchomić wyłącznie na Linuksie.")


def run_studio(*, platform_mode: str | None = None) -> int:
    core = _core()
    requested = platform_mode or ("windows" if os.name == "nt" else "linux" if sys.platform.startswith("linux") else "generic")
    if requested in {"windows", "linux"}:
        _platform_guard(requested)
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise RuntimeError("Tkinter nie jest dostępny w tej instalacji Pythona.") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError(f"Brak sesji graficznej: {exc}") from exc

    prefs = studio_preferences()
    root.title(f"Jaźń Pack Generator Studio v{core.GENERATOR_VERSION} — {requested}")
    root.geometry("1160x760")
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=12, pady=12)
    pack_tab = ttk.Frame(notebook, padding=14)
    settings_tab = ttk.Frame(notebook, padding=14)
    notebook.add(pack_tab, text="PAKOWANIE")
    notebook.add(settings_tab, text="USTAWIENIA")
    pack_tab.columnconfigure(1, weight=1)

    source_var = tk.StringVar(value=str(Path.cwd()))
    out_var = tk.StringVar(value=str(Path.cwd() / "dist"))
    mode_var = tk.StringVar(value=prefs["distribution_mode"])
    target_var = tk.StringVar(value=prefs["target_alias"])
    python_var = tk.StringVar(value=prefs["python_version"])
    bundle_var = tk.StringVar(value=prefs["dependency_bundle"])
    materialize_var = tk.BooleanVar(value=bool(prefs["materialize_dependencies"]))
    ui_var = tk.StringVar(value=prefs["ui_mode"])
    autostart_var = tk.BooleanVar(value=bool(prefs["ui_auto_start"]))
    status_var = tk.StringVar(value="Gotowe.")

    def add_row(row: int, label: str, variable, browse=None):
        ttk.Label(pack_tab, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(pack_tab, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        if browse:
            ttk.Button(pack_tab, text="Wybierz…", command=browse).grid(row=row, column=2, pady=5)

    add_row(0, "System Jaźni", source_var, lambda: source_var.set(filedialog.askdirectory() or source_var.get()))
    add_row(1, "Katalog wynikowy", out_var, lambda: out_var.set(filedialog.askdirectory() or out_var.get()))
    ttk.Label(pack_tab, text="Tryb dystrybucji").grid(row=2, column=0, sticky="w", pady=5)
    ttk.Combobox(pack_tab, textvariable=mode_var, values=core.DISTRIBUTION_MODE_CHOICES, state="readonly").grid(row=2, column=1, sticky="ew", padx=8)
    ttk.Label(pack_tab, text="Target").grid(row=3, column=0, sticky="w", pady=5)
    ttk.Combobox(pack_tab, textvariable=target_var, values=core.DISTRIBUTION_TARGET_CHOICES, state="readonly").grid(row=3, column=1, sticky="ew", padx=8)
    ttk.Label(pack_tab, text="Python").grid(row=4, column=0, sticky="w", pady=5)
    ttk.Combobox(pack_tab, textvariable=python_var, values=core.DISTRIBUTION_PYTHON_CHOICES, state="readonly").grid(row=4, column=1, sticky="ew", padx=8)
    add_row(5, "Zweryfikowany bundle zależności", bundle_var, lambda: bundle_var.set(filedialog.askdirectory() or bundle_var.get()))
    ttk.Checkbutton(pack_tab, text="Utwórz bundle zależności natywnie, jeśli go brakuje", variable=materialize_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=5)
    log = tk.Text(pack_tab, height=18, wrap="word")
    log.grid(row=9, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    pack_tab.rowconfigure(9, weight=1)

    def persist() -> dict[str, Any]:
        return save_studio_preferences(
            ui_mode=ui_var.get(), ui_auto_start=autostart_var.get(),
            distribution_mode=mode_var.get(), target_alias=target_var.get(),
            python_version=python_var.get(), dependency_bundle=bundle_var.get().strip(),
            materialize_dependencies=materialize_var.get(),
        )

    def pack_now() -> None:
        try:
            persist()
            report = core.run_distribution_pack(
                source=source_var.get(), out_dir=out_var.get(), mode=mode_var.get(),
                target_alias=target_var.get(), python_version=python_var.get(),
                dependency_bundle=bundle_var.get().strip() or None,
                materialize_dependencies=materialize_var.get(),
            )
            text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
            status_var.set("Pakowanie zakończone poprawnie.")
        except Exception as exc:
            text = f"BŁĄD: {type(exc).__name__}: {exc}"
            status_var.set("Pakowanie zakończone błędem.")
            messagebox.showerror("Generator", text)
        log.delete("1.0", "end")
        log.insert("end", text)

    ttk.Button(pack_tab, text="PAKUJ v3", command=pack_now).grid(row=7, column=0, sticky="w", pady=10)
    ttk.Label(pack_tab, textvariable=status_var).grid(row=7, column=1, sticky="w", padx=8)

    ttk.Label(settings_tab, text="Interfejs uruchamiany przez Generator").pack(anchor="w", pady=(4, 2))
    ttk.Combobox(settings_tab, textvariable=ui_var, values=UI_MODE_CHOICES, state="readonly", width=28).pack(anchor="w", pady=(0, 8))
    ttk.Label(settings_tab, text=";  ".join(f"{key} = {UI_MODE_LABELS[key]}" for key in UI_MODE_CHOICES), wraplength=920).pack(anchor="w", pady=(0, 10))
    ttk.Checkbutton(settings_tab, text="Uruchamiaj wybrany interfejs bez argumentów", variable=autostart_var).pack(anchor="w", pady=5)
    ttk.Button(settings_tab, text="ZAPISZ USTAWIENIA", command=persist).pack(anchor="w", pady=10)

    root.protocol("WM_DELETE_WINDOW", lambda: (persist(), root.destroy()))
    root.mainloop()
    return 0


def run_ui_mode(mode: str, argv: Sequence[str] | None = None) -> int:
    core = _core()
    normalized = normalize_ui_mode(mode)
    if normalized == "tekstowy":
        return int(core.legacy._impl.interactive(ui_override="tekstowy"))
    if normalized == "kursorowy":
        return int(core.legacy._impl.interactive(ui_override="kursorowy"))
    if normalized == "studio-terminal":
        return run_terminal_studio()
    if normalized == "studio-windows":
        return run_studio(platform_mode="windows")
    if normalized == "studio-linux":
        return run_studio(platform_mode="linux")
    raise AssertionError(normalized)


def main(argv: Sequence[str] | None = None) -> int:
    core = _core()
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "ui":
        parser = argparse.ArgumentParser(prog="jazn_pack_generator.py ui", allow_abbrev=False)
        parser.add_argument("mode", choices=UI_MODE_CHOICES)
        args = parser.parse_args(raw[1:])
        return run_ui_mode(args.mode, raw[2:])
    if raw and raw[0] == "studio":
        prefs = studio_preferences()
        mode = prefs["ui_mode"]
        if mode not in {"studio-terminal", "studio-windows", "studio-linux"}:
            mode = "studio-windows" if os.name == "nt" else "studio-linux" if sys.platform.startswith("linux") else "studio-terminal"
        return run_ui_mode(mode)
    if not raw:
        prefs = studio_preferences()
        if prefs.get("ui_auto_start"):
            return run_ui_mode(str(prefs["ui_mode"]))
    return int(core.main(raw))
