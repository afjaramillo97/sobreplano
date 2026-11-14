"""Chat with the advisor in the terminal: python -m sobreplano.interface.cli.advise."""

import argparse
import logging
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from pydantic import ValidationError

from sobreplano.domain.advisor import AdvisorAnswer
from sobreplano.domain.errors import (
    AdvisorBudgetExceededError,
    AdvisorLimitError,
    AdvisorThreadNotFoundError,
    AdvisorTurnLimitError,
    AdvisorUnavailableError,
)
from sobreplano.infrastructure.advisor.checkpointer import open_checkpointer
from sobreplano.infrastructure.advisor.tracing import shutdown_tracing
from sobreplano.infrastructure.db.engine import create_db_engine, create_session_factory
from sobreplano.infrastructure.settings import load_settings
from sobreplano.interface.advisor_composition import build_ask_advisor, today_in_bogota

EXIT_WORDS = {"exit", "quit", "salir"}


def format_answer(answer: AdvisorAnswer) -> str:
    """The reply followed by one line with the tools, tokens and cost of the turn."""
    calls = answer.reply.llm_calls
    tokens_in = sum(call.input_tokens for call in calls)
    tokens_out = sum(call.output_tokens for call in calls)
    cost = sum((call.cost_usd or Decimal(0) for call in calls), Decimal(0))
    tools = ", ".join(answer.reply.tools_used) or "none"
    return (
        f"{answer.reply.text}\n"
        f"  [tools: {tools} | {len(calls)} LLM calls, {tokens_in} in / {tokens_out} out, "
        f"{cost} USD]"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Read messages until an empty line, 'salir' or Ctrl-D; exits 2 on bad configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread", type=UUID, default=None, help="continue this conversation")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    try:
        settings = load_settings()
    except ValidationError as error:
        print(f"bad configuration: {error}")
        return 2
    session_factory = create_session_factory(create_db_engine(settings.database_url))
    thread_id: UUID | None = args.thread
    print(f"Sobreplano advisor ({settings.advisor_model}). Empty line or 'salir' to quit.")

    with open_checkpointer(settings.database_url) as checkpointer:
        while True:
            try:
                message = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not message or message.lower() in EXIT_WORDS:
                break
            # One session per message, as the API opens one per request.
            with session_factory() as session:
                ask = build_ask_advisor(settings, session, checkpointer, source="cli")
                try:
                    answer = ask(thread_id, message, today_in_bogota().date())
                except AdvisorLimitError:
                    session.commit()  # keep the spend, as the API does
                    print("The advisor could not answer (too many tool rounds).")
                    continue
                except AdvisorUnavailableError as error:
                    print(f"Advisor unavailable: {error}")
                    continue
                except (
                    AdvisorBudgetExceededError,
                    AdvisorThreadNotFoundError,
                    AdvisorTurnLimitError,
                ) as error:
                    # None of these clears up by asking again in this session.
                    print(f"{type(error).__name__}: {error}")
                    break
                session.commit()
            thread_id = answer.thread_id
            print(format_answer(answer))

    # Pending traces would be lost when the process exits.
    shutdown_tracing(settings)
    if thread_id is not None:
        print(f"\nthread_id: {thread_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
