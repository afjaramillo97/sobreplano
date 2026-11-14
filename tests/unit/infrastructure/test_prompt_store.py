"""Unit tests for the prompt store: pinned versions and how a version is derived."""

import hashlib

import pytest

from sobreplano.infrastructure.llm.prompt_store import APP_PROMPTS, load_prompt

# Changing a prompt changes its version: update the value here in the same PR, so the change
# shows up in review (SPEC 09).
PINNED_VERSIONS = {
    "advisor_system": "51a5d765091a",
    "extractor": "6682e7fa8220",
}


@pytest.mark.parametrize(("name", "version"), PINNED_VERSIONS.items())
def test_prompt_versions_are_pinned(name: str, version: str) -> None:
    assert load_prompt(APP_PROMPTS, name).version == version


def test_judge_prompt_version_is_pinned() -> None:
    # The judge lives with the evals; its calibration is only valid for this version.
    assert load_prompt("sobreplano.evals.prompts", "judge").version == "75d053a91f88"


@pytest.mark.parametrize("name", PINNED_VERSIONS)
def test_version_is_the_short_sha256_of_the_exact_text(name: str) -> None:
    prompt = load_prompt(APP_PROMPTS, name)
    assert prompt.name == name
    assert prompt.version == hashlib.sha256(prompt.text.encode("utf-8")).hexdigest()[:12]


def test_text_is_read_as_stored() -> None:
    # The advisor prompt ended in a newline as a constant; the extractor prompt did not.
    assert load_prompt(APP_PROMPTS, "advisor_system").text.endswith("separators.\n")
    assert load_prompt(APP_PROMPTS, "extractor").text.endswith("missing values.")


def test_loading_twice_returns_the_cached_prompt() -> None:
    assert load_prompt(APP_PROMPTS, "extractor") is load_prompt(APP_PROMPTS, "extractor")


def test_unknown_prompt_fails() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt(APP_PROMPTS, "missing")
