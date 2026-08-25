from __future__ import annotations

from pathlib import Path
import json
import unicodedata
from .base import ProviderLemmaCandidate
from ..polish_normalizer import PolishTextNormalizer

class BuiltinPolishLemmaProvider:
    name = "builtin_safe_polish_current_line"
    available = True

    _RULES: tuple[tuple[str, str, float], ...] = (
        ("ami", "", 0.50), ("ach", "", 0.50), ("ego", "y", 0.46), ("emu", "y", 0.46),
        ("owa", "owy", 0.42), ("owej", "owy", 0.42), ("owych", "owy", 0.42),
        ("ścią", "ść", 0.46), ("scią", "ść", 0.40), ("ści", "ść", 0.44), ("sci", "ść", 0.38),
        ("anie", "ać", 0.42), ("enie", "ić", 0.40), ("acją", "acja", 0.45), ("acja", "acja", 0.70),
        ("ego", "", 0.35), ("ami", "", 0.35), ("ami", "a", 0.32),
    )

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root).resolve() if root else None
        self.overrides = self._load_overrides()

    def _load_overrides(self) -> dict[str, str]:
        package_resource = Path(__file__).resolve().parents[2] / "resources" / "polish_lemma_overrides.json"
        candidates: list[Path] = [package_resource]
        if self.root:
            rooted_resource = self.root / "latka_jazn" / "resources" / "polish_lemma_overrides.json"
            if rooted_resource.resolve() != package_resource.resolve():
                candidates.append(rooted_resource)
            candidates.append(self.root / "memory" / "raw" / "polish_lemma_overrides.json")
        merged: dict[str, str] = {}
        normalizer = PolishTextNormalizer()
        for path in candidates:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                raw = (data.get("overrides") or data) if isinstance(data, dict) else {}
                if not isinstance(raw, dict):
                    continue
                for key, value in raw.items():
                    normalized_key = normalizer.ascii_fold(str(key).strip()).casefold()
                    normalized_value = unicodedata.normalize("NFC", str(value).strip()).casefold()
                    if normalized_key and normalized_value:
                        merged[normalized_key] = normalized_value
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                continue
        return merged

    def analyse_token(self, token: str, *, folded: str, context: str = "") -> list[ProviderLemmaCandidate]:
        if not token:
            return []
        candidates: list[ProviderLemmaCandidate] = []
        if folded in self.overrides:
            candidates.append(ProviderLemmaCandidate(
                lemma=self.overrides[folded], confidence=0.94, provider=self.name,
                explanation="jawny override słownika Jaźni"
            ))
        # Zachowaj powierzchniową formę jako bezpiecznego kandydata. To chroni przed złym ucinaniem końcówek.
        candidates.append(ProviderLemmaCandidate(
            lemma=folded, confidence=0.62 if len(folded) >= 4 else 0.78, provider=self.name,
            explanation="forma znormalizowana jako bezpieczny fallback"
        ))
        if len(folded) >= 6:
            for suffix, replacement, confidence in self._RULES:
                if folded.endswith(suffix) and len(folded) - len(suffix) >= 3:
                    lemma = folded[: -len(suffix)] + replacement
                    if lemma and lemma != folded:
                        candidates.append(ProviderLemmaCandidate(
                            lemma=lemma, confidence=confidence, provider=self.name,
                            explanation=f"ostrożna reguła sufiksu -{suffix}"
                        ))
        # dedupe by lemma, highest confidence wins
        best: dict[str, ProviderLemmaCandidate] = {}
        for c in candidates:
            prev = best.get(c.lemma)
            if prev is None or c.confidence > prev.confidence:
                best[c.lemma] = c
        return sorted(best.values(), key=lambda c: (-c.confidence, c.lemma))[:5]
