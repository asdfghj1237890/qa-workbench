"""Explicit synthetic replay: useful for reproducibility, never live-model proof."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from ..contracts import Capabilities, ContractError
from ..runtime import (
    Generation,
    ImageBlock,
    Message,
    RunLimits,
    RuntimeFailure,
    ToolSpec,
    Usage,
)


class ReplayModel:
    capabilities = Capabilities(frozenset({"text", "tools", "replay"}))

    def __init__(self, generations: Sequence[Generation | str], *, name: str = "synthetic-replay"):
        if not generations:
            raise ContractError("replay requires at least one explicit generation")
        self._generations = tuple(Generation(item) if isinstance(item, str) else item for item in generations)
        if not all(isinstance(item, Generation) for item in self._generations):
            raise ContractError("replay accepts text or Generation only")
        self._cursor = 0
        self._lock = threading.Lock()
        self.name = name

    def describe(self) -> dict[str, Any]:
        payload = json.dumps([asdict(item) for item in self._generations], sort_keys=True, ensure_ascii=False)
        return {"adapter": "ReplayModel", "adapter_version": 1, "provider": "replay", "model": self.name,
                "evidence_kind": "synthetic_replay", "synthetic": True, "settings": {},
                "replay_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "capabilities": sorted(self.capabilities.features)}

    def estimate_cost(self, limits: RunLimits) -> float:
        return 0.0

    def generate(self, messages: Sequence[Message], *, tools: Sequence[ToolSpec] = (),
                 limits: RunLimits | None = None, cancel: threading.Event | None = None) -> Generation:
        if cancel is not None and cancel.is_set():
            raise RuntimeFailure("cancelled")
        if any(isinstance(block, ImageBlock) for message in messages if not isinstance(message.content, str) for block in message.content):
            self.capabilities.require("image_input")
        with self._lock:
            if self._cursor >= len(self._generations):
                raise RuntimeFailure("replay_exhausted")
            item = self._generations[self._cursor]
            self._cursor += 1
        # Replay execution is free; original token counts remain unknown unless
        # explicitly recorded. A historical provider cost stays in raw evidence.
        usage = Usage(item.usage.input_tokens, item.usage.output_tokens, 0.0,
                      dict(item.usage.details, api_requests=1, evidence_kind="synthetic_replay",
                           recorded_provider_cost_usd=item.usage.cost_usd))
        return Generation(item.text, item.tool_calls, item.finish_reason, usage,
                          dict(item.raw, evidence_kind="synthetic_replay"), "replay", self.name)
