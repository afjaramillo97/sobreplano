"""Wires the advisor: agent, tools, repositories and limits for one database session.

Kept apart from composition.py so the scraper Lambda, which has no advisor dependencies,
never imports LangGraph.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.orm import Session

from sobreplano.application.ask_advisor import AskAdvisor
from sobreplano.infrastructure.advisor.chat_models import build_chat_model
from sobreplano.infrastructure.advisor.langgraph_advisor import LangGraphAdvisor
from sobreplano.infrastructure.advisor.tools import build_tools
from sobreplano.infrastructure.db.advisor_thread_repository import SqlAdvisorThreadRepository
from sobreplano.infrastructure.db.llm_usage_repository import SqlLlmUsageRepository
from sobreplano.infrastructure.db.project_listing_query import SqlProjectListingQuery
from sobreplano.infrastructure.settings import Settings

BOGOTA = ZoneInfo("America/Bogota")


def build_ask_advisor(
    settings: Settings, session: Session, checkpointer: BaseCheckpointSaver[Any]
) -> AskAdvisor:
    """The AskAdvisor use case over session; the chat model is built on the first message."""
    agent = LangGraphAdvisor(
        chat_model=lambda: build_chat_model(settings),
        model_name=settings.advisor_model,
        tools=build_tools(SqlProjectListingQuery(session)),
        checkpointer=checkpointer,
    )
    return AskAdvisor(
        agent=agent,
        usage=SqlLlmUsageRepository(session),
        threads=SqlAdvisorThreadRepository(session),
        daily_budget_usd=settings.advisor_daily_budget_usd,
        max_turns=settings.advisor_max_turns,
    )


def today_in_bogota() -> datetime:
    """Now in America/Bogota; its date is the day the advisor budget is counted on."""
    return datetime.now(BOGOTA)
