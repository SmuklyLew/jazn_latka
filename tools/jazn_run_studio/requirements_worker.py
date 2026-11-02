"""Read-only first-run checks in the selected interpreter, outside the GUI."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any


def setup_scope(root: Path, python: str) -> str:
    digest = sha256((str(root.resolve()) + "\0" + python).encode())
    for name in ("pyproject.toml", "latka_jazn/resources/dependencies/profiles.json"):
        path = root / name
        digest.update(path.read_bytes() if path.is_file() else b"missing")
    return digest.hexdigest()


def inspect_requirements(root: Path) -> dict[str, Any]:
    from packaging.specifiers import SpecifierSet
    import tomllib
    from latka_jazn.dependencies.common import resolve_profile_requirements, inspect_current_requirements
    from latka_jazn.tools.package_integrity import verify_package_integrity_manifest
    from latka_jazn.core.system_config import read_system_config
    from .core import discovery, Settings

    root = root.resolve()
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    rows: list[dict[str, Any]] = []
    def row(name: str, ok: bool, detail: str, remedy: str, *, required: bool = True) -> None:
        rows.append({"name": name, "state": "PASS" if ok else "FAIL" if required else "OPTIONAL_MISSING",
                     "detail": detail, "remedy": "" if ok else remedy, "required": required})
    row("System i architektura", platform.system() in {"Windows", "Linux"},
        platform.system() + " / " + platform.machine(), "Użyj wspieranej platformy Windows albo Linux.")
    row("Python", platform.python_version() in SpecifierSet(project["requires-python"]),
        platform.python_version() + " / " + sys.executable, "Wybierz interpreter zgodny z pyproject.toml.")
    row("Środowisko wirtualne", sys.prefix != sys.base_prefix, sys.prefix,
        "Zalecane jest odizolowane środowisko z profilem run-studio.", required=False)
    requirements = resolve_profile_requirements(root, ("core", "run-studio"))
    for status in inspect_current_requirements(root, requirements):
        row(status.distribution, status.ready, status.requirement + " / " + str(status.installed_version or "brak"),
            "Sprawdź profil core + run-studio w Studiu Zależności; instalacja wymaga zgody.")
    checked = verify_package_integrity_manifest(root)
    codes = [str(e.get("code", "invalid")) for e in checked.get("errors", []) if isinstance(e, dict)]
    row("Integralność SYSTEM", checked.get("ok") is True,
        "Manifest i pochodzenie: " + ("zweryfikowane" if checked.get("ok") else ", ".join(codes[:8])),
        "Sprawdź paczkę lub zakończ kanoniczną synchronizację metadanych. Nie edytuj manifestu ręcznie.")
    try:
        read_system_config(root)
    except (OSError, ValueError) as exc:
        row("Konfiguracja", False, type(exc).__name__, "Otwórz Konfigurację Qt i popraw profil.")
    else:
        row("Konfiguracja", True, "Kanoniczny schemat konfiguracji", "")
    row("Dostęp do SYSTEM", os.access(root, os.R_OK), "Sprawdzenie uprawnień odczytu", "Sprawdź uprawnienia katalogu.")

    # Optional MCP lives in a separately selected interpreter. Test that real
    # environment, never the Qt worker's imports, and never install implicitly.
    from .core import load_settings, mcp_dependency_preflight, python_executable
    mcp_python = ""
    mcp_checks = {name: False for name in ("mcp", "uvicorn", "starlette", "pydantic", "packaging", "tzdata")}
    mcp_error = ""
    try:
        configured, _digest = load_settings(root)
        mcp_python = python_executable(
            Settings(python=configured.mcp_python or configured.python or sys.executable)
        )
        mcp_checks = mcp_dependency_preflight(mcp_python, root)
    except (OSError, ValueError, RuntimeError) as exc:
        # A broken optional service must never suppress the required GUI audit.
        mcp_error = type(exc).__name__
    row("Interpreter MCP", bool(mcp_python) and not mcp_error,
        mcp_python or mcp_error or "Nieustalony",
        "Wybierz właściwy Python MCP w ustawieniach Studio.", required=False)
    for module, available in mcp_checks.items():
        row("MCP: " + module, available,
            "Import i wersja zgodne z profilem mcp-http" if available else
            "Brak importu, wymaganej wersji lub niezgodny interpreter",
            "Otwórz Studio Zależności; użyj zatwierdzonego profilu mcp-http "
            "i zweryfikowanego wheelhouse w wybranym interpreterze.", required=False)
    return {"schema": "jazn_studio_setup/v1", "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": setup_scope(root, sys.executable), "rows": rows,
            "required_ok": all(r["state"] == "PASS" for r in rows if r["required"]),
            "discovery": discovery(Settings(python=sys.executable)),
            "mcp": {"interpreter": mcp_python, "ready": all(mcp_checks.values()) and not mcp_error,
                    "modules": mcp_checks, "error_type": mcp_error or None},
            "runtime_activated": False, "accepted_visible_turn": False}


def main() -> int:
    try:
        print(json.dumps(inspect_requirements(Path.cwd()), ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"schema": "jazn_studio_setup/v1", "required_ok": False,
                          "error": type(exc).__name__, "rows": []}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
