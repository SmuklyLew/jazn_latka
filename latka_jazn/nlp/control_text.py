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
_CREATIVE_SECTION_RE = re.compile(
    r"^\s*\[(?:chorus|verse|bridge|pre[- ]?chorus|intro|outro|refren|zwrotka|przedrefren|łącznik|lacznik)[^\]]*\]\s*$",
    re.IGNORECASE | re.UNICODE,
)
_MATERIAL_SEPARATOR_RE = re.compile(r"^\s*(?:-{3,}|_{3,}|={3,})\s*$")
_META_RESUME_RE = re.compile(
    r"^\s*(?:@|popatrz\b|sprawdź\b|sprawdz\b|oceń\b|ocen\b|przeanalizuj\b|"
    r"porównaj\b|porownaj\b|przeredaguj\b|popraw\b|przygotuj\b|wracając\b|wracajac\b)",
    re.IGNORECASE | re.UNICODE,
)


def _mask_match(match: re.Match[str]) -> str:
    text = match.group(0)
    return "\n" * text.count("\n") + " "


def _mask_line(line: str) -> str:
    ending = "\n" if line.endswith("\n") else ""
    return ending


def _mask_structured_creative_material(text: str) -> tuple[str, int]:
    """Mask structured lyrics while preserving instructions around the material."""
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    in_material = False
    blank_run = 0
    span_count = 0

    for line in lines:
        stripped = line.strip()
        if _CREATIVE_SECTION_RE.match(stripped):
            if not in_material:
                span_count += 1
            in_material = True
            blank_run = 0
            output.append(_mask_line(line))
            continue

        if in_material:
            if _MATERIAL_SEPARATOR_RE.match(stripped):
                in_material = False
                blank_run = 0
                output.append(line)
                continue
            if blank_run > 0 and stripped and _META_RESUME_RE.match(stripped):
                in_material = False
                blank_run = 0
                output.append(line)
                continue
            output.append(_mask_line(line))
            blank_run = blank_run + 1 if not stripped else 0
            continue

        output.append(line)

    return "".join(output), span_count


def extract_intent_control_text(text: str) -> IntentControlText:
    original = str(text or "")
    masked, creative_spans = _mask_structured_creative_material(original)
    count = creative_spans
    for pattern in (_FENCED_CODE_RE, _BLOCKQUOTE_RE, _INLINE_CODE_RE, *_QUOTED_PATTERNS):
        masked, substitutions = pattern.subn(_mask_match, masked)
        count += substitutions
    control = re.sub(r"[ \t\r\f\v]+", " ", masked)
    control = re.sub(r"\n{3,}", "\n\n", control).strip()
    # Jeżeli cała wiadomość jest cytatem, kodem lub materiałem twórczym, nie
    # przywracaj jej jako tekstu sterującego. Oryginał nadal trafia do detektora
    # materiału i do odpowiedzi, ale jego słowa nie mogą przejąć routingu.
    if not control and not count:
        control = original.strip()
    return IntentControlText(
        original_text=original,
        control_text=control,
        quoted_material_masked=count > 0,
        masked_span_count=count,
    )
