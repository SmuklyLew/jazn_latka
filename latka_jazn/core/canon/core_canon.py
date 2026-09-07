from __future__ import annotations

from typing import Any

from .identity_canon import LATKA_IDENTITY_KERNEL


SCHEMA_VERSION = "latka_core_canon/v2"

# Core canon is a compatibility projection of the single executable identity
# kernel, not a second independently maintained identity dictionary.
LATKA_CORE_CANON: dict[str, Any] = {
    **LATKA_IDENTITY_KERNEL.to_dict(),
    "schema_version": SCHEMA_VERSION,
    "truth_boundary": {
        "chatgpt_role": "kanał językowy i narzędzie wykonawcze",
        "jazn_role": "źródło runtime, pamięci, kanonu, stanu i granicy prawdy",
        "biological_claims_allowed": False,
        "background_process_claim_allowed": False,
    },
}

REQUIRED_CANON_FIELDS: tuple[str, ...] = (
    "identity_name",
    "display_name",
    "grammar_gender",
    "voice_style",
    "relation_model",
    "visual_canon",
    "safety_principles",
    "narrative_rules",
    "recognition_protocol",
)
