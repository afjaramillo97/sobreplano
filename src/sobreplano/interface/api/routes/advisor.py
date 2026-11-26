"""POST /advisor/chat and /advisor/chat/stream: one message to the advisor, as JSON or SSE."""

import logging
import queue
import threading
import time
from collections.abc import Callable, Iterator
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, StringConstraints

from sobreplano.domain.advisor import AdvisorStep
from sobreplano.domain.errors import (
    AdvisorBudgetExceededError,
    AdvisorLimitError,
    AdvisorThreadNotFoundError,
    AdvisorTurnLimitError,
    AdvisorUnavailableError,
)
from sobreplano.interface.advisor_composition import today_in_bogota
from sobreplano.interface.api.dependencies import (
    AdvisorOpener,
    AdvisorOpenerDep,
    AskAdvisorDep,
    SessionDep,
)
from sobreplano.interface.api.rate_limit import AdvisorRateLimitDep

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 1000
# The stream gives up on a turn that has not ended by then and sends an `error`. The turn
# goes on in its thread and is still recorded; each model call has its own timeout too.
TURN_TIMEOUT_SECONDS = 60.0

# Status and detail of each advisor error, the same in the JSON answer and the SSE event.
ADVISOR_ERRORS: dict[type[Exception], tuple[int, str]] = {
    AdvisorThreadNotFoundError: (404, "conversation not found"),
    AdvisorTurnLimitError: (409, "conversation limit reached"),
    AdvisorBudgetExceededError: (503, "advisor budget exhausted for today"),
    AdvisorUnavailableError: (503, "advisor unavailable"),
    AdvisorLimitError: (503, "advisor could not answer"),
}
KNOWN_ERRORS = tuple(ADVISOR_ERRORS)
UNAVAILABLE = ADVISOR_ERRORS[AdvisorUnavailableError]

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
    projects: list[str]  # slugs of the projects the reply names, in order, at most 6


class StepOut(BaseModel):
    """Data of a `step` event: one tool of the turn started or ended."""

    tool: str
    phase: Literal["start", "end"]


class StreamAnswerOut(ChatOut):
    """Data of the `answer` event, the last one of a stream that went well."""

    remaining_today: int | None  # advisor messages the client has left today; None if unlimited


class StreamErrorOut(BaseModel):
    """Data of the `error` event: the turn failed after the stream opened."""

    status: int
    detail: str


def _http_error(error: Exception) -> HTTPException:
    status, detail = _status_and_detail(error)
    return HTTPException(status_code=status, detail=detail)


def _status_and_detail(error: Exception) -> tuple[int, str]:
    for kind, answer in ADVISOR_ERRORS.items():
        if isinstance(error, kind):
            return answer
    return UNAVAILABLE


@router.post("/advisor/chat")
def chat(
    _rate_limit: AdvisorRateLimitDep, body: ChatIn, ask: AskAdvisorDep, session: SessionDep
) -> ChatOut:
    """Answer one message with Sobreplano's data.

    Commits the conversation and the token log, also before the 503 for too many tool
    rounds, so the spend is not lost.
    """
    try:
        answer = ask(body.thread_id, body.message, today_in_bogota().date())
    except AdvisorLimitError as error:
        session.commit()
        raise _http_error(error) from error
    except KNOWN_ERRORS as error:
        raise _http_error(error) from error
    session.commit()
    return ChatOut(
        thread_id=answer.thread_id,
        reply=answer.reply.text,
        tools_used=answer.reply.tools_used,
        projects=answer.reply.projects,
    )


def check_advisor_turn(body: ChatIn, open_advisor: AdvisorOpenerDep) -> ChatIn:
    """The message, once the budget and its conversation allow an answer now.

    A dependency, so its refusals leave as HTTP codes: an HTTPException raised inside the
    stream would reach the client after the 200. Writes nothing.

    Raises:
        HTTPException: 404, 409 or 503 (budget), with the details of POST /advisor/chat.
    """
    with open_advisor() as (ask, _):
        try:
            ask.check(body.thread_id, today_in_bogota().date())
        except KNOWN_ERRORS as error:
            raise _http_error(error) from error
    return body


AdvisorTurnCheckDep = Annotated[ChatIn, Depends(check_advisor_turn)]


@router.post("/advisor/chat/stream", response_class=EventSourceResponse)
def chat_stream(
    remaining: AdvisorRateLimitDep, body: AdvisorTurnCheckDep, open_advisor: AdvisorOpenerDep
) -> Iterator[ServerSentEvent]:
    """Answer one message as Server-Sent Events, telling each tool as it starts and ends.

    Events: `step` (StepOut) when a tool starts or ends, then one `answer` (StreamAnswerOut)
    or one `error` (StreamErrorOut). The answer is the verified text, never partial text.
    What is known before the turn (422, 429, 404, 409, 503) is a plain HTTP answer, as in
    POST /advisor/chat.

    The turn runs in a thread with its own session and commits the conversation and the
    token log, also after too many tool rounds. If the client goes away or the stream
    times out, the turn still ends and is recorded.
    """
    events: queue.Queue[ServerSentEvent | None] = queue.Queue()
    today = today_in_bogota().date()
    remaining_today = remaining.day if remaining is not None else None

    def run() -> None:
        try:
            events.put(_run_turn(open_advisor, body, today, events.put, remaining_today))
        finally:
            events.put(None)  # end of the stream

    # Not a daemon: a shutdown waits for the turn, so its spend is committed.
    threading.Thread(target=run, name="advisor-turn").start()
    deadline = time.monotonic() + TURN_TIMEOUT_SECONDS
    while True:
        try:
            event = events.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            logger.error("advisor turn still running after %s s", TURN_TIMEOUT_SECONDS)
            status, detail = ADVISOR_ERRORS[AdvisorLimitError]
            yield _event("error", StreamErrorOut(status=status, detail=detail))
            return
        if event is None:
            return
        yield event


def _run_turn(
    open_advisor: AdvisorOpener,
    body: ChatIn,
    today: date,
    put: Callable[[ServerSentEvent], None],
    remaining_today: int | None,
) -> ServerSentEvent:
    """Run one turn, putting a `step` event per tool start and end; return the last event."""

    def on_step(step: AdvisorStep) -> None:
        put(_event("step", StepOut(tool=step.tool, phase=step.phase)))

    try:
        with open_advisor() as (ask, session):
            try:
                answer = ask(body.thread_id, body.message, today, on_step)
            except AdvisorLimitError:
                session.commit()
                raise
            session.commit()
    except KNOWN_ERRORS as error:
        status, detail = _status_and_detail(error)
        return _event("error", StreamErrorOut(status=status, detail=detail))
    except Exception:
        # The stream is already a 200: an error event is the only way to tell the client.
        logger.exception("advisor stream turn failed")
        status, detail = UNAVAILABLE
        return _event("error", StreamErrorOut(status=status, detail=detail))
    return _event(
        "answer",
        StreamAnswerOut(
            thread_id=answer.thread_id,
            reply=answer.reply.text,
            tools_used=answer.reply.tools_used,
            projects=answer.reply.projects,
            remaining_today=remaining_today,
        ),
    )


def _event(name: str, data: BaseModel) -> ServerSentEvent:
    return ServerSentEvent(event=name, data=data)
