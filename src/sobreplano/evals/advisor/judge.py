"""LLM judge of the advisor: one binary rubric per call, reason first, structured output."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, get_args

import openai
from openai import OpenAI
from openai.types import CompletionUsage
from pydantic import BaseModel, ConfigDict

from sobreplano.domain.advisor import LlmCall
from sobreplano.evals.advisor.cases import RubricId
from sobreplano.infrastructure.llm.prompt_store import Prompt, load_prompt
from sobreplano.infrastructure.llm.providers import (
    PROVIDERS,
    REQUEST_TIMEOUT_SECONDS,
    estimate_cost_usd,
)
from sobreplano.infrastructure.settings import Settings

DEFAULT_JUDGE_MODEL = "openai:gpt-6.1-terra"
JUDGE_PROMPTS = "sobreplano.evals.prompts"
MAX_COMPLETION_TOKENS = 2048
# Low effort: the reason field already makes the model justify before it decides.
REASONING_EFFORT = "low"
# Per tool result, so a long search does not multiply the judge's cost.
MAX_TOOL_RESULT_CHARS = 6000
_TAGS = (
    "<conversation>",
    "</conversation>",
    "<tool_results>",
    "</tool_results>",
    "<answer>",
    "</answer>",
)
_COST_QUANTUM = Decimal("0.000001")


class JudgeUnavailableError(Exception):
    """The judge cannot run: bad EVAL_JUDGE_MODEL, unknown provider or no API key."""


class Verdict(BaseModel):
    """The judge's answer; the reason comes first so the model reasons before deciding."""

    model_config = ConfigDict(extra="forbid")

    reason: str
    passed: bool


@dataclass(frozen=True)
class JudgeInput:
    """What the judge sees: user messages so far, this turn's tool results and the answer."""

    user_messages: list[str]
    tool_results: list[str]
    answer: str


@dataclass(frozen=True)
class JudgeOutcome:
    """A verdict with its LLM call, or the error that prevented it."""

    verdict: Verdict | None
    call: LlmCall | None
    error: str | None = None


class Judge(Protocol):
    """Judges one answer against one rubric."""

    model: str
    prompt_version: str

    def judge(self, rubric: RubricId, data: JudgeInput) -> JudgeOutcome: ...


def judge_prompt() -> Prompt:
    """The judge prompt file: a preamble and one `## <rubric>` section per rubric."""
    return load_prompt(JUDGE_PROMPTS, "judge")


def rubric_texts(prompt: Prompt) -> tuple[str, dict[str, str]]:
    """Split the prompt into its preamble and the text of each rubric.

    Raises:
        ValueError: if a rubric of RubricId has no section, or a section is not a rubric.
    """
    preamble, *sections = prompt.text.split("\n## ")
    rubrics: dict[str, str] = {}
    for section in sections:
        name, _, body = section.partition("\n")
        rubrics[name.strip()] = body.strip()
    expected = set(get_args(RubricId))
    if set(rubrics) != expected:
        raise ValueError(f"judge prompt rubrics {sorted(rubrics)} != {sorted(expected)}")
    return preamble.strip(), rubrics


def system_message(prompt: Prompt, rubric: RubricId) -> str:
    """The preamble followed by the one rubric being judged."""
    preamble, rubrics = rubric_texts(prompt)
    return f"{preamble}\n\n## Rubric: {rubric}\n\n{rubrics[rubric]}"


def user_message(data: JudgeInput) -> str:
    """The data block; tags inside the data are removed so it cannot close a block early."""

    def clean(text: str) -> str:
        for tag in _TAGS:
            text = text.replace(tag, "")
        return text

    conversation = "\n".join(f"{i}. {clean(m)}" for i, m in enumerate(data.user_messages, 1))
    results = (
        "\n".join(f"- {clean(r[:MAX_TOOL_RESULT_CHARS])}" for r in data.tool_results)
        or "(no tools were called in this turn)"
    )
    return (
        f"<conversation>\n{conversation}\n</conversation>\n"
        f"<tool_results>\n{results}\n</tool_results>\n"
        f"<answer>\n{clean(data.answer)}\n</answer>"
    )


class OpenAIJudge:
    """Judge over Chat Completions with a strict Pydantic response format."""

    def __init__(self, client: OpenAI, *, model: str, api_model: str) -> None:
        self.model = model
        self._client = client
        self._api_model = api_model
        self._prompt = judge_prompt()
        self.prompt_version = self._prompt.version
        rubric_texts(self._prompt)  # fail at startup, not on the first call

    def judge(self, rubric: RubricId, data: JudgeInput) -> JudgeOutcome:
        """Ask for a verdict; API errors, refusals and cut-off answers become outcome errors."""
        try:
            completion = self._client.chat.completions.parse(
                model=self._api_model,
                messages=[
                    {"role": "system", "content": system_message(self._prompt, rubric)},
                    {"role": "user", "content": user_message(data)},
                ],
                response_format=Verdict,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
                reasoning_effort=REASONING_EFFORT,
            )
        except (openai.LengthFinishReasonError, openai.ContentFilterFinishReasonError):
            return JudgeOutcome(None, None, "answer cut off or filtered")
        except openai.APIError as error:
            return JudgeOutcome(None, None, f"API error: {type(error).__name__}")

        call = self._call(completion.usage)
        message = completion.choices[0].message
        if message.refusal:
            return JudgeOutcome(None, call, f"refused: {message.refusal}")
        if message.parsed is None:
            return JudgeOutcome(None, call, "empty parsed answer")
        return JudgeOutcome(message.parsed, call)

    def _call(self, usage: CompletionUsage | None) -> LlmCall:
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = estimate_cost_usd(self.model, input_tokens, output_tokens)
        return LlmCall(
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=None if cost is None else Decimal(str(cost)).quantize(_COST_QUANTUM),
            prompt_version=self.prompt_version,
        )


def judge_model_name() -> str:
    """EVAL_JUDGE_MODEL, or the default judge."""
    return os.environ.get("EVAL_JUDGE_MODEL") or DEFAULT_JUDGE_MODEL


def build_judge(settings: Settings, model: str, *, advisor_model: str) -> OpenAIJudge:
    """The judge for model ("provider:model").

    Raises:
        JudgeUnavailableError: if model is malformed, its provider unknown, its API key
            missing, or it is the advisor's own model (a model favors its own answers).
    """
    provider_name, separator, api_model = model.partition(":")
    if not separator or not provider_name or not api_model:
        raise JudgeUnavailableError(f"EVAL_JUDGE_MODEL must be provider:model, got {model!r}")
    if model == advisor_model:
        raise JudgeUnavailableError(f"the judge must not be the advisor's model ({model})")
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        raise JudgeUnavailableError(f"unknown provider {provider_name!r} in EVAL_JUDGE_MODEL")
    api_key = provider.api_key(settings)
    if api_key is None or not api_key.get_secret_value():
        raise JudgeUnavailableError(f"{provider.api_key_variable} is not set")
    client = OpenAI(
        api_key=api_key.get_secret_value(),
        base_url=provider.base_url,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return OpenAIJudge(client, model=model, api_model=api_model)


def rubrics_for(explicit: Sequence[RubricId], cites_source: bool) -> list[RubricId]:
    """The rubrics of a turn: the case's own, plus price_citation where cites_source applied."""
    rubrics = list(explicit)
    if cites_source and "price_citation" not in rubrics:
        rubrics.append("price_citation")
    return rubrics
