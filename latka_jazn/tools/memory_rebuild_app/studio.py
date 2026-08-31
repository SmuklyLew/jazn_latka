from __future__ import annotations

"""Canonical Jaźń Memory Rebuild Studio.

One state machine owns TESTY, PROJEKTOWANIE and USTAWIENIA. Actions open
theme-aware modal dialogs and call the engine directly; the application never
starts another Memory Rebuild UI.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
import json
import os

from latka_jazn.version import PACKAGE_VERSION

from .application import MemoryRebuildApplicationService
from .layout import build_studio_layout
from .models import DEFAULT_SETTINGS
from .project_store import ProjectStore
from .settings import (
    MemoryRebuildSettings,
    MemoryRebuildStudioPreferences,
    MemoryRebuildToolSettings,
    load_tool_settings,
    resolve_settings_path,
    save_tool_settings,
)
from .studio_dialogs import DialogBackend, TextDialogs, make_dialogs
from .studio_workflows import StudioWorkflows
from .test_spec import TEST_PROTOCOL_ORDER, TEST_SPECS, get_test_spec
from .themes import THEMES, get_theme, prompt_toolkit_style


STUDIO_VERSION = "memory-rebuild-studio/v16.3.20"
PAGE_IDS = ("tests", "design", "settings")
PAGE_LABELS = {
    "tests": "TESTY",
    "design": "PROJEKTOWANIE",
    "settings": "USTAWIENIA",
}


@dataclass(frozen=True, slots=True)
class PageItem:
    key: str
    label: str
    hint: str = ""


DESIGN_ITEMS: tuple[PageItem, ...] = (
    PageItem("project", "Projekt i źródła", "Projekt, źródła, baseline’y, role i pipeline’y."),
    PageItem("database", "Baza docelowa", "Jedna kanoniczna memory_jazn.sqlite3 i jej walidacja."),
    PageItem("import", "Import źródeł", "Rozmowy, HTML, dzienniki, nowe wątki i migracja starych baz."),
    PageItem("candidates", "Kandydaci pamięci", "Ręczny review L1 bez automatycznego L2/L3."),
    PageItem("plan", "Plan bez zapisu", "Preflight i dokładny plan bez uruchamiania odbudowy."),
    PageItem("rebuild", "Wykonaj odbudowę", "Jawnie potwierdzony zapis zgodnie z aktualnym planem."),
    PageItem("compare", "Porównanie z baseline", "Porównanie celu z zachowanymi Testami 01–04."),
    PageItem("export", "Finalny eksport", "Staging, pełna walidacja i atomowa publikacja."),
    PageItem("recall", "Recall / benchmark", "FTS5 baseline i mierzalny benchmark przed eksperymentami A/B."),
)

SETTINGS_ITEMS: tuple[PageItem, ...] = (
    PageItem("all", "Wszystkie ustawienia", "Centrum ustawień narzędzia i projektu."),
    PageItem("project-settings", "Ustawienia projektu", "Skanowanie, walidacja, backup i klasyfikacja."),
    PageItem("retrieval", "FTS / retrieval / embeddings", "Parametry wyszukiwania i opcjonalnych embeddingów."),
    PageItem("safety", "Granice bezpieczeństwa", "Wymuszone blokady automatycznej promocji i aktywacji."),
    PageItem("paths", "Ścieżki i środowisko", "Projekt, baza, settings JSON i katalog narzędzia."),
    PageItem("theme", "Wygląd / theme", "Spójna paleta shellu i wszystkich dialogów."),
)

PROJECT_LOCKED_SETTINGS = frozenset(
    {"automatic_experience_approval", "automatic_l2", "automatic_l3"}
)
PROJECT_RISKY_TRUE = frozenset(
    {"continue_on_error", "apply_reclassification", "force_topics", "system_acceptance"}
)
PROJECT_RISKY_FALSE = frozenset(
    {
        "verify_after_each",
        "full_validation",
        "create_backup",
        "audit_classifiers",
        "hash_sources_during_scan",
        "preserve_all_chat_branches",
        "preserve_exact_source_text",
    }
)

PROJECT_SETTING_LABELS: dict[str, str] = {
    "recursive_scan": "Skanuj podfoldery",
    "verify_after_each": "Weryfikuj po każdym etapie",
    "full_validation": "Pełna walidacja",
    "continue_on_error": "Kontynuuj po błędzie",
    "create_backup": "Twórz backup",
    "audit_classifiers": "Audyt klasyfikatorów",
    "reclassify_journal_dry_run": "Reklasyfikacja dziennika — dry-run",
    "apply_reclassification": "Zastosuj reklasyfikację",
    "analyse_topics": "Analizuj tematy",
    "force_topics": "Wymuś analizę tematów",
    "candidate_limit": "Limit kandydatów (0 = bez limitu)",
    "progress_every_conversations": "Raport postępu co N rozmów",
    "hash_sources_during_scan": "SHA-256 źródeł podczas skanu",
    "verify_zip_crc_during_scan": "CRC ZIP podczas skanu",
    "preserve_all_chat_branches": "Zachowaj wszystkie gałęzie rozmów",
    "preserve_exact_source_text": "Zachowaj dokładny tekst źródłowy",
    "automatic_experience_approval": "Automatyczna akceptacja experience",
    "automatic_l2": "Automatyczne L2",
    "automatic_l3": "Automatyczne L3",
}


def _yes_no(value: Any) -> str:
    return "TAK" if bool(value) else "NIE"


def _value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return _yes_no(value)
    return str(value)


def _runtime_lines(settings: MemoryRebuildSettings) -> list[str]:
    return [
        f"retrieval_limit: {settings.retrieval_limit}  [EDYTOWALNE 1..500]",
        f"min_lexical_score: {settings.min_lexical_score}  [EDYTOWALNE 0..1]",
        f"embeddings_enabled: {_yes_no(settings.embeddings_enabled)}  [EDYTOWALNE]",
        f"embedding_model: {_value(settings.embedding_model)}  [EDYTOWALNE]",
        f"require_fts5: {_yes_no(settings.require_fts5)}  [READ-ONLY — wymagane]",
        f"require_provenance: {_yes_no(settings.require_provenance)}  [READ-ONLY — wymagane]",
        f"automatic_l2: {_yes_no(settings.automatic_l2)}  [READ-ONLY / ZABLOKOWANE]",
        f"automatic_l3: {_yes_no(settings.automatic_l3)}  [READ-ONLY / ZABLOKOWANE]",
        f"automatic_activation: {_yes_no(settings.automatic_activation)}  [READ-ONLY / ZABLOKOWANE]",
    ]


def _recall_status_lines() -> list[str]:
    return [
        "[Recall benchmark]",
        "baseline: fts5-bm25/v1  [READ-ONLY]",
        "query_rewrite: NIEIMPLEMENTOWANE  [READ-ONLY]",
        "dense_retrieval: NIEIMPLEMENTOWANE  [READ-ONLY]",
        "reranker: NIEIMPLEMENTOWANE  [READ-ONLY]",
        "model_training: NIE  [READ-ONLY / ZABLOKOWANE]",
    ]


def _project_setting_lines(project: dict[str, Any] | None) -> list[str]:
    raw = dict(project.get("settings") or {}) if project else {}
    result: list[str] = []
    for key, default in DEFAULT_SETTINGS.items():
        value = raw.get(key, default)
        if key in PROJECT_LOCKED_SETTINGS:
            marker = "[READ-ONLY / ZABLOKOWANE]"
        elif key in PROJECT_RISKY_TRUE or key in PROJECT_RISKY_FALSE:
            marker = "[EDYTOWALNE — mniej bezpieczna wartość wymaga potwierdzenia]"
        else:
            marker = "[EDYTOWALNE]"
        result.append(f"{key}: {_value(value)}  {marker}")
    for key, value in sorted(raw.items()):
        if key in DEFAULT_SETTINGS or key.startswith("_"):
            continue
        if key == "unified_database_path":
            marker = "[READ-ONLY tutaj — zmień w „Baza docelowa”]"
        elif key in {"test04_acceptance_report", "system_acceptance"}:
            marker = "[EDYTOWALNE]"
        else:
            marker = "[READ-ONLY — rozszerzenie projektu]"
        result.append(f"{key}: {_value(value)}  {marker}")
    return result


@dataclass(slots=True)
class StudioAction:
    kind: str
    value: str | None = None


@dataclass(slots=True)
class StudioState:
    database: Path
    project_root: str | Path | None
    project: str | None
    tool_root: Path
    settings_path: str | Path | None = None
    active_page: str = "tests"
    selected: dict[str, int] = field(default_factory=lambda: {page: 0 for page in PAGE_IDS})
    theme_name: str = "latka-terminal"
    status: str = "Gotowe. Wybierz stronę i operację."
    status_kind: str = "ok"
    project_snapshot: dict[str, Any] | None = None
    project_error: str | None = None
    runtime_settings: MemoryRebuildSettings = field(default_factory=MemoryRebuildSettings)
    test_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    protocol_service: MemoryRebuildApplicationService | None = field(default=None, repr=False)
    dialogs: DialogBackend | None = field(default=None, repr=False)
    settings_file: Path = field(init=False)
    tool_settings: MemoryRebuildToolSettings = field(init=False)

    def __post_init__(self) -> None:
        self.database = Path(self.database).expanduser().resolve()
        self.tool_root = Path(self.tool_root).expanduser().resolve()
        self.settings_file = resolve_settings_path(self.settings_path, tool_root=self.tool_root)
        self.tool_settings = load_tool_settings(
            self.settings_file,
            tool_root=self.tool_root,
            create=True,
        )
        if self.tool_settings.studio.theme_name not in THEMES:
            raise ValueError(
                f"Nieznany theme w {self.settings_file}: "
                f"{self.tool_settings.studio.theme_name!r}"
            )
        self.settings_path = self.settings_file
        self.runtime_settings = self.tool_settings.runtime
        self.theme_name = self.tool_settings.studio.theme_name
        self.refresh()

    def bind_dialogs(self, dialogs: DialogBackend) -> None:
        self.dialogs = dialogs

    def refresh(self) -> None:
        self.project_snapshot = None
        self.project_error = None
        if not self.project:
            return
        try:
            loaded = ProjectStore(self.project_root).load(self.project)
            self.project = loaded.project_id
            self.project_snapshot = loaded.to_dict()
        except Exception as exc:
            self.project_error = f"project: {type(exc).__name__}: {exc}"

    def select_project(self, identifier: str | None) -> None:
        if identifier is None:
            self.project = None
            self.refresh()
            return
        loaded = ProjectStore(self.project_root).load(identifier)
        self.project = loaded.project_id
        configured = str(loaded.settings.get("unified_database_path") or "").strip()
        if configured:
            self.database = Path(configured).expanduser().resolve()
        elif loaded.target_root:
            self.database = (
                Path(loaded.target_root).expanduser().resolve() / "memory_jazn.sqlite3"
            )
        self.refresh()
        self.status = f"Projekt: {loaded.name}"
        self.status_kind = "ok"

    def set_database(self, path: str | Path, *, remember: bool = True) -> None:
        self.database = Path(path).expanduser().resolve()
        if remember and self.project:
            store = ProjectStore(self.project_root)
            loaded = store.load(self.project)
            loaded.settings["unified_database_path"] = str(self.database)
            store.save(loaded)
            self.project = loaded.project_id
        self.refresh()
        self.status = f"Baza: {self.database}"
        self.status_kind = "ok"

    def save_tool_settings(self) -> Path:
        path = save_tool_settings(
            self.tool_settings,
            self.settings_file,
            tool_root=self.tool_root,
        )
        self.settings_path = path
        self.runtime_settings = self.tool_settings.runtime
        return path

    def set_runtime(self, runtime: MemoryRebuildSettings) -> Path:
        self.tool_settings = self.tool_settings.with_runtime(runtime)
        return self.save_tool_settings()

    def set_theme(self, name: str) -> Path:
        if name not in THEMES:
            raise ValueError(f"Nieznany theme: {name}")
        self.tool_settings = self.tool_settings.with_studio(
            MemoryRebuildStudioPreferences(theme_name=name)
        )
        self.theme_name = name
        return self.save_tool_settings()

    def cycle_theme_persistent(self) -> Path:
        names = tuple(THEMES)
        try:
            index = names.index(self.theme_name)
        except ValueError:
            index = -1
        return self.set_theme(names[(index + 1) % len(names)])

    def set_page(self, page: str) -> None:
        if page not in PAGE_IDS:
            raise ValueError(page)
        self.active_page = page

    def cycle_page(self, delta: int) -> None:
        index = PAGE_IDS.index(self.active_page)
        self.active_page = PAGE_IDS[(index + delta) % len(PAGE_IDS)]

    def items(self) -> Sequence[PageItem]:
        if self.active_page == "tests":
            return tuple(PageItem(item.profile, item.label, item.goal) for item in TEST_SPECS)
        if self.active_page == "design":
            return DESIGN_ITEMS
        return SETTINGS_ITEMS

    def move_selection(self, delta: int) -> None:
        items = self.items()
        if not items:
            return
        current = self.selected.get(self.active_page, 0)
        self.selected[self.active_page] = (current + delta) % len(items)

    def current_item(self) -> PageItem:
        items = self.items()
        index = min(self.selected.get(self.active_page, 0), max(0, len(items) - 1))
        return items[index]

    def header_fragments(self):
        theme = get_theme(self.theme_name)
        project_name = (self.project_snapshot or {}).get("name") or "bez projektu"
        return [
            ("class:header-title", f"  {theme.title}  "),
            ("class:header-version", f"{STUDIO_VERSION}   "),
            ("class:muted", f"projekt: {project_name}"),
            ("", "\n"),
            ("class:muted", f"  baza: {self.database}"),
        ]

    def tab_fragments(self):
        fragments: list[tuple[str, str]] = [("", "  ")]
        for page in PAGE_IDS:
            style = "class:tab-active" if page == self.active_page else "class:tab"
            fragments.append((style, f" {PAGE_LABELS[page]} "))
            fragments.append(("class:tabs", "  "))
        return fragments

    def sidebar_fragments(self):
        fragments: list[tuple[str, str]] = []
        selected = self.selected.get(self.active_page, 0)
        for index, item in enumerate(self.items()):
            style = "class:selected" if index == selected else "class:sidebar"
            marker = "›" if index == selected else " "
            fragments.append((style, f" {marker} {item.label}\n"))
        return fragments

    def _project_lines(self) -> list[str]:
        project = self.project_snapshot
        if project is None:
            lines = ["Projekt: nie wybrano."]
            if self.project_error:
                lines.append(self.project_error)
            lines.append("Otwórz „Projekt i źródła”, aby wybrać lub utworzyć projekt.")
            return lines
        return [
            f"Nazwa: {project.get('name')}",
            f"Tryb: {project.get('mode')}",
            f"Target root: {project.get('target_root')}",
            f"Folder źródeł: {project.get('source_directory') or '—'}",
            f"Źródła: {len(project.get('sources') or [])}",
            f"Baseline’y: {len(project.get('baselines') or [])}",
            f"Revision: {project.get('revision')}",
        ]

    def _test_detail(self, profile: str) -> list[str]:
        spec = get_test_spec(profile)
        result = self.test_results.get(profile)
        outcome = (
            str(result.get("outcome") or ("PASSED" if result.get("ok") else "FAILED"))
            if result
            else "NOT RUN"
        )
        lines = [
            spec.label,
            "",
            "CEL",
            f"  {spec.goal}",
            "",
            "WEJŚCIA",
            *(f"  • {value}" for value in spec.inputs),
            "",
            "GOTOWOŚĆ",
            *(f"  • {value}" for value in spec.readiness),
            "",
            "FAZY",
            f"  {' → '.join(spec.phases)}",
            "",
            "KONTROLE",
            *(f"  ✓ {value}" for value in spec.checks),
            "",
            "WYNIK",
            f"  {outcome}",
            "",
            "DOWODY",
        ]
        if result:
            for evidence_key in (
                "run_id",
                "database_sha256",
                "baseline_id",
                "sanitized_report",
            ):
                if result.get(evidence_key) is not None:
                    lines.append(f"  {evidence_key}: {result.get(evidence_key)}")
            if result.get("quality_gate_passed") is not None:
                lines.append(
                    f"  quality_gate_passed: {result.get('quality_gate_passed')}"
                )
            if lines[-1] == "DOWODY":
                lines.append("  raport istnieje, ale nie zawiera skróconych pól dowodowych")
        else:
            lines.append("  brak — protokół nie był uruchamiany w tej sesji")
        lines.extend(("", "WYJŚCIA"))
        lines.extend(f"  • {value}" for value in spec.outputs)
        lines.extend(("", "GRANICA PRAWDY"))
        lines.extend(f"  • {value}" for value in spec.truth_boundary)
        lines.extend(("", "R/Enter uruchamia protokół lub jego aktualny validator."))
        return lines

    def _design_detail(self, key: str) -> list[str]:
        item = next(value for value in DESIGN_ITEMS if value.key == key)
        lines = [item.label, "", item.hint, "", "Stan projektu:"]
        lines.extend(f"  {value}" for value in self._project_lines())
        lines.extend(
            (
                "",
                f"Kanoniczna baza: {self.database}",
                f"Istnieje: {_yes_no(self.database.is_file())}",
            )
        )
        if key == "plan":
            lines.extend(("", "Plan bez zapisu nie uruchamia odbudowy."))
        elif key == "rebuild":
            lines.extend(
                (
                    "",
                    "Zapis wymaga poprawnego preflightu, planu i ręcznego tokenu potwierdzenia.",
                    "Brak automatycznej akceptacji experience i promocji L2/L3.",
                )
            )
        elif key == "compare":
            lines.extend(("", "Baseline’y pozostają tylko do odczytu."))
        elif key == "candidates":
            lines.extend(("", "Każda decyzja review jest jawna i zapisywana w ledgerze."))
        elif key == "recall":
            return [
                "Recall / benchmark",
                "",
                "R0  Source Fidelity (Test00)",
                "R1  Prywatny, wersjonowany benchmark Recall",
                "R2  FTS5/BM25 baseline — AKTYWNY ETAP",
                "R3  Query rewrite A/B — NIEIMPLEMENTOWANE",
                "R4  Dense retrieval / rerank A/B — NIEIMPLEMENTOWANE",
                "R5  Trening/wybór retrievera — ZABLOKOWANE do przewagi benchmarkowej",
                "",
                "Metryki: Recall@k, MRR, nDCG, abstention, provenance, temporal/update, false-memory i sensitive leakage.",
                "Prywatne query/wyniki pozostają w private report; sanitized report przechowuje wyłącznie dozwolone metryki i dowody.",
                "",
                "Baseline nigdy nie używa embeddingów ani modelu treningowego.",
            ]
        return lines

    def _settings_detail(self, key: str) -> list[str]:
        if key == "project-settings":
            return [
                "Ustawienia projektu",
                "",
                "Enter otwiera pełny edytor bieżącego projektu.",
                "",
                *_project_setting_lines(self.project_snapshot),
            ]
        if key == "retrieval":
            return [
                "FTS / retrieval / embeddings",
                "",
                "Enter otwiera edytor; zmiany są walidowane i zapisywane atomowo.",
                "",
                *_runtime_lines(self.runtime_settings),
                "",
                *_recall_status_lines(),
            ]
        if key == "safety":
            return [
                "Granice bezpieczeństwa",
                "",
                "require_fts5: TAK  [READ-ONLY]",
                "require_provenance: TAK  [READ-ONLY]",
                "automatic_experience_approval: NIE  [READ-ONLY / ZABLOKOWANE]",
                "automatic_l2: NIE  [READ-ONLY / ZABLOKOWANE]",
                "automatic_l3: NIE  [READ-ONLY / ZABLOKOWANE]",
                "automatic_activation: NIE  [READ-ONLY / ZABLOKOWANE]",
            ]
        if key == "paths":
            workspace = os.environ.get("JAZN_RUNTIME_WORKSPACE_DIR", "").strip()
            return [
                "Ścieżki i środowisko",
                "",
                f"Project root: {_value(self.project_root)}",
                f"Project: {_value(self.project)}",
                f"Database: {self.database}",
                f"Settings JSON: {self.settings_file}",
                f"Tool root: {self.tool_root}",
                f"JAZN_RUNTIME_WORKSPACE_DIR: {_value(workspace)}",
            ]
        if key == "theme":
            theme = get_theme(self.theme_name)
            return [
                "Wygląd / theme",
                "",
                "Enter wybiera theme; T przełącza i zapisuje wybór.",
                "Ten sam theme jest używany przez shell i wszystkie dialogi.",
                "",
                f"Theme: {theme.name}  [EDYTOWALNE]",
                f"Tło: {theme.background}",
                f"Panel: {theme.panel}",
                f"Obramowanie: {theme.border}",
                f"Akcent: {theme.accent}",
            ]
        return [
            "Wszystkie ustawienia",
            "",
            f"Plik narzędzia: {self.settings_file}",
            "",
            "[narzędzie / retrieval]",
            *_runtime_lines(self.runtime_settings),
            "",
            *_recall_status_lines(),
            "",
            "[studio]",
            f"theme_name: {self.theme_name}  [EDYTOWALNE]",
            "",
            "[projekt]",
            *_project_setting_lines(self.project_snapshot),
            "",
            "[informacje]",
            f"database: {self.database}",
            f"project: {_value(self.project)}",
            f"tool_root: {self.tool_root}",
        ]

    def content_fragments(self):
        key = self.current_item().key
        if self.active_page == "tests":
            lines = self._test_detail(key)
        elif self.active_page == "design":
            lines = self._design_detail(key)
        else:
            lines = self._settings_detail(key)
        fragments: list[tuple[str, str]] = []
        for index, line in enumerate(lines):
            if index == 0:
                style = "class:section"
            elif "ZABLOKOWANE" in line:
                style = "class:warning"
            elif line.startswith("  ✓"):
                style = "class:success"
            elif line.startswith("[") and line.endswith("]"):
                style = "class:accent"
            else:
                style = "class:content"
            fragments.append((style, f" {line}\n"))
        return fragments

    def status_fragments(self):
        style = "class:status-error" if self.status_kind == "error" else "class:status-ok"
        return [(style, f" {self.status}")]

    def footer_fragments(self):
        return [
            ("class:footer-key", " 1 "), ("class:footer", "Testy  "),
            ("class:footer-key", " 2 "), ("class:footer", "Projektowanie  "),
            ("class:footer-key", " 3 "), ("class:footer", "Ustawienia  "),
            ("class:footer-key", " ↑↓ "), ("class:footer", "Wybór  "),
            ("class:footer-key", " Enter "), ("class:footer", "Otwórz  "),
            ("class:footer-key", " R "), ("class:footer", "Test  "),
            ("class:footer-key", " S "), ("class:footer", "Zapisz settings  "),
            ("class:footer-key", " T "), ("class:footer", "Theme  "),
            ("class:footer-key", " Q "), ("class:footer", "Wyjście"),
        ]

    def edit_project_settings(self) -> None:
        if self.dialogs is None:
            raise RuntimeError("studio_dialog_backend_not_bound")
        _edit_project_settings(self, self.dialogs)


def _action_for_state(state: StudioState) -> StudioAction:
    item = state.current_item().key
    if state.active_page == "tests":
        return StudioAction("run-test", item)
    if state.active_page == "design":
        return StudioAction(item)
    return StudioAction(
        {
            "all": "settings-hub",
            "project-settings": "settings-project",
            "retrieval": "settings-runtime",
            "safety": "settings-safety",
            "paths": "settings-paths",
            "theme": "settings-theme",
        }[item]
    )


def _run_shell(state: StudioState) -> StudioAction:
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings

    bindings = KeyBindings()

    def invalidate(event) -> None:
        event.app.invalidate()

    @bindings.add("1")
    def _tests(event) -> None:
        state.set_page("tests")
        invalidate(event)

    @bindings.add("2")
    def _design(event) -> None:
        state.set_page("design")
        invalidate(event)

    @bindings.add("3")
    def _settings(event) -> None:
        state.set_page("settings")
        invalidate(event)

    @bindings.add("left")
    @bindings.add("s-tab")
    def _previous_page(event) -> None:
        state.cycle_page(-1)
        invalidate(event)

    @bindings.add("right")
    @bindings.add("tab")
    def _next_page(event) -> None:
        state.cycle_page(1)
        invalidate(event)

    @bindings.add("up")
    def _up(event) -> None:
        state.move_selection(-1)
        invalidate(event)

    @bindings.add("down")
    def _down(event) -> None:
        state.move_selection(1)
        invalidate(event)

    @bindings.add("t")
    def _theme(event) -> None:
        try:
            state.cycle_theme_persistent()
            state.status = f"Theme zapisany: {state.theme_name}"
            state.status_kind = "ok"
            event.app.style = prompt_toolkit_style(get_theme(state.theme_name))
        except Exception as exc:
            state.status = f"{type(exc).__name__}: {exc}"
            state.status_kind = "error"
        invalidate(event)

    @bindings.add("s")
    def _save(event) -> None:
        try:
            path = state.save_tool_settings()
            state.status = f"Zapisano ustawienia: {path}"
            state.status_kind = "ok"
        except Exception as exc:
            state.status = f"{type(exc).__name__}: {exc}"
            state.status_kind = "error"
        invalidate(event)

    @bindings.add("r")
    def _run_test(event) -> None:
        if state.active_page == "tests":
            event.app.exit(result=StudioAction("run-test", state.current_item().key))
        else:
            state.status = "R uruchamia profil tylko na stronie TESTY."
            state.status_kind = "error"
            invalidate(event)

    @bindings.add("enter")
    def _activate(event) -> None:
        event.app.exit(result=_action_for_state(state))

    @bindings.add("q")
    @bindings.add("c-c")
    def _quit(event) -> None:
        event.app.exit(result=StudioAction("quit"))

    application = Application(
        layout=build_studio_layout(state),
        key_bindings=bindings,
        style=prompt_toolkit_style(get_theme(state.theme_name)),
        full_screen=True,
        mouse_support=False,
    )
    result = application.run()
    return result if isinstance(result, StudioAction) else StudioAction("quit")


def _project_sources(state: StudioState) -> list[Path]:
    if not state.project:
        raise ValueError("Protokół wymaga projektu z jawną listą źródeł.")
    project = ProjectStore(state.project_root).load(state.project)
    sources = [Path(item.path).expanduser().resolve() for item in project.enabled_sources()]
    if not sources:
        raise ValueError("Projekt nie ma włączonych źródeł dla Test00.")
    return sources


def _run_test(state: StudioState, dialogs: DialogBackend, profile: str) -> None:
    if profile not in TEST_PROTOCOL_ORDER:
        raise ValueError(profile)
    project = ProjectStore(state.project_root).load(state.project) if state.project else None
    settings = dict(project.settings) if project else {}
    sources = _project_sources(state) if profile in {"test00", "test01", "test03"} else []
    if profile == "test00":
        state.test_results.clear()
        state.protocol_service = MemoryRebuildApplicationService(
            state.tool_root / "memory" / "rebuild_tests" / "protocols",
            tool_root=state.tool_root,
            settings=state.runtime_settings,
        )
    elif state.protocol_service is None:
        raise ValueError(f"{profile.upper()} wymaga rozpoczęcia runu od Test00 w tej sesji Studio.")
    service = state.protocol_service
    assert service is not None
    state.test_results[profile] = {"outcome": "RUNNING", "ok": False}
    state.status = f"{profile.upper()}: RUNNING"
    state.status_kind = "ok"

    if profile == "test00":
        kwargs: dict[str, Any] = {"sources": sources}
    elif profile == "test01":
        prerequisite = state.test_results.get("test00")
        if not prerequisite or not prerequisite.get("downstream_ready", prerequisite.get("ok")):
            raise ValueError("Test01 wymaga zaliczonego Test00 w tej sesji Studio.")
        kwargs = {"sources": sources, "database": state.database, "test00_result": prerequisite}
    elif profile == "test02":
        prerequisite = state.test_results.get("test01")
        if not prerequisite or not prerequisite.get("ok"):
            raise ValueError("Test02 wymaga zaliczonego Test01 w tej sesji Studio.")
        kwargs = {"database": state.database, "test01_result": prerequisite}
    elif profile == "test03":
        prerequisite = state.test_results.get("test02")
        if not prerequisite or not prerequisite.get("ok"):
            raise ValueError("Test03 wymaga zaliczonego Test02 w tej sesji Studio.")
        kwargs = {"sources": sources, "test02_result": prerequisite}
    elif profile == "test04":
        prerequisite = state.test_results.get("test03")
        if not prerequisite or not prerequisite.get("ok"):
            raise ValueError("Test04 wymaga zaliczonego Test03 w tej sesji Studio.")
        benchmark = settings.get("test04_benchmark")
        if not benchmark:
            raise ValueError("Test04 wymaga prywatnego ustawienia projektu test04_benchmark.")
        kwargs = {
            "database": state.database,
            "benchmark": benchmark,
            "test03_result": prerequisite,
            "system_acceptance": bool(settings.get("system_acceptance", False)),
            "restart_continuity_report": settings.get("restart_continuity_report"),
        }
    else:
        prerequisite = state.test_results.get("test04")
        if not prerequisite or not prerequisite.get("ok"):
            raise ValueError("Final wymaga zaliczonego Test04 w tej sesji Studio.")
        final_output = settings.get("final_output") or str(state.database.parent / "final-memory")
        kwargs = {
            "database": state.database,
            "output": final_output,
            "test04_result": prerequisite,
            "sources": [Path(item.path) for item in project.enabled_sources()] if project else [],
        }
    report = service.run_protocol(profile, **kwargs)
    state.test_results[profile] = dict(report)
    state.status = f"{profile.upper()}: {report['outcome']}"
    state.status_kind = "ok" if report.get("ok") else "error"
    dialogs.message(
        "WYNIK PROTOKOŁU PAMIĘCI",
        json.dumps(report, ensure_ascii=False, indent=2, default=str)[:12000],
    )


def _edit_runtime_settings(state: StudioState, dialogs: DialogBackend) -> None:
    while True:
        current = state.tool_settings.runtime
        action = dialogs.choice(
            "USTAWIENIA NARZĘDZIA — RETRIEVAL",
            "\n".join(_runtime_lines(current)),
            [
                ("limit", f"retrieval_limit — {current.retrieval_limit}"),
                ("score", f"min_lexical_score — {current.min_lexical_score}"),
                ("embeddings", f"embeddings_enabled — {_yes_no(current.embeddings_enabled)}"),
                ("model", f"embedding_model — {_value(current.embedding_model)}"),
                ("reset", "Przywróć bezpieczne ustawienia"),
                ("json", "Pokaż pełny memory_rebuild_settings.json"),
                ("back", "Wróć"),
            ],
            default="limit",
        )
        if action in {None, "back"}:
            return
        try:
            if action == "limit":
                raw = dialogs.input("RETRIEVAL LIMIT", "Zakres 1..500:", str(current.retrieval_limit))
                if raw is not None:
                    state.set_runtime(current.with_overrides(retrieval_limit=int(raw.strip())))
            elif action == "score":
                raw = dialogs.input("MIN LEXICAL SCORE", "Zakres 0..1:", str(current.min_lexical_score))
                if raw is not None:
                    state.set_runtime(
                        current.with_overrides(
                            min_lexical_score=float(raw.strip().replace(",", "."))
                        )
                    )
            elif action == "embeddings":
                enable = not current.embeddings_enabled
                model = current.embedding_model
                if enable and not (model or "").strip():
                    model = dialogs.input(
                        "MODEL EMBEDDINGÓW",
                        "Włączenie embeddingów wymaga jawnego modelu:",
                        "",
                    )
                    if not model or not model.strip():
                        continue
                state.set_runtime(
                    current.with_overrides(
                        embeddings_enabled=enable,
                        embedding_model=model.strip() if isinstance(model, str) and model.strip() else None,
                    )
                )
            elif action == "model":
                raw = dialogs.input(
                    "MODEL EMBEDDINGÓW",
                    "Identyfikator modelu; pusty tylko gdy embeddingi są wyłączone:",
                    current.embedding_model or "",
                )
                if raw is not None:
                    state.set_runtime(current.with_overrides(embedding_model=raw.strip() or None))
            elif action == "reset":
                if dialogs.confirm("PRZYWRÓĆ USTAWIENIA", "Przywrócić bezpieczne ustawienia domyślne?"):
                    state.set_runtime(MemoryRebuildSettings())
            elif action == "json":
                dialogs.message(
                    "memory_rebuild_settings.json",
                    json.dumps(state.tool_settings.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
                )
        except (OSError, TypeError, ValueError) as exc:
            dialogs.message("NIEPRAWIDŁOWE USTAWIENIE", str(exc))


def _confirm_risk(dialogs: DialogBackend, key: str, new_value: bool) -> bool:
    less_safe = (key in PROJECT_RISKY_TRUE and new_value) or (
        key in PROJECT_RISKY_FALSE and not new_value
    )
    if not less_safe:
        return True
    return dialogs.confirm(
        "POTWIERDŹ MNIEJ BEZPIECZNE USTAWIENIE",
        f"{key} = {_yes_no(new_value)} zmniejsza ochronę lub zwiększa zakres zapisu. Kontynuować?",
    )


def _edit_project_settings(state: StudioState, dialogs: DialogBackend) -> None:
    if not state.project:
        dialogs.message("USTAWIENIA PROJEKTU", "Najpierw wybierz lub utwórz projekt.")
        return
    store = ProjectStore(state.project_root)
    project = store.load(state.project)
    state.project = project.project_id
    while True:
        project.normalized()
        rows: list[tuple[str, str]] = [
            ("name", f"Nazwa projektu: {project.name}"),
            ("mode", f"Tryb: {project.mode}"),
            ("target_root", f"Katalog docelowy: {project.target_root}"),
            ("source_directory", f"Główny folder źródeł: {project.source_directory or '—'}"),
            ("test04_acceptance_report", f"Raport Test04: {project.settings.get('test04_acceptance_report') or '—'}"),
            ("system_acceptance", f"System acceptance: {_yes_no(project.settings.get('system_acceptance', False))}"),
        ]
        for key, default in DEFAULT_SETTINGS.items():
            value = project.settings.get(key, default)
            label = PROJECT_SETTING_LABELS.get(key, key)
            suffix = "  [READ-ONLY]" if key in PROJECT_LOCKED_SETTINGS else ""
            rows.append((f"locked:{key}" if key in PROJECT_LOCKED_SETTINGS else f"setting:{key}", f"{label}: {_value(value)}{suffix}"))
        rows.extend(
            [
                ("safe", "Przywróć bezpieczne ustawienia projektu"),
                ("json", "Pokaż pełny JSON ustawień projektu"),
                ("back", "Wróć"),
            ]
        )
        action = dialogs.choice(
            "PEŁNE USTAWIENIA PROJEKTU",
            "Zmiany są zapisywane od razu. Pola READ-ONLY są wymuszone przez bezpieczeństwo.",
            rows,
            default="name",
        )
        if action in {None, "back"}:
            state.refresh()
            return
        if action == "name":
            raw = dialogs.input("NAZWA PROJEKTU", "Nazwa:", project.name)
            if raw and raw.strip():
                project.name = raw.strip()
        elif action == "mode":
            value = dialogs.choice(
                "TRYB PROJEKTU",
                "Developer służy do odbudów testowych; system do finalnych operacji.",
                [("developer", "developer"), ("system", "system")],
                default=project.mode,
            )
            if value:
                project.mode = str(value)
        elif action in {"target_root", "source_directory"}:
            current = project.target_root if action == "target_root" else project.source_directory
            raw = dialogs.input("ŚCIEŻKA", "Pełna ścieżka:", current or "")
            if raw is None:
                continue
            value = raw.strip()
            if action == "target_root" and not value:
                dialogs.message("NIEPRAWIDŁOWA WARTOŚĆ", "Katalog docelowy nie może być pusty.")
                continue
            resolved = str(Path(value).expanduser().resolve()) if value else ""
            if action == "target_root":
                project.target_root = resolved
            else:
                project.source_directory = resolved
        elif action == "test04_acceptance_report":
            raw = dialogs.input(
                "RAPORT TEST04",
                "Ścieżka prywatnego raportu; puste = nie ustawiono:",
                str(project.settings.get("test04_acceptance_report") or ""),
            )
            if raw is not None:
                if raw.strip():
                    project.settings["test04_acceptance_report"] = str(Path(raw).expanduser().resolve())
                else:
                    project.settings.pop("test04_acceptance_report", None)
        elif action == "system_acceptance":
            new_value = not bool(project.settings.get("system_acceptance", False))
            if not _confirm_risk(dialogs, "system_acceptance", new_value):
                continue
            project.settings["system_acceptance"] = new_value
        elif isinstance(action, str) and action.startswith("locked:"):
            key = action.split(":", 1)[1]
            dialogs.message("TYLKO DO ODCZYTU", f"{key} pozostaje wymuszone na NIE.")
            continue
        elif isinstance(action, str) and action.startswith("setting:"):
            key = action.split(":", 1)[1]
            current = project.settings.get(key, DEFAULT_SETTINGS[key])
            if isinstance(DEFAULT_SETTINGS[key], bool):
                new_value = not bool(current)
                if not _confirm_risk(dialogs, key, new_value):
                    continue
                project.settings[key] = new_value
            elif key in {"candidate_limit", "progress_every_conversations"}:
                raw = dialogs.input("WARTOŚĆ", f"{key}:", str(current))
                if raw is None:
                    continue
                value = int(raw.strip())
                if key == "candidate_limit" and value < 0:
                    raise ValueError("candidate_limit musi być >= 0")
                if key == "progress_every_conversations" and not 1 <= value <= 100000:
                    raise ValueError("progress_every_conversations: zakres 1..100000")
                project.settings[key] = value
        elif action == "safe":
            if dialogs.confirm("PRZYWRÓĆ USTAWIENIA", "Przywrócić standardowe ustawienia projektu?"):
                extras = {key: value for key, value in project.settings.items() if key not in DEFAULT_SETTINGS}
                project.settings = dict(DEFAULT_SETTINGS)
                project.settings.update(extras)
        elif action == "json":
            dialogs.message(
                "USTAWIENIA PROJEKTU JSON",
                json.dumps(project.settings, ensure_ascii=False, indent=2, sort_keys=True, default=str),
            )
            continue
        project.normalized()
        store.save(project)
        state.project = project.project_id
        state.refresh()


def _settings_hub(state: StudioState, dialogs: DialogBackend) -> None:
    while True:
        action = dialogs.choice(
            "CENTRUM USTAWIEŃ MEMORY REBUILD",
            f"Plik narzędzia:\n{state.settings_file}",
            [
                ("runtime", "Retrieval / embeddingi"),
                ("project", "Pełne ustawienia projektu"),
                ("theme", "Wygląd / theme"),
                ("safety", "Granice bezpieczeństwa — tylko odczyt"),
                ("paths", "Ścieżki i środowisko"),
                ("json", "Pokaż pełny memory_rebuild_settings.json"),
                ("save", "Zapisz pełny plik ustawień ponownie"),
                ("back", "Wróć"),
            ],
            default="runtime",
        )
        if action in {None, "back"}:
            return
        if action == "runtime":
            _edit_runtime_settings(state, dialogs)
        elif action == "project":
            _edit_project_settings(state, dialogs)
        elif action == "theme":
            selected = dialogs.choice(
                "THEME MEMORY REBUILD STUDIO",
                "Theme obejmuje shell i wszystkie dialogi.",
                [(name, name) for name in THEMES],
                default=state.theme_name,
            )
            if selected:
                state.set_theme(str(selected))
        elif action == "safety":
            dialogs.message("GRANICE BEZPIECZEŃSTWA", "\n".join(state._settings_detail("safety")))
        elif action == "paths":
            dialogs.message("ŚCIEŻKI MEMORY REBUILD", "\n".join(state._settings_detail("paths")))
        elif action == "json":
            dialogs.message(
                "memory_rebuild_settings.json",
                json.dumps(state.tool_settings.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            )
        elif action == "save":
            dialogs.message("ZAPISANO", str(state.save_tool_settings()))


def _handle_action(
    state: StudioState,
    dialogs: DialogBackend,
    workflows: StudioWorkflows,
    action: StudioAction,
) -> int | None:
    if action.kind == "quit":
        return 0
    if action.kind == "run-test":
        _run_test(state, dialogs, str(action.value))
    elif action.kind == "project":
        workflows.project_hub()
    elif action.kind == "database":
        workflows.database_hub()
    elif action.kind == "import":
        workflows.import_hub()
    elif action.kind == "candidates":
        workflows.candidates_hub()
    elif action.kind == "plan":
        workflows.plan(compare=False)
    elif action.kind == "rebuild":
        workflows.rebuild()
    elif action.kind == "compare":
        workflows.plan(compare=True)
    elif action.kind == "export":
        workflows.export()
    elif action.kind == "recall":
        dialogs.message("RECALL / BENCHMARK", "\n".join(state._design_detail("recall")))
    elif action.kind == "settings-hub":
        _settings_hub(state, dialogs)
    elif action.kind == "settings-project":
        _edit_project_settings(state, dialogs)
    elif action.kind == "settings-runtime":
        _edit_runtime_settings(state, dialogs)
    elif action.kind == "settings-theme":
        selected = dialogs.choice(
            "THEME MEMORY REBUILD STUDIO",
            "Theme obejmuje shell i wszystkie dialogi.",
            [(name, name) for name in THEMES],
            default=state.theme_name,
        )
        if selected:
            state.set_theme(str(selected))
    elif action.kind == "settings-safety":
        dialogs.message("GRANICE BEZPIECZEŃSTWA", "\n".join(state._settings_detail("safety")))
    elif action.kind == "settings-paths":
        dialogs.message("ŚCIEŻKI MEMORY REBUILD", "\n".join(state._settings_detail("paths")))
    else:
        raise ValueError(f"Nieobsługiwana akcja Studio: {action.kind}")
    state.refresh()
    state.status = f"Gotowe — {action.kind}"
    state.status_kind = "ok"
    return None


def _run_text_studio(
    state: StudioState,
    dialogs: DialogBackend,
    workflows: StudioWorkflows,
) -> int:
    pages = [
        ("tests", "TESTY"),
        ("design", "PROJEKTOWANIE"),
        ("settings", "USTAWIENIA"),
        ("quit", "Zakończ"),
    ]
    while True:
        page = dialogs.choice(
            f"JAŹŃ MEMORY REBUILD STUDIO — {STUDIO_VERSION}",
            f"Wersja pakietu: {PACKAGE_VERSION}\nBaza: {state.database}",
            pages,
            default="design",
        )
        if page in {None, "quit"}:
            return 0
        state.set_page(str(page))
        while True:
            values = [(item.key, item.label) for item in state.items()] + [("__back__", "Wróć")]
            selected = dialogs.choice(
                PAGE_LABELS[state.active_page],
                "",
                values,
                default=state.items()[0].key,
            )
            if selected in {None, "__back__"}:
                break
            for index, item in enumerate(state.items()):
                if item.key == selected:
                    state.selected[state.active_page] = index
                    break
            result = _handle_action(state, dialogs, workflows, _action_for_state(state))
            if result is not None:
                return result


def run_studio(
    *,
    database: str | Path,
    project_root: str | Path | None = None,
    project: str | None = None,
    tool_root: str | Path | None = None,
    settings_path: str | Path | None = None,
    text_ui: bool = False,
) -> int:
    state = StudioState(
        database=Path(database),
        project_root=project_root,
        project=project,
        tool_root=Path(tool_root or Path.cwd()),
        settings_path=settings_path,
    )
    dialogs = make_dialogs(theme_name=lambda: state.theme_name, text_ui=text_ui)
    state.bind_dialogs(dialogs)
    workflows = StudioWorkflows(state, dialogs)

    if text_ui or isinstance(dialogs, TextDialogs):
        return _run_text_studio(state, dialogs, workflows)

    while True:
        action = _run_shell(state)
        try:
            result = _handle_action(state, dialogs, workflows, action)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            state.status = f"{type(exc).__name__}: {exc}"
            state.status_kind = "error"
            dialogs.message("MEMORY REBUILD STUDIO", state.status)
            state.refresh()
            continue
        if result is not None:
            return result


def edit_tool_settings_text(path: Path, *, tool_root: Path) -> None:
    state = StudioState(
        database=(tool_root / "memory_jazn.sqlite3"),
        project_root=None,
        project=None,
        tool_root=tool_root,
        settings_path=path,
    )
    dialogs = TextDialogs()
    state.bind_dialogs(dialogs)
    _settings_hub(state, dialogs)


__all__ = [
    "DESIGN_ITEMS",
    "PAGE_IDS",
    "PAGE_LABELS",
    "PROJECT_LOCKED_SETTINGS",
    "PROJECT_RISKY_FALSE",
    "PROJECT_RISKY_TRUE",
    "SETTINGS_ITEMS",
    "STUDIO_VERSION",
    "StudioAction",
    "StudioState",
    "edit_tool_settings_text",
    "run_studio",
]
