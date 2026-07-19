from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TextIO
import json
import sys

from latka_jazn.tools.chat_export_ui import CursorMenu, explicit_confirmation, json_pretty
from latka_jazn.tools.memory_restore import (
    DEVELOPER_CONFIRMATION,
    SYSTEM_CONFIRMATION,
    MemoryRestoreOrchestrator,
    MemoryRestoreSettings,
    confirmation_token,
    RestoreSource,
    compare_database_sets,
    discover_restore_sources,
    is_known_non_memory_source,
)
from latka_jazn.version import schema_version


CONFIG_SCHEMA_VERSION = schema_version("memory_restore_ui_config")
SUPPORTED_EXTERNAL_SUFFIXES = {".zip", ".json", ".jsonl", ".ndjson", ".html", ".htm"}


def normalize_path_input(raw: str) -> str:
    value = str(raw or "").strip()
    if value.casefold().startswith("cd "):
        value = value[3:].strip()
    return value.strip().strip('"').strip("'")


BOOLEAN_SETTINGS = (
    ("recursive_scan", "Skanuj podkatalogi"),
    ("verify_after_each", "Pełna kontrola po każdym źródle"),
    ("full_validation", "Używaj integrity_check zamiast quick_check"),
    ("continue_on_error", "Kontynuuj po błędzie kolejnego źródła"),
    ("create_backup", "Utwórz spójną kopię istniejących baz"),
    ("audit_classifiers", "Uruchom audyt klasyfikatorów po imporcie"),
    ("reclassify_journal_dry_run", "Wykonaj dry-run reklasyfikacji dziennika"),
    ("apply_reclassification", "Zastosuj reklasyfikację po dry-run"),
    ("analyse_topics", "Analizuj tematy po pełnym imporcie L0"),
    ("force_topics", "Wymuś ponowną analizę istniejących segmentów"),
)


@dataclass(slots=True)
class MemoryRestoreUiState:
    repo_root: Path
    settings: MemoryRestoreSettings
    discovered: list[RestoreSource] = field(default_factory=list)
    selected_paths: list[Path] = field(default_factory=list)
    last_plan: dict | None = None
    last_result: dict | None = None


