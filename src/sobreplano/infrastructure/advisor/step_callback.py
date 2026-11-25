"""LangChain callback that tells the caller when each tool of a turn starts and ends."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from sobreplano.domain.advisor import AdvisorStep


class StepCallback(BaseCallbackHandler):
    """Calls on_step with a start and an end for every tool run, also when the tool fails.

    LangChain catches and logs what a handler raises, so a failing on_step never stops
    the turn.
    """

    def __init__(self, on_step: Callable[[AdvisorStep], None]) -> None:
        super().__init__()
        self._on_step = on_step
        # on_tool_end and on_tool_error do not carry the tool's name, only its run id.
        self._names: dict[UUID, str] = {}

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Report the tool as started."""
        name = str(serialized.get("name") or kwargs.get("name") or "")
        self._names[run_id] = name
        self._on_step(AdvisorStep(tool=name, phase="start"))

    def on_tool_end(
        self, output: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any
    ) -> None:
        """Report the tool as ended; tool errors the tool handles itself also end here."""
        self._end(run_id)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Report the tool as ended, so the live progress never stays on a failed tool."""
        self._end(run_id)

    def _end(self, run_id: UUID) -> None:
        name = self._names.pop(run_id, None)
        if name is not None:
            self._on_step(AdvisorStep(tool=name, phase="end"))
