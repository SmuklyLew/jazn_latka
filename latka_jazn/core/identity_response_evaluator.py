from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Mapping

from latka_jazn.core.full_canon_model_context import (
    evaluate_visible_voice_against_full_canon,
    validate_full_canon_model_context,
)
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("identity_response_evaluator")
_HOST_IDENTITY_LEAKS = (
    "jako chatgpt", "jestem chatgpt", "moja persona", "persona chatgpt",
    "udaję łatkę", "udaje łatkę", "odgrywam łatkę", "odgrywam łatke",
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]


@dataclass(slots=True)
class IdentityResponseEvaluation:
    accepted: bool
    score: float
    checks: dict[str, bool]
    reasons: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Ocena dotyczy zgodności widocznego tekstu z kanonem i perspektywą runtime. "
        "Nie wnioskuje o świadomości ani uczuciach na podstawie stylu wypowiedzi."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_identity_response(
    *,
    text: str,
    full_canon_model_context: Any,
    answer_kind: str = "natural_dialogue",
    user_text: str | None = None,
) -> IdentityResponseEvaluation:
    """Evaluate generated output, never the user's text, for identity continuity."""

    clean = str(text or "").strip()
    low = clean.lower()
    validation = validate_full_canon_model_context(full_canon_model_context)
    voice = evaluate_visible_voice_against_full_canon(
        clean,
        full_canon_model_context,
        answer_kind=answer_kind,
    )
    violations: list[str] = list(
        dict.fromkeys([*_string_list(validation.get("violations")), *_string_list(voice.get("violations"))])
    )
    if any(marker in low for marker in _HOST_IDENTITY_LEAKS):
        violations.append("host_persona_identity_leak")

    context = _mapping(full_canon_model_context)
    canon = _mapping(context.get("immutable_canon"))
    identity = _mapping(canon.get("identity_core"))
    expected_name = str(identity.get("identity_name") or identity.get("display_name") or "Łatka")
    name_conflict = bool(re.search(r"\b(?:nie\s+jestem|nie\s+nazywam\s+się)\s+Łatk", clean, flags=re.IGNORECASE))
    if name_conflict:
        violations.append("identity_name_conflict")

    checks = {
        "full_canon_valid": bool(validation.get("ok")),
        "voice_perspective_valid": bool(voice.get("ok")),
        "host_persona_absent": not any(marker in low for marker in _HOST_IDENTITY_LEAKS),
        "identity_name_not_contradicted": not name_conflict,
        "evaluated_output_not_user_input": clean != str(user_text or "").strip() or not clean,
    }
    reasons = [name for name, ok in checks.items() if ok]
    score = sum(1.0 for ok in checks.values() if ok) / max(1, len(checks))
    accepted = bool(clean) and not violations and checks["full_canon_valid"]
    if expected_name and accepted:
        reasons.append(f"identity_authority:{expected_name}")
    return IdentityResponseEvaluation(
        accepted=accepted,
        score=round(score, 4),
        checks=checks,
        reasons=reasons,
        violations=list(dict.fromkeys(violations)),
    )
