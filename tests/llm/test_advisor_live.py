"""Optional paid test of the advisor against the real model: RUN_LLM_TESTS=1, a key and a DB."""

import os
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from sobreplano.domain.catalog import Municipality
from sobreplano.domain.listings import ProjectFilters, ProjectSort
from sobreplano.infrastructure.advisor.chat_models import build_chat_model
from sobreplano.infrastructure.advisor.langgraph_advisor import LangGraphAdvisor
from sobreplano.infrastructure.advisor.tools import build_tools
from sobreplano.infrastructure.db.engine import create_db_engine, create_session_factory
from sobreplano.infrastructure.db.project_listing_query import SqlProjectListingQuery
from sobreplano.infrastructure.settings import load_settings

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        os.environ.get("RUN_LLM_TESTS") != "1", reason="paid API call; set RUN_LLM_TESTS=1"
    ),
]


def test_sabaneta_question_searches_and_names_a_real_project() -> None:
    settings = load_settings()
    session_factory = create_session_factory(create_db_engine(settings.database_url))
    with session_factory() as session:
        query = SqlProjectListingQuery(session)
        page = query.list_projects(
            filters=ProjectFilters(municipality=Municipality.SABANETA),
            sort=ProjectSort.NAME,
            limit=50,
            offset=0,
        )
        if page.total == 0:
            pytest.skip("no Sabaneta projects in this database")
        # Memory in RAM and no use case: the test leaves nothing in the database.
        advisor = LangGraphAdvisor(
            chat_model=lambda: build_chat_model(settings),
            model_name=settings.advisor_model,
            tools=build_tools(query),
            checkpointer=InMemorySaver(),
        )
        reply = advisor.reply(uuid4(), "¿Qué proyectos hay en Sabaneta?")
        session.rollback()

    print(reply.text, reply.tools_used, reply.llm_calls, sep="\n")
    assert "search_projects" in reply.tools_used
    names = [project.name.lower() for project in page.items]
    assert any(name in reply.text.lower() for name in names)
    assert all(call.input_tokens > 0 for call in reply.llm_calls)
