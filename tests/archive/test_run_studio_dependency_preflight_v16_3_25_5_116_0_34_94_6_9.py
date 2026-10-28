"""Early dependency audit tests; no network, pip or GUI installation."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio import dependency_preflight as preflight


def test_inspection_uses_canonical_profiles_without_requiring_optional(monkeypatch, tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    monkeypatch.setattr(preflight, "_profiles", lambda root: ["core", "run-studio", "polish-nlp"])
    class Common:
        def resolve_profile_requirements(self, root, names):
            return {"core": ["packaging>=24"], "run-studio": ["PySide6-Essentials>=6"], "polish-nlp": ["spacy>=3"]}[names[0]]
        def inspect_current_requirements(self, root, reqs):
            missing = "spacy" in reqs[0]
            return [SimpleNamespace(
                distribution=reqs[0].split(">=")[0].lower(), requirement=reqs[0],
                installed_version=None if missing else "99",
                version_satisfies=not missing, import_available=not missing, ready=not missing, import_name="test",
            )]
    monkeypatch.setattr(preflight, "_common", lambda: Common())
    result = preflight.inspect(tmp_path)
    assert result["required_issues"] == []
    assert result["profiles"]["polish-nlp"][0]["state"] == "MISSING"


def test_missing_essential_is_reported(monkeypatch, tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    monkeypatch.setattr(preflight, "_profiles", lambda root: ["core", "run-studio"])
    class Common:
        def resolve_profile_requirements(self, root, names): return ["PySide6-Essentials>=6"]
        def inspect_current_requirements(self, root, reqs):
            return [SimpleNamespace(distribution="pyside6-essentials", requirement=reqs[0],
                                    installed_version=None, version_satisfies=False,
                                    import_available=False, ready=False, import_name="PySide6")]
    monkeypatch.setattr(preflight, "_common", lambda: Common())
    assert preflight.inspect(tmp_path)["required_issues"]


def test_no_venv_never_spawns_pip(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(preflight.sys, "prefix", "/base")
    monkeypatch.setattr(preflight.sys, "base_prefix", "/base")
    monkeypatch.setattr(preflight.subprocess, "run", lambda *_a, **_kw: pytest.fail("pip was run"))
    assert preflight._install(tmp_path, ["core"]) is False


def test_declined_install_never_spawns_pip(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(preflight.sys, "prefix", "/venv")
    monkeypatch.setattr(preflight.sys, "base_prefix", "/base")
    class Common:
        def resolve_profile_requirements(self, root, names): return ["packaging>=24"]
        def inspect_current_requirements(self, root, reqs):
            return [SimpleNamespace(requirement=reqs[0], ready=False)]
    monkeypatch.setattr(preflight, "_common", lambda: Common())
    monkeypatch.setattr("builtins.input", lambda _prompt: "NIE")
    monkeypatch.setattr(preflight.subprocess, "run", lambda *_a, **_kw: pytest.fail("pip was run"))
    assert preflight._install(tmp_path, ["core"]) is False


def test_allowed_install_uses_only_pypi_with_guardrails(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(preflight.sys, "prefix", "/venv")
    monkeypatch.setattr(preflight.sys, "base_prefix", "/base")
    class Common:
        def resolve_profile_requirements(self, root, names): return ["packaging>=24"]
        def inspect_current_requirements(self, root, reqs):
            return [SimpleNamespace(requirement=reqs[0], ready=False)]
    monkeypatch.setattr(preflight, "_common", lambda: Common())
    monkeypatch.setattr("builtins.input", lambda _prompt: "TAK")
    seen = {}
    def fake_run(args, **kw):
        seen.update(args=args, **kw)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    assert preflight._install(tmp_path, ["core"]) is True
    assert seen["args"][0] == preflight.sys.executable
    assert "--only-binary=:all:" in seen["args"]
    assert seen["args"][seen["args"].index("--index-url")+1] == preflight.INDEX
    assert seen["shell"] is False
    assert seen["env"]["PIP_CONFIG_FILE"] == preflight.os.devnull


def test_noninteractive_missing_environment_does_not_install(monkeypatch):
    monkeypatch.setattr(preflight, "_interactive", lambda: False)
    report = {"required_issues": [{"distribution": "pyside6-essentials"}]}
    assert preflight._menu(Path("."), report, explicit=False) is False


def test_user_can_confirm_lowercase_tak(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(preflight.sys, "prefix", "/venv")
    monkeypatch.setattr(preflight.sys, "base_prefix", "/base")
    class Common:
        def resolve_profile_requirements(self, root, names):
            return ["prompt-toolkit>=3"]
        def inspect_current_requirements(self, root, reqs):
            return [SimpleNamespace(requirement=reqs[0], ready=False)]
    monkeypatch.setattr(preflight, "_common", lambda: Common())
    monkeypatch.setattr("builtins.input", lambda _prompt: " tak ")
    calls = []
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    assert preflight._install(tmp_path, ["studio"]) is True
    assert len(calls) == 1


def test_compact_report_hides_optional_package_details(monkeypatch, capsys):
    report = {"interpreter": "python.exe", "required_issues": [],
              "profiles": {"core": [], "run-studio": [],
                           "polish-nlp": [{"state": "MISSING", "version": None,
                                           "requirement": "spacy>=3"}]}}
    monkeypatch.setattr(preflight, "_pip_check", lambda: ("PASS", ""))
    preflight.show(report, full=False)
    output = capsys.readouterr().out
    assert "NIE BLOKUJĄ GUI" in output
    assert "spacy>=3" not in output
    preflight.show(report, full=True)
    assert "spacy>=3" in capsys.readouterr().out


def test_optional_install_stays_in_menu(monkeypatch, capsys):
    report = {"interpreter": "python.exe", "required_issues": [],
              "profiles": {"core": [], "run-studio": [],
                           "studio": [{"state": "MISSING", "version": None,
                                       "requirement": "prompt-toolkit>=3"}]}}
    ready = {"interpreter": "python.exe", "required_issues": [],
             "profiles": {"core": [], "run-studio": [],
                          "studio": [{"state": "PASS", "version": "3.1",
                                      "requirement": "prompt-toolkit>=3"}]}}
    choices = iter(["2", "1", "0"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(choices))
    monkeypatch.setattr(preflight, "_interactive", lambda: True)
    monkeypatch.setattr(preflight, "_install", lambda root, names: names == ["studio"])
    monkeypatch.setattr(preflight, "inspect", lambda root: ready)
    monkeypatch.setattr(preflight, "_pip_check", lambda: ("PASS", ""))
    assert preflight._menu(Path("."), report, explicit=True) is True
    assert "[GOTOWE] Zainstalowany profil: studio" in capsys.readouterr().out


def test_auto_tui_selection_and_forced_text(monkeypatch):
    monkeypatch.setattr(preflight, "_tui_available", lambda: True)
    assert preflight._ui_mode() == "tui"
    assert preflight._ui_mode("text") == "text"
    monkeypatch.setattr(preflight, "_tui_available", lambda: False)
    assert preflight._ui_mode() == "text"
    assert preflight._ui_mode("tui") == "text"


def test_numeric_text_menu_has_validation_and_cancel(monkeypatch):
    choices = iter(["99", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(choices))
    assert preflight._choose("text", "Title", "Desc", [("1", "A"), ("2", "B")]) == "2"
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert preflight._choose("text", "Title", "Desc", [("0", "Exit")]) is None


def test_cursor_menu_uses_prompt_toolkit_radio(monkeypatch):
    import sys
    from types import ModuleType
    fake = ModuleType("prompt_toolkit.shortcuts")
    seen = {}
    class Dialog:
        def run(self):
            return "2"
    def radio(**kw):
        seen.update(kw)
        return Dialog()
    fake.radiolist_dialog = radio
    monkeypatch.setitem(sys.modules, "prompt_toolkit.shortcuts", fake)
    assert preflight._choose("tui", "TUI", "Choices", [("1", "A"), ("2", "B")]) == "2"
    assert seen["title"] == "TUI"
    assert seen["values"][1][0] == "2"


def test_text_ui_does_not_need_optional_tui_dependency(monkeypatch):
    monkeypatch.setattr(preflight, "_tui_available", lambda: False)
    assert preflight._ui_mode("text") == "text"


def test_tui_cancel_logs_reason(monkeypatch, capsys):
    import sys
    from types import ModuleType
    fake = ModuleType("prompt_toolkit.shortcuts")
    class CancelDialog:
        def run(self):
            return None
    fake.radiolist_dialog = lambda **kwargs: CancelDialog()
    monkeypatch.setitem(sys.modules, "prompt_toolkit.shortcuts", fake)
    assert preflight._choose("tui", "Menu", "Opis", [("0", "Zakończ")]) is None
    assert "[TUI] Dialog zamknięty bez wyboru." in capsys.readouterr().out


def test_tui_selection_logs_chosen_option(monkeypatch, capsys):
    import sys
    from types import ModuleType
    fake = ModuleType("prompt_toolkit.shortcuts")
    class PickDialog:
        def run(self):
            return "2"
    fake.radiolist_dialog = lambda **kwargs: PickDialog()
    monkeypatch.setitem(sys.modules, "prompt_toolkit.shortcuts", fake)
    assert preflight._choose("tui", "Menu", "Opis", [("2", "Profil")]) == "2"
    assert "[TUI] Wybrano opcję: 2." in capsys.readouterr().out
