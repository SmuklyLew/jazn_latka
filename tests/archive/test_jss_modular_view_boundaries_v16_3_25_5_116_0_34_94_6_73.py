"""JSS architectural guard: modular views without importing or starting runtime."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "tools" / "jazn_run_studio"
OWNERS = {
    "view_dashboard.py": [
        "_dashboard",
        "check_local_readiness",
        "refresh_quick_start",
        "render_discovery"
    ],
    "view_services.py": [
        "_services",
        "selected_service",
        "inspect_service",
        "selected_service_action",
        "refresh_service_controls",
        "refresh_services",
        "service",
        "update_service_summary",
        "refresh_service_table",
        "open_service_status"
    ],
    "view_chat.py": [
        "_chat",
        "select_local_model",
        "connect_local_chat",
        "send_chat",
        "resume_chat"
    ],
    "view_studios.py": [
        "_diagnostics",
        "_studios",
        "_configuration",
        "_version_studio",
        "_tests_catalog",
        "_local_acceptance",
        "open_tpa_dependencies",
        "_memory",
        "reset_studio_operations",
        "load_studio_operations",
        "render_operation",
        "invalidate_operation_preview",
        "operation_payload",
        "preview_operation",
        "execute_operation"
    ],
    "view_settings.py": [
        "_settings",
        "settings_model_selected",
        "set_settings_installed_models",
        "fill_discovered_defaults",
        "choose_custom_color",
        "save_profile",
        "save",
        "apply_settings",
        "select_style",
        "style_selected",
        "apply_theme",
        "settings_draft",
        "settings_changed",
        "reset_settings_draft",
        "filter_settings"
    ],
    "view_navigation.py": [
        "_about",
        "update_current_section",
        "toggle_sidebar",
        "set_logs_visible",
        "toggle_logs",
        "show_log",
        "log_view",
        "navigate",
        "filter_navigation",
        "select_search_result",
        "_workspace_menu",
        "switch_sidebar",
        "reset_layout",
        "restore_layout",
        "persist_layout",
        "setup_completed",
        "open_setup",
        "_models",
        "_connections",
        "refresh_connection_checks",
        "_developer",
        "export"
    ],
    "view_events.py": [
        "poll"
    ]
}


def _methods(path: Path, cls: str) -> set[str]:
    source = ast.parse(path.read_text(encoding="utf-8"))
    owner = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == cls)
    return {node.name for node in owner.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_each_functional_view_owns_exactly_one_method_implementation() -> None:
    remaining = _methods(ROOT / "window.py", "Window")
    assert remaining == {"__init__", "page", "button", "guard", "action", "closeEvent"}
    seen = set(remaining)
    for file, expected in OWNERS.items():
        owners = {"view_dashboard.py": "DashboardViewMixin", "view_services.py": "ServiceViewMixin",
                  "view_chat.py": "ChatViewMixin", "view_studios.py": "StudioViewMixin",
                  "view_settings.py": "SettingsViewMixin", "view_navigation.py": "NavigationViewMixin",
                  "view_events.py": "EventViewMixin"}
        class_name = owners[file]
        actual = _methods(ROOT / file, class_name)
        assert actual == set(expected), (file, actual ^ set(expected))
        assert not (seen & actual), (file, seen & actual)
        seen.update(actual)


def test_studio_module_imports_preserve_canonical_controller_boundary() -> None:
    text = (ROOT / "window.py").read_text(encoding="utf-8")
    assert "QMainWindow" in text
    for file in OWNERS:
        assert "from ." + file[:-3] + " import " in text
    assert "self.core.close()" in text
    assert "def run_window(" in text
