"""Spanish or English, guessed by counting each language's most frequent words."""

import re
import unicodedata
from typing import Literal

Language = Literal["es", "en"]

# Frequent words that are not also common in the other language (no "a", "no", "es").
_SPANISH = frozenset(
    [
        "de",
        "la",
        "que",
        "el",
        "en",
        "y",
        "los",
        "las",
        "del",
        "se",
        "por",
        "con",
        "para",
        "una",
        "un",
        "su",
        "al",
        "lo",
        "como",
        "mas",
        "pero",
        "sus",
        "le",
        "ya",
        "este",
        "si",
        "porque",
        "esta",
        "entre",
        "cuando",
        "muy",
        "sin",
        "sobre",
        "tambien",
        "me",
        "hasta",
        "hay",
        "donde",
        "desde",
        "todo",
        "nos",
        "puedes",
        "puede",
        "tiene",
        "tienen",
        "cuota",
        "precio",
        "precios",
        "apartamento",
        "alcobas",
        "proyecto",
        "proyectos",
        "mes",
        "meses",
        "anos",
        "tasa",
        "credito",
        "ahorro",
        "ingresos",
        "usted",
        "tu",
    ]
)
_ENGLISH = frozenset(
    [
        "the",
        "and",
        "of",
        "to",
        "in",
        "is",
        "you",
        "that",
        "it",
        "for",
        "on",
        "with",
        "as",
        "are",
        "this",
        "be",
        "at",
        "or",
        "from",
        "your",
        "have",
        "an",
        "by",
        "not",
        "can",
        "would",
        "what",
        "which",
        "there",
        "per",
        "month",
        "months",
        "price",
        "prices",
        "apartment",
        "bedrooms",
        "project",
        "projects",
        "rate",
        "loan",
        "savings",
        "income",
        "afford",
        "could",
        "will",
        "these",
        "those",
    ]
)
_WORD = re.compile(r"[a-z]+")


def _words(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.lower())
    return _WORD.findall("".join(c for c in plain if not unicodedata.combining(c)))


def detect_language(text: str) -> Language:
    """The language with more frequent-word hits; Spanish on a tie, as the default audience."""
    words = _words(text)
    spanish = sum(word in _SPANISH for word in words)
    english = sum(word in _ENGLISH for word in words)
    return "en" if english > spanish else "es"
