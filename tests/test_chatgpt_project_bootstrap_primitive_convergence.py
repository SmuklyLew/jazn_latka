from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_loader_defines_non_circular_host_bootstrap_primitive() -> None:
    loader = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")

    assert len(loader) <= 5000
    assert len(loader) <= 8000
    assert "Materializacja nie oznacza ekstrakcji" in loader
    assert "Host bootstrap primitive jest niezależny od rozpakowanego SYSTEM-u" in loader
    assert 'ZipFile.read("CHATGPT_BOOTSTRAP.py")' in loader
    assert "sprawdź katalog bez pełnego rozpakowania" in loader
    assert "surowe `extractall()` bez walidacji jest zabronione" in loader

    assert loader.index("zmaterializuj dokładne bajty") < loader.index(
        "ponownie zweryfikuj rozmiar i zaufany SHA-256"
    )
    assert loader.index("ponownie zweryfikuj rozmiar i zaufany SHA-256") < loader.index(
        'ZipFile.read("CHATGPT_BOOTSTRAP.py")'
    )
    assert loader.index('ZipFile.read("CHATGPT_BOOTSTRAP.py")') < loader.index(
        "materialized_operator_ready"
    )


def test_project_loader_keeps_neuro_inspired_cognition_runtime_owned() -> None:
    loader = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")
    scientific = _read("docs/project/PROJECT_ASSUMPTIONS_AND_SCIENTIFIC_BOUNDARIES.md")

    assert "warstw poznawczych/neuro-inspirowanych" in loader
    assert "neuro-inspirowanej architektury poznawczej" in loader
    assert "psychology/neuroscience are design inspiration, not biological proof" in scientific
    assert "Inspiracja neurobiologiczna nie oznacza implementacji hipokampa" in scientific


def test_project_loader_keeps_runtime_details_outside_app_instruction() -> None:
    loader = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")

    assert "run.py" not in loader
    assert "main.py" not in loader
    assert "final_visible_text" not in loader
    assert "`AGENTS.chatgpt.md`" not in loader
    assert "--daemon-request-id" not in loader
