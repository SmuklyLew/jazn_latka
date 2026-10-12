from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .polish_lemmatizer import PolishLemmatizationEngine

SCHEMA_VERSION = "polish_morphology_frame/v2"


@dataclass(slots=True)
class PolishMorphologyFrame:
    token: str
    lemma_candidates: list[str] = field(default_factory=list)
    pos_candidates: list[str] = field(default_factory=list)
    morph_candidates: list[dict[str, str]] = field(default_factory=list)
    provider: str = "layered_polish_lemmatizer"
    confidence: float = 0.0
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PolishMorphologyAnalyzer:
    """Bounded morphology view backed by the canonical layered lemma providers.

    The built-in provider remains a conservative fallback. If Morfeusz2 or Stanza
    is installed locally, their POS/morph candidates can enrich this frame without
    making either dependency mandatory for runtime startup.
    """

    def __init__(self, root: Path | None = None, *, enable_optional: bool | None = None) -> None:
        self.engine = PolishLemmatizationEngine(root, enable_optional=enable_optional)

    def analyse_token(self, token: str) -> PolishMorphologyFrame:
        text = (token or "").strip()
        if not text:
            return PolishMorphologyFrame(token="", provider="none", confidence=0.0)
        report = self.engine.analyse(text)
        item = next((candidate for candidate in report.tokens if candidate.is_word), None)
        if item is None:
            return PolishMorphologyFrame(token=text, provider="none", confidence=0.0)
        lemmas = list(dict.fromkeys(
            candidate.lemma for candidate in item.lemma_candidates if candidate.lemma
        ))[:8]
        pos = list(dict.fromkeys(
            candidate.pos for candidate in item.lemma_candidates if candidate.pos
        ))[:8]
        morph: list[dict[str, str]] = []
        for candidate in item.lemma_candidates:
            if candidate.morph and candidate.morph not in morph:
                morph.append(dict(candidate.morph))
            if len(morph) >= 8:
                break
        return PolishMorphologyFrame(
            token=text,
            lemma_candidates=lemmas,
            pos_candidates=pos,
            morph_candidates=morph,
            provider=item.provider,
            confidence=item.confidence,
        )
