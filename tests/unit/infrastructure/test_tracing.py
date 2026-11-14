"""Unit tests for Langfuse tracing: off without keys, so nothing is sent and nothing fails."""

from typing import Any

import pytest
from pydantic import SecretStr

from sobreplano.infrastructure.advisor.tracing import (
    flush_tracing,
    langfuse_callbacks,
    langfuse_client,
    score_trace,
    shutdown_tracing,
    traced_span,
    tracing_enabled,
)
from sobreplano.infrastructure.settings import Settings


def settings(**overrides: Any) -> Settings:
    return Settings(database_url="postgresql+psycopg://x", **overrides)


@pytest.mark.parametrize(
    "keys",
    [
        {},
        {"langfuse_public_key": "pk-lf-test"},
        {"langfuse_secret_key": SecretStr("sk-lf-test")},
        {"langfuse_public_key": "pk-lf-test", "langfuse_secret_key": SecretStr("")},
    ],
)
def test_without_both_keys_there_are_no_callbacks(keys: dict[str, Any]) -> None:
    off = settings(**keys)
    assert not tracing_enabled(off)
    assert langfuse_callbacks(off) == []
    assert langfuse_client(off) is None


def test_without_keys_spans_scores_and_flush_do_nothing() -> None:
    off = settings()
    with traced_span(off, "eval S1 r1 t1", input="Hola", session_id="t", tags=["eval"]) as trace_id:
        assert trace_id is None
    score_trace(off, "trace", "check.grounded", True)
    flush_tracing(off)
    shutdown_tracing(off)


def test_both_keys_enable_tracing() -> None:
    on = settings(langfuse_public_key="pk-lf-test", langfuse_secret_key=SecretStr("sk-lf-test"))
    assert tracing_enabled(on)
    assert on.langfuse_base_url == "https://us.cloud.langfuse.com"