class MemoryRestoreCursorApp:
    MENU = (
        "Ustaw katalog eksportów",
        "Skanuj i wybierz pliki",
        "Dodaj plik źródłowy spoza katalogu",
        "Wybierz tryb i katalog docelowy",
        "Ustawienia restore",
        "Ustaw bazy porównawcze test_01/test_02",
        "Pokaż plan bez zapisu",
        "Uruchom restore",
        "Porównaj bieżące bazy z test_01/test_02",
        "Zapisz konfigurację JSON",
        "Wczytaj konfigurację JSON",
        "Zakończ",
    )

    def __init__(
        self,
        repo_root: str | Path,
        *,
        settings: MemoryRestoreSettings | None = None,
        input_func: Callable[[str], str] = input,
        output: TextIO | None = None,
    ) -> None:
        root = Path(repo_root).expanduser().resolve()
        default = settings or MemoryRestoreSettings(
            source_directory=str(root.parent),
            target_root=str(root.parent / "jazn_memory_test_03"),
            mode="developer",
        )
        self.state = MemoryRestoreUiState(root, default.normalized())
        self.input = input_func
        self.output = output or sys.stdout

    def run(self) -> int:
        while True:
            title = (
                "Restore pamięci Jaźni — kursorowy orchestrator\n"
                f"Źródła: {self.state.settings.source_directory or '(nie ustawiono)'}\n"
                f"Wybrane: {len(self.state.selected_paths)} plików\n"
                f"Tryb: {self.state.settings.mode}\n"
                f"Cel: {self.state.settings.target_root or '(nie ustawiono)'}"
            )
            choice = CursorMenu(title, list(self.MENU)).choose(output=self.output, input_func=self.input)
            if choice is None:
                continue
            if int(choice) == len(self.MENU) - 1:
                return 0
            try:
                self._dispatch(int(choice))
            except KeyboardInterrupt:
                self._write("Przerwano. Zatwierdzone transakcje pozostają zapisane; aktywna transakcja SQLite została cofnięta.")
                return 130
            except Exception as exc:
                self._write(f"Błąd: {type(exc).__name__}: {exc}")
            self.input("\nEnter — wróć do menu: ")

    def _dispatch(self, choice: int) -> None:
        actions = {
            0: self._set_source_directory,
            1: self._scan_and_select,
            2: self._add_external_source,
            3: self._set_target,
            4: self._settings_page,
            5: self._set_baselines,
            6: self._preview_plan,
            7: self._run_restore,
            8: self._compare_baselines,
            9: self._save_config,
            10: self._load_config,
        }
        actions[choice]()

    def _write(self, text: str) -> None:
        self.output.write(text + "\n")
        self.output.flush()

    def _replace_settings(self, **changes: object) -> None:
        payload = self.state.settings.to_dict()
        payload.update(changes)
        self.state.settings = MemoryRestoreSettings(**payload).normalized()

    def _choose_multi(self, title: str, labels: list[str], initial: set[int]) -> set[int] | None:
        """Multi-select with retained state without changing the shared CursorMenu API."""
        if not sys.stdin.isatty() or not self.output.isatty():
            self._write(title)
            for index, label in enumerate(labels, 1):
                mark = "x" if index - 1 in initial else " "
                self._write(f"{index}. [{mark}] {label}")
            raw = self.input("Numery oddzielone przecinkami; Enter zachowuje wybór; 0 anuluje: ").strip()
            if not raw:
                return set(initial)
            if raw == "0":
                return None
            return {int(value.strip()) - 1 for value in raw.split(",") if value.strip()}

        from latka_jazn.tools.chat_export_ui import TerminalKeySource
        cursor = 0
        selected = set(initial)
        with TerminalKeySource() as source:
            while True:
                self.output.write("\x1b[2J\x1b[H")
                self.output.write(f"{title}\n↑/↓ wybór • Spacja zaznacz • Enter zatwierdź • Esc wróć • Ctrl+X zakończ\n\n")
                for index, label in enumerate(labels):
                    pointer = "▶" if index == cursor else " "
                    mark = "[x]" if index in selected else "[ ]"
                    self.output.write(f"{pointer} {mark} {label}\n")
                self.output.flush()
                key = source.read_key()
                if key == "up":
                    cursor = (cursor - 1) % len(labels)
                elif key == "down":
                    cursor = (cursor + 1) % len(labels)
                elif key == "space":
                    selected.symmetric_difference_update({cursor})
                elif key == "enter":
                    return selected
                elif key == "escape":
                    return None
                elif key == "ctrl_x":
                    raise KeyboardInterrupt

    def _set_source_directory(self) -> None:
        raw = normalize_path_input(self.input(
            f"Katalog eksportów [{self.state.settings.source_directory}] (podaj samą ścieżkę; opcjonalne 'cd ' zostanie usunięte): "
        ))
        if not raw:
            return
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            raise NotADirectoryError(path)
        self._replace_settings(source_directory=str(path))
        self.state.discovered.clear()
        self.state.selected_paths.clear()

    def _scan_and_select(self) -> None:
        if not self.state.settings.source_directory:
            raise RuntimeError("najpierw ustaw katalog eksportów")
        self._write("Skanuję katalog…")
        self.state.discovered = discover_restore_sources(
            self.state.settings.source_directory,
            recursive=self.state.settings.recursive_scan,
        )
        if not self.state.discovered:
            self._write("Nie znaleziono plików ZIP/JSON/JSONL/NDJSON/HTML.")
            return
        selected_now = {path for path in self.state.selected_paths}
        initial = {index for index, item in enumerate(self.state.discovered) if item.path in selected_now}
        labels = [f"{item.suffix.upper():7s} {human_size(item.size_bytes):>10s}  {item.path.name}" for item in self.state.discovered]
        chosen = self._choose_multi(
            "Wybierz źródła do restore\nHTML bez conversations.json będzie tylko odrzucony w planie",
            labels,
            initial,
        )
        if chosen is None:
            return
        discovered_paths = {item.path for item in self.state.discovered}
        external = [path for path in self.state.selected_paths if path not in discovered_paths]
        selected = [self.state.discovered[index].path for index in sorted(chosen)]
        self.state.selected_paths = external + [path for path in selected if path not in external]
        self._write(f"Wybrano {len(self.state.selected_paths)} plików.")

    def _add_external_source(self) -> None:
        raw = normalize_path_input(self.input("Pełna ścieżka dodatkowego ZIP/JSON/JSONL/NDJSON/HTML: "))
        if not raw:
            return
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        suffix = path.suffix.casefold()
        if suffix not in SUPPORTED_EXTERNAL_SUFFIXES:
            raise ValueError(f"nieobsługiwany typ źródła: {suffix or '(brak rozszerzenia)'}")
        if suffix == ".json" and is_known_non_memory_source(path):
            raise ValueError("plik wygląda jak sekret, poświadczenie albo techniczny JSON i nie może być źródłem pamięci")
        if path not in self.state.selected_paths:
            self.state.selected_paths.append(path)
        if all(item.path != path for item in self.state.discovered):
            self.state.discovered.append(RestoreSource(path, path.stat().st_size, suffix))
        self._write(f"Dodano źródło: {path}")

    def _set_target(self) -> None:
        selected = CursorMenu("Tryb docelowy", ["developer — poza repo, np. test_03", "system — bezpośrednio do aktywnego folderu systemu"]).choose(
            output=self.output, input_func=self.input
        )
        if selected is None:
            return
        mode = "developer" if int(selected) == 0 else "system"
        default = self.state.repo_root.parent / "jazn_memory_test_03" if mode == "developer" else self.state.repo_root
        raw = normalize_path_input(self.input(f"Katalog docelowy [{default}]: "))
        target = Path(raw).expanduser().resolve() if raw else default.resolve()
        self._replace_settings(mode=mode, target_root=str(target))

    def _settings_page(self) -> None:
        current = self.state.settings.to_dict()
        initial = {index for index, (key, _) in enumerate(BOOLEAN_SETTINGS) if bool(current[key])}
        labels = [label for _, label in BOOLEAN_SETTINGS]
        chosen = self._choose_multi("Ustawienia restore", labels, initial)
        if chosen is None:
            return
        changes = {key: index in chosen for index, (key, _) in enumerate(BOOLEAN_SETTINGS)}
        raw_limit = self.input(f"Limit próbki kandydatów [0 = wyłączone, obecnie {self.state.settings.candidate_limit}]: ").strip()
        if raw_limit:
            changes["candidate_limit"] = max(0, int(raw_limit))
        raw_progress = self.input(
            f"Raport postępu co N rozmów [obecnie {self.state.settings.progress_every_conversations}]: "
        ).strip()
        if raw_progress:
            changes["progress_every_conversations"] = max(1, int(raw_progress))
        self._replace_settings(**changes)

    def _set_baselines(self) -> None:
        current = list(self.state.settings.baseline_roots)
        first_default = current[0] if len(current) > 0 else str(self.state.repo_root.parent / "jazn_memory_test_01")
        second_default = current[1] if len(current) > 1 else str(self.state.repo_root.parent / "jazn_memory_test_02")
        first_raw = normalize_path_input(self.input(f"Katalog test_01 [{first_default}]: "))
        second_raw = normalize_path_input(self.input(f"Katalog test_02 [{second_default}]: "))
        roots: list[str] = []
        for raw, default in ((first_raw, first_default), (second_raw, second_default)):
            value = raw or default
            path = Path(value).expanduser().resolve()
            if not path.is_dir():
                raise NotADirectoryError(path)
            roots.append(str(path))
        self._replace_settings(baseline_roots=roots)

    def _orchestrator(self) -> MemoryRestoreOrchestrator:
        return MemoryRestoreOrchestrator(
            self.state.settings,
            tool_root=self.state.repo_root,
            callback=self._progress,
        )

    def _require_selection(self) -> list[Path]:
        if not self.state.selected_paths:
            raise RuntimeError("najpierw zeskanuj i zaznacz źródła")
        return list(self.state.selected_paths)

    def _preview_plan(self) -> None:
        plan = self._orchestrator().plan(self._require_selection())
        self.state.last_plan = plan.to_dict()
        self._write(json_pretty(self.state.last_plan))

    def _run_restore(self) -> None:
        sources = self._require_selection()
        orchestrator = self._orchestrator()
        plan = orchestrator.plan(sources)
        self.state.last_plan = plan.to_dict()
        self._write(json_pretty({
            "ok": plan.ok,
            "mode": self.state.settings.mode,
            "target_root": self.state.settings.target_root,
            "chat_sources": len(plan.chats),
            "journal_sources": len(plan.journals),
            "rejected": plan.rejected,
            "blocking_errors": plan.target_preflight.get("blocking_errors", []),
            "settings": self.state.settings.to_dict(),
        }))
        if not plan.ok:
            self._write("Plan jest zablokowany. Nie uruchomiono zapisu.")
            return
        token = confirmation_token(self.state.settings)
        prompt = f"Wpisz dokładnie {token}, aby rozpocząć restore: "
        if not explicit_confirmation(self.input, prompt, token=token):
            self._write("Restore anulowany — bazy nie zostały zmienione.")
            return
        result = orchestrator.run(sources, confirmation=token, prepared_plan=plan)
        self.state.last_result = result
        self._write(json_pretty(result))

    def _compare_baselines(self) -> None:
        if not self.state.settings.baseline_roots:
            raise RuntimeError("najpierw ustaw katalogi baz test_01/test_02")
        report = compare_database_sets(self.state.settings.target_root, self.state.settings.baseline_roots)
        target = Path(self.state.settings.target_root) / "reports" / "memory_restore" / "manual_baseline_comparison.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        self._write(json_pretty(report))
        self._write(f"Raport: {target}")

    def _save_config(self) -> None:
        default = self.state.repo_root.parent / "restore_memory_test_03.json"
        raw = normalize_path_input(self.input(f"Plik konfiguracji [{default}]: "))
        candidate = Path(raw).expanduser() if raw else default
        if not candidate.is_absolute():
            candidate = default.parent / candidate
        if candidate.suffix.casefold() != ".json":
            candidate = candidate.with_suffix(".json")
        path = candidate.resolve()
        try:
            path.relative_to(self.state.repo_root)
        except ValueError:
            pass
        else:
            raise ValueError("konfiguracja restore musi być zapisana poza repozytorium")
        payload = {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "settings": self.state.settings.to_dict(),
            "selected_sources": [str(path) for path in self.state.selected_paths],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._write(f"Zapisano: {path}")

    def _load_config(self) -> None:
        raw = normalize_path_input(self.input("Ścieżka konfiguracji JSON: "))
        if not raw:
            return
        path = Path(raw).expanduser().resolve()
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        self.state.settings = MemoryRestoreSettings.from_json(path)
        configured = payload.get("selected_sources", []) if isinstance(payload, dict) else []
        selected: list[Path] = []
        missing: list[str] = []
        for item in configured if isinstance(configured, list) else []:
            source = Path(str(item)).expanduser().resolve()
            if source.is_file():
                selected.append(source)
            else:
                missing.append(str(source))
        self.state.discovered.clear()
        self.state.selected_paths = selected
        self._write(f"Wczytano konfigurację i {len(selected)} istniejących źródeł.")
        if missing:
            self._write("Brakujące źródła: " + "; ".join(missing))

    def _progress(self, event: dict) -> None:
        name = str(event.get("event", "progress"))
        source = Path(str(event.get("source", ""))).name if event.get("source") else ""
        pieces = [name]
        if source:
            pieces.append(source)
        for key in ("stage", "index", "total", "conversations", "nodes", "messages", "elapsed_seconds", "ok"):
            if key in event:
                pieces.append(f"{key}={event[key]}")
        self._write("[restore] " + " | ".join(pieces))


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


__all__ = [
    "MemoryRestoreCursorApp", "MemoryRestoreUiState", "human_size", "normalize_path_input",
]
