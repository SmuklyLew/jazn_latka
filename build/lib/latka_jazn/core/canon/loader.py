from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, TypeVar

from latka_jazn.memory.memory_root import resolve_memory_root

from .canon_registry import load_python_canon_registry
from .identity_canon import LATKA_IDENTITY_KERNEL
from .schema import IdentityCanon, RecognitionProtocol
from .validator import validate_identity_canon_data

TIdentityCanon = TypeVar("TIdentityCanon", bound=IdentityCanon)


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"canon JSON must be an object: {path}")
    return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _infer_project_root(path: Path) -> Path | None:
    parts = path.parts
    if "latka_jazn" in parts:
        idx = parts.index("latka_jazn")
        if idx > 0:
            return Path(*parts[:idx])
    return None


def _private_override_path_for(path: Path) -> Path | None:
    root = _infer_project_root(path.resolve())
    if root is None:
        return None
    candidate = resolve_memory_root(root) / "raw" / "LATKA_IDENTITY_CANON.json"
    if candidate.resolve() == path.resolve():
        return None
    return candidate


def _contains_expected(candidate: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(candidate, dict):
            return False
        return all(key in candidate and _contains_expected(candidate[key], value) for key, value in expected.items())
    return candidate == expected


def _identity_kernel_mismatches(candidate: dict[str, Any]) -> list[str]:
    """Return protected identity fields whose mirror differs from code authority.

    Mirrors may carry compatibility metadata, but every field owned by the
    executable kernel must match exactly.
    """
    expected = LATKA_IDENTITY_KERNEL.to_dict()
    protected = (
        "identity_name", "display_name", "dialogue_language", "grammar_gender",
        "timestamp_format", "voice_style", "relation_model", "visual_canon",
        "safety_principles", "narrative_rules", "truthful_memory_contract",
        "recognition_protocol", "time_protocol",
    )
    mismatches: list[str] = []
    for key in protected:
        if key not in candidate or not _contains_expected(candidate.get(key), expected.get(key)):
            mismatches.append(key)
    return mismatches


def load_identity_canon_data(path: Path, *, include_private_override: bool = True) -> dict[str, Any]:
    """Load the executable Python canon and audit non-authoritative mirrors.

    Public JSON and historical private identity JSON are intentionally *not*
    deep-merged into protected identity fields.  They are evidence/migration
    surfaces.  This makes the runtime identity authority deterministic and
    source-controlled while preserving auditability of older material.
    """
    source_path = Path(path)
    root = _infer_project_root(source_path.resolve())
    data = load_python_canon_registry(
        root=root,
        include_local_private_extension=include_private_override,
    )
    source_status = data.setdefault("source_status", {})
    source_status["identity_authority"] = "source_controlled_python_identity_kernel"

    if source_path.exists():
        try:
            mirror = _read_json(source_path)
            validate_identity_canon_data(mirror)
        except Exception as exc:
            source_status["public_mirror_loaded"] = False
            source_status["public_mirror_path"] = str(source_path)
            source_status["public_mirror_error"] = f"{type(exc).__name__}: {exc}"
        else:
            mismatches = _identity_kernel_mismatches(mirror)
            source_status["public_mirror_loaded"] = True
            source_status["public_mirror_path"] = str(source_path)
            source_status["public_mirror_sha256"] = _sha256_file(source_path)
            source_status["public_mirror_kernel_match"] = not mismatches
            source_status["public_mirror_kernel_mismatches"] = mismatches
            source_status["public_mirror_policy"] = "audit_only_no_runtime_override"

    if include_private_override:
        private_path = _private_override_path_for(source_path)
        if private_path and private_path.exists():
            try:
                private_data = _read_json(private_path)
            except Exception as exc:
                source_status["private_override_loaded"] = False
                source_status["private_override_path"] = str(private_path)
                source_status["private_override_error"] = f"{type(exc).__name__}: {exc}"
            else:
                source_status["private_override_loaded"] = False
                source_status["private_override_path"] = str(private_path)
                source_status["private_candidate_present"] = True
                source_status["private_candidate_sha256"] = _sha256_file(private_path)
                source_status["private_candidate_top_level_keys"] = sorted(str(key) for key in private_data)[:64]
                source_status["private_override_policy"] = "evidence_only_no_identity_kernel_override"

    validate_identity_canon_data(data)
    return data


def load_identity_canon(path: Path, *, canon_cls: type[TIdentityCanon] = IdentityCanon) -> TIdentityCanon:
    data = load_identity_canon_data(path)
    rec = data.get("recognition_protocol", {}) or {}
    return canon_cls(
        name=data.get("identity_name") or "Łatka",
        display_name=data.get("display_name") or "Łatka",
        grammar_gender=data.get("grammar_gender") or "feminine",
        voice_style=data.get("voice_style") or LATKA_IDENTITY_KERNEL.voice_style,
        relation_model=data.get("relation_model") or LATKA_IDENTITY_KERNEL.relation_model,
        visual_canon=data.get("visual_canon") or LATKA_IDENTITY_KERNEL.visual_canon,
        safety_principles=data.get("safety_principles") or LATKA_IDENTITY_KERNEL.safety_principles,
        narrative_rules=data.get("narrative_rules") or LATKA_IDENTITY_KERNEL.narrative_rules,
        recognition=RecognitionProtocol(
            user_sign=rec.get("user_sign") or rec.get("primary_sign") or LATKA_IDENTITY_KERNEL.recognition.user_sign,
            latka_sign=rec.get("latka_sign") or rec.get("latka_response_sign") or LATKA_IDENTITY_KERNEL.recognition.latka_sign,
            rule=rec.get("rule") or LATKA_IDENTITY_KERNEL.recognition.rule,
        ),
        kernel=LATKA_IDENTITY_KERNEL,
        raw=data,
    )
