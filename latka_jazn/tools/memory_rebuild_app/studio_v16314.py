from __future__ import annotations

"""v16.3.14 Memory Rebuild Studio extension.

This module composes the existing P0 shell instead of duplicating its layout,
theme, project editor or import engine.  It adds Test00 protocol execution,
shared TestSpec presentation and an explicit Recall benchmark project surface.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
import json

from .models import DEFAULT_SETTINGS
from .project_store import ProjectStore
from .source_fidelity import default_test00_root, run_test00_source_fidelity
from .test_profiles import PROFILE_NAMES, run_test_profile
from .test_spec import TEST_SPECS, get_test_spec
from .studio_p0 import (
    DESIGN_ITEMS,
    SETTINGS_ITEMS,
    PageItem,
    StudioAction,
    StudioState,
    _format_test_report,
    _handle_action,
    _run_shell,
)
from .tui_common import message


STUDIO_VERSION = "memory-rebuild-studio/v16.3.14"
RECALL_DESIGN_ITEM = PageItem(
    "recall",
    "Recall / benchmark",
    "Mierzalny subsystem: benchmark → FTS5 baseline → eksperymenty A/B; trening modeli pozostaje wyłączony.",
)


@dataclass(slots=True)
class StudioV16314State(StudioState):
    test_results: dict[str, dict[str, Any]] = field(default_factory=dict)

    def items(self) -> Sequence[PageItem]:
        if self.active_page == "tests":
            return tuple(PageItem(item.profile, item.label, item.goal) for item in TEST_SPECS)
        if self.active_page == "design":
            return (*DESIGN_ITEMS, RECALL_DESIGN_ITEM)
        return SETTINGS_ITEMS

    def header_fragments(self):
        fragments = list(super().header_fragments())
        if len(fragments) > 1:
            fragments[1] = ("class:header-version", f"{STUDIO_VERSION}   ")
        return fragments

    def _test_detail(self, profile: str) -> list[str]:
        spec = get_test_spec(profile)
        result = self.test_results.get(profile)
        outcome = str(result.get("outcome") or ("PASSED" if result.get("ok") else "FAILED")) if result else "NOT RUN"
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
            for key in ("run_id", "database_sha256", "baseline_id", "sanitized_report"):
                if result.get(key) is not None:
                    lines.append(f"  {key}: {result.get(key)}")
            if result.get("quality_gate_passed") is not None:
                lines.append(f"  quality_gate_passed: {result.get('quality_gate_passed')}")
        else:
            lines.append("  brak — protokół nie był uruchamiany w tej sesji")
        lines.extend(("", "WYJŚCIA"))
        lines.extend(f"  • {value}" for value in spec.outputs)
        lines.extend(("", "GRANICA PRAWDY"))
        lines.extend(f"  • {value}" for value in spec.truth_boundary)
        if profile == "test00":
            lines.extend(("", "R/Enter uruchamia Test00 i zapisuje wyłącznie pod memory/rebuild_tests/test_00/."))
        else:
            lines.extend(("", "R/Enter wykonuje istniejący read-only validator etapu; pełne runnery 01-04 pozostają kolejną fazą implementacji."))
        return lines

    def _design_detail(self, key: str) -> list[str]:
        if key != "recall":
            return super()._design_detail(key)
        return [
            "Recall / benchmark",
            "",
            "Cel: mierzyć pamięć zanim zaczniemy trenować lub wybierać retriever.",
            "",
            "R0  Source Fidelity (Test00)",
            "R1  Prywatny, wersjonowany benchmark Recall",
            "R2  FTS5/BM25 baseline — AKTYWNY ETAP",
            "R3  Query rewrite A/B — NIEIMPLEMENTOWANE",
            "R4  Dense retrieval / rerank A/B — NIEIMPLEMENTOWANE",
            "R5  Trening/wybór retrievera — ZABLOKOWANE do czasu przewagi benchmarkowej",
            "",
            "Metryki: Recall@k, MRR, nDCG, abstention, provenance, temporal/update, false-memory i sensitive leakage.",
            "Prywatne query/wyniki pozostają wyłącznie w private report; sanitized report przechowuje hashe i metryki.",
            "",
            "Baseline nigdy nie używa embeddingów ani modelu treningowego.",
        ]

    def _settings_detail(self, key: str) -> list[str]:
        lines = list(super()._settings_detail(key))
        if key in {"retrieval", "all"}:
            lines.extend(
                (
                    "",
                    "[Recall benchmark]",
                    "baseline: fts5-bm25/v1",
                    "query_rewrite: NIEIMPLEMENTOWANE",
                    "dense_retrieval: NIEIMPLEMENTOWANE",
                    "reranker: NIEIMPLEMENTOWANE",
                    "model_training: NIE [ZABLOKOWANE do czasu A/B]",
                )
            )
        return lines


def _project_sources(state: StudioV16314State) -> list[Path]:
    if not state.project:
        raise ValueError("Test00 wymaga projektu z jawną listą źródeł.")
    project = ProjectStore(state.project_root).load(state.project)
    sources = [Path(item.path).expanduser().resolve() for item in project.enabled_sources()]
    if not sources:
        raise ValueError("Projekt nie ma włączonych źródeł dla Test00.")
    return sources


def _format_test00_report(report: dict[str, Any]) -> str:
    lines = [
        "Profil: test00",
        f"Wynik: {report.get('outcome')}",
        f"Run ID: {report.get('run_id')}",
        f"Source mirror: {report.get('database')}",
        f"SHA-256 bazy: {report.get('database_sha256')}",
        f"Źródła: {report.get('source_count')}",
        "",
    ]
    for item in report.get("results") or []:
        lines.append(
            f"{item.get('outcome')} | {item.get('source_name')} | {item.get('parse_mode')} | "
            f"conv={item.get('conversation_count')} nodes={item.get('node_count')} messages={item.get('message_count')}"
        )
        roles = item.get("role_counts") or {}
        if roles:
            lines.append("  role: " + ", ".join(f"{key}={value}" for key, value in sorted(roles.items())))
        if item.get("warnings"):
            lines.append(f"  warnings={len(item.get('warnings') or [])}")
        if item.get("errors"):
            lines.append(f"  errors={len(item.get('errors') or [])}")
    lines.extend(("", "Granica prawdy: Test00 dowodzi wierności źródła, nie aktywnej pamięci ani Recall."))
    return "\n".join(lines)


def _run_test_action_v16314(state: StudioV16314State, profile: str) -> None:
    if profile == "test00":
        sources = _project_sources(state)
        report = run_test00_source_fidelity(
            sources,
            output_root=default_test00_root(state.tool_root),
        )
        state.test_results[profile] = dict(report)
        state.status = f"TEST00: {report.get('outcome')}"
        state.status_kind = "ok" if report.get("outcome") == "PASSED" else "error"
        message("Wynik Test00 Source Fidelity", _format_test00_report(report))
        return
    if profile not in PROFILE_NAMES:
        raise ValueError(profile)
    project = ProjectStore(state.project_root).load(state.project) if state.project else None
    baselines = [item.path for item in project.enabled_baselines()] if project else []
    settings = dict(project.settings) if project else {}
    report = run_test_profile(
        state.database,
        profile,
        baselines=baselines,
        full_validation=True,
        acceptance_report=settings.get("test04_acceptance_report"),
        system_acceptance=bool(settings.get("system_acceptance", False)),
    )
    normalized = dict(report)
    normalized["outcome"] = "PASSED" if report.get("ok") else "FAILED"
    state.test_results[profile] = normalized
    state.status = f"{profile.upper()}: {normalized['outcome']}"
    state.status_kind = "ok" if report.get("ok") else "error"
    message("Wynik testu pamięci", _format_test_report(report))


def _handle_action_v16314(state: StudioV16314State, action: StudioAction) -> int | None:
    if action.kind == "run-test":
        _run_test_action_v16314(state, str(action.value))
        state.refresh()
        return None
    if action.kind == "recall":
        body = "\n".join(state._design_detail("recall"))
        message("Recall / benchmark", body)
        state.status = "Recall: FTS5 baseline gotowy; trening pozostaje zablokowany."
        state.status_kind = "ok"
        return None
    return _handle_action(state, action)


def run_studio_v16314(
    *,
    database: str | Path,
    project_root: str | Path | None = None,
    project: str | None = None,
    tool_root: str | Path | None = None,
    settings_path: str | Path | None = None,
) -> int:
    state = StudioV16314State(
        database=Path(database),
        project_root=project_root,
        project=project,
        tool_root=Path(tool_root or Path.cwd()),
        settings_path=settings_path,
    )
    while True:
        action = _run_shell(state)
        try:
            result = _handle_action_v16314(state, action)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            state.status = f"{type(exc).__name__}: {exc}"
            state.status_kind = "error"
            message("Memory Rebuild Studio", state.status)
            state.refresh()
            continue
        if result is not None:
            return result


__all__ = ["STUDIO_VERSION", "StudioV16314State", "run_studio_v16314"]
