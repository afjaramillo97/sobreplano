"""Langfuse tracing of the advisor: off without keys, and never a reason for a turn to fail."""

from collections.abc import Generator
from contextlib import contextmanager
from functools import cache

from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from sobreplano.infrastructure.settings import Settings


def tracing_enabled(settings: Settings) -> bool:
    """Whether both Langfuse keys are set."""
    return bool(
        settings.langfuse_public_key
        and settings.langfuse_secret_key
        and settings.langfuse_secret_key.get_secret_value()
    )


@cache
def _client(public_key: str, secret_key: str, base_url: str) -> Langfuse:
    # One client per process: it batches and exports spans in the background.
    return Langfuse(public_key=public_key, secret_key=secret_key, base_url=base_url)


def langfuse_client(settings: Settings) -> Langfuse | None:
    """The process' Langfuse client, or None when tracing is off."""
    if not tracing_enabled(settings):
        return None
    assert settings.langfuse_public_key is not None and settings.langfuse_secret_key is not None
    return _client(
        settings.langfuse_public_key,
        settings.langfuse_secret_key.get_secret_value(),
        settings.langfuse_base_url,
    )


def langfuse_callbacks(settings: Settings) -> list[BaseCallbackHandler]:
    """[CallbackHandler()] when tracing is on, else []; the handler sends LangChain runs."""
    client = langfuse_client(settings)
    if client is None:
        return []
    return [CallbackHandler(public_key=settings.langfuse_public_key)]


def flush_tracing(settings: Settings) -> None:
    """Send pending traces now; call it before the process exits."""
    client = langfuse_client(settings)
    if client is not None:
        client.flush()


def shutdown_tracing(settings: Settings) -> None:
    """Flush and stop the background exporter; the client must not be used afterwards."""
    client = langfuse_client(settings)
    if client is not None:
        client.shutdown()


@contextmanager
def traced_span(
    settings: Settings,
    name: str,
    *,
    input: object = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
) -> Generator[str | None]:
    """Run the block inside a Langfuse span and yield its trace id (None when tracing is off).

    LangChain runs started inside the block, with langfuse_callbacks, nest under this span;
    session_id and tags are set on the whole trace.
    """
    client = langfuse_client(settings)
    if client is None:
        yield None
        return
    with (
        client.start_as_current_observation(name=name, input=input),
        propagate_attributes(session_id=session_id, tags=tags),
    ):
        yield client.get_current_trace_id()


def score_trace(
    settings: Settings, trace_id: str | None, name: str, passed: bool, comment: str = ""
) -> None:
    """Attach a boolean score to a trace; does nothing when tracing is off."""
    client = langfuse_client(settings)
    if client is None or trace_id is None:
        return
    client.create_score(
        trace_id=trace_id,
        name=name,
        value=1 if passed else 0,
        data_type="BOOLEAN",
        comment=comment or None,
    )
