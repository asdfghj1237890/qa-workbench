"""Independent single-call harness, without implicit tool execution."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from ..contracts import UnsupportedCapability
from ..runtime import HarnessResult, Message, RunLimits, ToolSpec
from .tool_loop import ToolLoopHarness


class SingleTurnHarness(ToolLoopHarness):
    def describe(self) -> dict[str, Any]:
        return dict(super().describe(), settings={"max_turns": 1, "tools": "unsupported",
                    "cancellation": "bounded_wait_and_no_further_dispatch"})

    def run(self, messages: Sequence[Message], *, tools: Sequence[ToolSpec] = (),
            handlers: Mapping[str, Callable[[Mapping[str, Any]], Any]] | None = None,
            limits: RunLimits | None = None, cancel: threading.Event | None = None) -> HarnessResult:
        if tools or handlers:
            raise UnsupportedCapability("SingleTurnHarness does not execute tools")
        return super().run(messages, limits=replace(limits or RunLimits(), max_turns=1), cancel=cancel)
