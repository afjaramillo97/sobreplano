"""LangChain callback that records model and tokens of every LLM call (principle 5)."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from sobreplano.domain.advisor import LlmCall
from sobreplano.infrastructure.llm.providers import estimate_cost_usd

_COST_QUANTUM = Decimal("0.000001")  # llm_usage.cost_usd is numeric(12, 6)


class UsageCallback(BaseCallbackHandler):
    """Collects one LlmCall per model call, also for calls of a turn that later fails."""

    def __init__(self, model: str, prompt_version: str | None) -> None:
        super().__init__()
        self.model = model  # the configured "provider:model", not what the API echoes back
        self.prompt_version = prompt_version
        self.calls: list[LlmCall] = []

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Append the call's tokens; a response without usage metadata counts as 0 tokens."""
        input_tokens = output_tokens = 0
        for generations in response.generations:
            for generation in generations:
                if isinstance(generation, ChatGeneration) and isinstance(
                    generation.message, AIMessage
                ):
                    usage = generation.message.usage_metadata
                    if usage is not None:
                        input_tokens += usage["input_tokens"]
                        output_tokens += usage["output_tokens"]
        cost = estimate_cost_usd(self.model, input_tokens, output_tokens)
        self.calls.append(
            LlmCall(
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=Decimal(str(cost)).quantize(_COST_QUANTUM) if cost is not None else None,
                prompt_version=self.prompt_version,
            )
        )
