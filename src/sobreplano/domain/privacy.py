"""Redaction of personal data (email, phone, ID number) from text before it is stored or sent."""

import re
from dataclasses import dataclass

EMAIL = "email"
PHONE = "phone"
ID_NUMBER = "id_number"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Colombian mobile: 10 digits starting with 3, optional +57 and separators. The lookarounds keep
# it from matching inside a longer number such as a price written with dots.
_PHONE = re.compile(r"(?<![\d.,])(?:\+?57[\s.-]?)?3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)(?![.,]\d)")
# A number only counts as an ID when a keyword comes up to three words before it: a bare
# 1.234.567.890 can just as well be a price.
_KEYWORD = r"(?:c[eé]dula|c\.c\.|cc|documento|nit|pasaporte|id)"
_ID_NUMBER = re.compile(
    rf"(?<![^\W\d_]){_KEYWORD}(?![^\W\d_])(?:[\s:.,#-]+[^\W\d_]+){{0,3}}[\s:.,#-]*"
    r"(?P<number>\d(?:\.?\d){5,9})(?!\d)(?![.,]\d)",
    re.IGNORECASE,
)

_REPLACEMENTS = {EMAIL: "[correo]", PHONE: "[teléfono]", ID_NUMBER: "[documento]"}


@dataclass(frozen=True)
class Redaction:
    """The text with personal data replaced, and the kind of each replacement."""

    text: str
    kinds: list[str]  # "email", "phone", "id_number", in order of appearance


def redact_personal_data(text: str) -> Redaction:
    """Replace emails, Colombian mobile numbers and keyword-tagged ID numbers in text.

    An ID number is redacted only after a keyword (cédula, CC, documento, NIT, pasaporte, ID),
    so prices such as $450.000.000 or 3.000.000 are never touched. It never raises.
    """
    # (start, end, kind); phone before id_number so the same span is read as a phone.
    spans: list[tuple[int, int, str]] = [
        *((m.start(), m.end(), EMAIL) for m in _EMAIL.finditer(text)),
        *((m.start(), m.end(), PHONE) for m in _PHONE.finditer(text)),
        *((m.start("number"), m.end("number"), ID_NUMBER) for m in _ID_NUMBER.finditer(text)),
    ]
    spans.sort(key=lambda span: span[0])
    pieces: list[str] = []
    kinds: list[str] = []
    cursor = 0
    for start, end, kind in spans:
        if start < cursor:  # overlaps a span already replaced
            continue
        pieces.append(text[cursor:start])
        pieces.append(_REPLACEMENTS[kind])
        kinds.append(kind)
        cursor = end
    pieces.append(text[cursor:])
    return Redaction("".join(pieces), kinds)
