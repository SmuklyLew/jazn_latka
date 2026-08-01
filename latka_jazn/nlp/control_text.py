from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("intent_control_text")


@dataclass(slots=True, frozen=True)
class IntentControlText:
    original_text: str
    control_text: str
    quoted_material_masked: bool
    masked_span_count: int
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Tekst sterujący służy wyłącznie do klasyfikacji intencji. Oryginalna wiadomość pozostaje bez zmian "
        "dla odpowiedzi, zapisu źródłowego i audytu."
    )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_BLOCKQUOTE_RE = re.compile(r"(?m)^\s*>[^\n]*(?:\n|$)")
_QUOTED_PATTERNS = (
    re.compile(r"„[^”]*”", re.DOTALL),
    re.compile(r"“[^”]*”", re.DOTALL),
    re.compile(r"«[^»]*»", re.DOTALL),
    re.compile(r'"[^"\n]{1,2000}"'),
)


def _mask_match(match: re.Match[str]) -> str:
    text = match.group(0)
    return "\n" * text.count("\n") + " "


def extract_intent_control_text(text: str) -> IntentControlText:
    original = str(text or "")
    masked = original
    count = 0
    for pattern in (_FENCED_CODE_RE, _BLOCKQUOTE_RE, _INLINE_CODE_RE, *_QUOTED_PATTERNS):
        masked, substitutions = pattern.subn(_mask_match, masked)
        count += substitutions
    control = re.sub(r"[ \t\r\f\v]+", " ", masked)
    control = re.sub(r"\n{3,}", "\n\n", control).strip()
    # Jeżeli cała wiadomość jest cytatem lub blokiem kodu, nie przywracaj
    # materiału cytowanego jako tekstu sterującego. Taki fallback ponownie
    # uruchamiałby dokładnie te frazy, które miały zostać wyłączone z routingu.
    if not control and not count:
        control = original.strip()
    return IntentControlText(
        original_text=original,
        control_text=control,
        quoted_material_masked=count > 0,
        masked_span_count=count,
    )
