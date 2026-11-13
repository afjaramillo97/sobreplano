"""Use case: answer one advisor message within the day's budget and the conversation's limit."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sobreplano.domain.advisor import AdvisorAnswer, LlmCall
from sobreplano.domain.errors import (
    AdvisorBudgetExceededError,
    AdvisorLimitError,
    AdvisorThreadNotFoundError,
    AdvisorTurnLimitError,
)
from sobreplano.domain.ports import AdvisorAgent, AdvisorThreadRepository, LlmUsageRepository

FEATURE = "advisor"


@dataclass(frozen=True)
class AskAdvisor:
    """Checks the budget and the conversation, asks the agent and records what it spent.

    Does not commit: the caller commits, also after AdvisorLimitError so the spend is kept.
    """

    agent: AdvisorAgent
    usage: LlmUsageRepository
    threads: AdvisorThreadRepository
    daily_budget_usd: Decimal
    max_turns: int

    def __call__(self, thread_id: UUID | None, message: str, today: date) -> AdvisorAnswer:
        """Answer message in thread_id, or in a new conversation when thread_id is None.

        today is the date in America/Bogota, the day the budget is counted on.

        Raises:
            AdvisorBudgetExceededError: if the day's spend already reached the budget; the
                model is not called and no conversation is created.
            AdvisorThreadNotFoundError: if thread_id is unknown or was deleted.
            AdvisorTurnLimitError: if the conversation already has max_turns messages.
            AdvisorLimitError: if the agent needs too many tool rounds; its calls are recorded.
            AdvisorUnavailableError: if the model cannot be reached.
        """
        if self.usage.cost_on(FEATURE, today) >= self.daily_budget_usd:
            raise AdvisorBudgetExceededError(f"advisor budget of {self.daily_budget_usd} USD spent")

        if thread_id is None:
            thread_id = self.threads.create()
        else:
            turns = self.threads.get_turns(thread_id)
            if turns is None:
                raise AdvisorThreadNotFoundError(str(thread_id))
            if turns >= self.max_turns:
                raise AdvisorTurnLimitError(str(thread_id))

        try:
            reply = self.agent.reply(thread_id, message)
        except AdvisorLimitError as error:
            self._record(error.llm_calls, thread_id)
            raise
        self._record(reply.llm_calls, thread_id)
        self.threads.record_turn(thread_id)
        return AdvisorAnswer(thread_id=thread_id, reply=reply)

    def _record(self, calls: list[LlmCall], thread_id: UUID) -> None:
        for call in calls:
            self.usage.add(FEATURE, call, thread_id)
