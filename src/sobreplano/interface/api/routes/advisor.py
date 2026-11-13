"""POST /advisor/chat: one message to the advisor, in a new or an existing conversation."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StringConstraints

from sobreplano.domain.errors import (
    AdvisorBudgetExceededError,
    AdvisorLimitError,
    AdvisorThreadNotFoundError,
    AdvisorTurnLimitError,
    AdvisorUnavailableError,
)
from sobreplano.interface.advisor_composition import today_in_bogota
from sobreplano.interface.api.dependencies import AskAdvisorDep, SessionDep

MAX_MESSAGE_LENGTH = 1000

router = APIRouter(tags=["advisor"])


class ChatIn(BaseModel):
    """A user message; without thread_id it starts a new conversation."""

    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_LENGTH)
    ]
    thread_id: UUID | None = None


class ChatOut(BaseModel):
    """The advisor's answer and the conversation to continue it in."""

    thread_id: UUID
    reply: str
    tools_used: list[str]


@router.post("/advisor/chat")
def chat(body: ChatIn, ask: AskAdvisorDep, session: SessionDep) -> ChatOut:
    """Answer one message with Sobreplano's data.

    The only route that writes: it commits the conversation and the token log, also before
    the 503 for too many tool rounds, so the spend is not lost.
    """
    try:
        answer = ask(body.thread_id, body.message, today_in_bogota().date())
    except AdvisorThreadNotFoundError as error:
        raise HTTPException(status_code=404, detail="conversation not found") from error
    except AdvisorTurnLimitError as error:
        raise HTTPException(status_code=409, detail="conversation limit reached") from error
    except AdvisorBudgetExceededError as error:
        raise HTTPException(status_code=503, detail="advisor budget exhausted for today") from error
    except AdvisorUnavailableError as error:
        raise HTTPException(status_code=503, detail="advisor unavailable") from error
    except AdvisorLimitError as error:
        session.commit()
        raise HTTPException(status_code=503, detail="advisor could not answer") from error
    session.commit()
    return ChatOut(
        thread_id=answer.thread_id, reply=answer.reply.text, tools_used=answer.reply.tools_used
    )
