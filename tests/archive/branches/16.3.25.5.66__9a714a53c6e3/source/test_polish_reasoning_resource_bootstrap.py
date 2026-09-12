from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from latka_jazn.nlp.local_resource_paths import (
    install_manifest_path,
    installed_provider_names,
    polish_nlp_data_root,
    stanza_model_dir,
)
from latka_jazn.nlp.providers.optional_stanza_provider import OptionalStanzaPolishProvider
from latka_jazn.nlp_reasoning.adapters.stanza_provider_adapter import StanzaReasoningAdapter
from latka_jazn.nlp.providers.optional_stanza_provider import StanzaTextAnalysis, StanzaTokenAnnotation


def _load_bootstrap_module():
    path = Path(__file__).resolve().parents[1] / "tools" / "bootstrap_polish_reasoning_resources.py"
    spec = importlib.util.spec_from_file_location("bootstrap_polish_reasoning_resources", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_resources_live_beside_package_not_in_workspace_runtime(monkeypatch) -> None:
    monkeypatch.delenv("LATKA_NLP_DATA_DIR", raising=False)
    root = Path(__file__).resolve().parents[1]
    expected = root / "latka_jazn" / "local_resources" / "nlp"
    assert polish_nlp_data_root(root) == expected.resolve()
    assert "workspace_runtime" not in str(polish_nlp_data_root(root))


def test_environment_override_is_explicit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LATKA_NLP_DATA_DIR", str(tmp_path / "custom"))
    assert polish_nlp_data_root() == (tmp_path / "custom").resolve()


def test_install_manifest_enables_only_confirmed_providers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LATKA_NLP_DATA_DIR", str(tmp_path))
    manifest = {
        "schema_version": "latka_polish_reasoning_install/v2",
        "resources": [
            {"provider": "morfeusz2-sgjp", "installed": True},
            {"provider": "stanza-pl", "installed": False},
        ],
    }
    install_manifest_path().parent.mkdir(parents=True, exist_ok=True)
    install_manifest_path().write_text(json.dumps(manifest), encoding="utf-8")
    assert installed_provider_names() == {"morfeusz2-sgjp"}


def test_stanza_provider_uses_local_dir_and_disables_download(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "stanza"
    (model_dir / "pl").mkdir(parents=True)
    (model_dir / "resources.json").write_text("{}", encoding="utf-8")
    calls: list[dict[str, object]] = []

    class FakePipeline:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def __call__(self, text: str):
            word = SimpleNamespace(lemma="piosenka", upos="NOUN", feats="Case=Gen")
            return SimpleNamespace(sentences=[SimpleNamespace(words=[word])])

    monkeypatch.setitem(sys.modules, "stanza", SimpleNamespace(Pipeline=FakePipeline))
    provider = OptionalStanzaPolishProvider(enabled=True, model_dir=model_dir)
    assert provider.available is True
    assert calls[0]["dir"] == str(model_dir.resolve())
    assert calls[0]["download_method"] is None
    assert provider.analyse_token("piosenki", folded="piosenki")[0].lemma == "piosenka"


def test_reasoning_adapter_wraps_existing_stanza_provider(tmp_path: Path) -> None:
    class FakeProvider:
        available = True
        last_error = None
        model_dir = tmp_path

        def analyse_text(self, text: str, *, include_ner: bool = False):
            assert text == "piosenki"
            assert include_ner is False
            token = StanzaTokenAnnotation(
                text="piosenki",
                lemma="piosenka",
                upos="NOUN",
                xpos="subst:pl:gen:f",
                feats={"Case": "Gen", "Number": "Plur"},
                head=0,
                deprel="root",
            )
            return StanzaTextAnalysis("optional_stanza_pl", True, sentences=[[token]])

    adapter = StanzaReasoningAdapter(provider=FakeProvider())  # type: ignore[arg-type]
    rows = adapter.analyse("piosenki")
    assert rows[0].lemma == "piosenka"
    assert rows[0].features["case"] == "Gen"
    assert rows[0].provider == "stanza-pl"


def test_bootstrap_dry_run_uses_project_local_path_and_does_not_write(tmp_path: Path, monkeypatch) -> None:
    module = _load_bootstrap_module()
    commands: list[list[str]] = []
    monkeypatch.setattr(module, "_run", lambda command, dry_run: commands.append(command))
    rc = module.main(["--profile", "recommended", "--data-dir", str(tmp_path), "--dry-run"])
    assert rc == 0
    assert commands
    assert any("morfeusz2==1.99.15" in part for command in commands for part in command)
    assert any("stanza>=1.14,<2" in part for command in commands for part in command)
    assert not (tmp_path / "install_manifest.json").exists()
    assert stanza_model_dir(Path(__file__).resolve().parents[1]).name == "stanza"


def test_bootstrap_and_lock_use_pypi_not_broken_homepage() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "tools" / "bootstrap_polish_reasoning_resources.py").read_text(encoding="utf-8")
    lock = json.loads((root / "latka_jazn" / "resources" / "polish_reasoning" / "sources.lock.json").read_text(encoding="utf-8"))
    assert "https://pypi.org/project/morfeusz2/" in script
    assert "morfeusz.sgjp.pl" not in script
    assert lock["sources"]["morfeusz2-sgjp"]["url"] == "https://pypi.org/project/morfeusz2/"
