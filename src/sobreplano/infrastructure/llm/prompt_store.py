"""Prompts kept as files inside the package, each with a version derived from its text."""

import hashlib
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

APP_PROMPTS = "sobreplano.infrastructure.llm.prompts"
VERSION_LENGTH = 12


@dataclass(frozen=True)
class Prompt:
    """A prompt's text and its version: the first 12 hex chars of the text's sha256."""

    name: str
    text: str
    version: str


@cache
def load_prompt(package: str, name: str) -> Prompt:
    """Read `<name>.md` from `package` exactly as stored, trailing newline included.

    The text is not stripped, so the version changes with any byte of the file.

    Raises:
        FileNotFoundError: if the package has no such prompt file.
    """
    text = files(package).joinpath(f"{name}.md").read_text(encoding="utf-8")
    version = hashlib.sha256(text.encode("utf-8")).hexdigest()[:VERSION_LENGTH]
    return Prompt(name=name, text=text, version=version)
