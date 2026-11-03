"""Clean text of a project page: what the extraction model reads and what its reuse key hashes."""

import re

from bs4 import BeautifulSoup

# Page chrome and the contact form: noise for the model, and the form is about personal data.
NOISE_TAGS = [
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "template",
    "header",
    "footer",
    "nav",
    "form",
]
BLOCK_END = "\x00"
BLOCK_TAGS = ["p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section"]


def clean_text(soup: BeautifulSoup) -> str:
    """Visible text without page chrome, one block per line. Mutates the soup."""
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    # "55.58 m<sup>2</sup>" would otherwise read "55.58 m 2".
    for sup in soup("sup"):
        sup.replace_with("²" if sup.get_text(strip=True) == "2" else sup.get_text())
    # Line breaks only after blocks, so inline pieces ("Desde <span>$506.100.000</span>")
    # stay on one line. The source HTML's own newlines are just whitespace, hence the marker.
    for block in soup(BLOCK_TAGS):
        block.append(BLOCK_END)
    text = re.sub(r"\s+", " ", soup.get_text(" "))
    lines = (line.strip() for line in text.split(BLOCK_END))
    return "\n".join(line for line in lines if line)
