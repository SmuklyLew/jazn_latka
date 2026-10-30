"""Local settings containment must compare canonical bases without relaxing link refusal."""
from pathlib import Path

import pytest

from latka_jazn.core.local_settings_layout import (
    resolve_local_settings_layout, verify_local_descendant,
)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "system"
    (root / ".settings").mkdir(parents=True)
    return root


def test_normal_future_operator_descendant_is_allowed(tmp_path):
    layout = resolve_local_settings_layout(_root(tmp_path))
    target = layout.operator / "jazn_run_studio" / "settings.json"
    assert verify_local_descendant(target, layout) == target.resolve()


def test_canonical_parent_representation_matches_canonical_child(tmp_path, monkeypatch):
    layout = resolve_local_settings_layout(_root(tmp_path))
    target = layout.operator / "jazn_run_studio" / "settings.json"
    physical_local = tmp_path / "physical-volume" / ".settings_local"
    ordinary_resolve = type(target).resolve

    def canonical_resolve(self, *args, **kwargs):
        # Model different lexical/physical spellings of the same safe root,
        # as can be observed when Windows resolves newly-created paths.
        if self == layout.local:
            return physical_local
        if self == target:
            return physical_local / "operator" / "jazn_run_studio" / "settings.json"
        return ordinary_resolve(self, *args, **kwargs)

    monkeypatch.setattr(type(target), "resolve", canonical_resolve)
    assert verify_local_descendant(target, layout) == (
        physical_local / "operator" / "jazn_run_studio" / "settings.json"
    )


def test_link_inside_operator_root_is_rejected(tmp_path):
    root = _root(tmp_path)
    layout = resolve_local_settings_layout(root)
    layout.operator.mkdir(parents=True)
    external = tmp_path / "outside"
    external.mkdir()
    redirected = layout.operator / "jazn_run_studio"
    try:
        redirected.symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Host does not permit creating directory symlinks")
    with pytest.raises(ValueError, match="redirected"):
        verify_local_descendant(redirected / "settings.json", layout)
