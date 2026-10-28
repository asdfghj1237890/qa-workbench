"""Serializable project ports. The platform never imports a system under test."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ProjectDescriptor:
    id: str
    name: str
    source_sha: str | None = None
    description: str = ""


@dataclass(frozen=True)
class TaskDefinition:
    id: str
    title: str
    description: str = ""
    paid: bool = False
    requires_review: bool = True
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    max_budget_usd: float | None = None
    review_rows_key: str | None = "rows"


@dataclass(frozen=True)
class RunRequest:
    task_id: str
    options: Mapping[str, Any] = field(default_factory=dict)
    acknowledge_cost: bool = False
    max_usd: float | None = None


@dataclass(frozen=True)
class RunResult:
    report: Mapping[str, Any]
    status: str = "completed"
    structural_status: str = "not_run"
    evidence_kind: str = "observed"
    gaps: Sequence[str] = ()


@dataclass
class ExecutionContext:
    owner: str
    run_id: str
    source_sha: str | None
    cancellation: asyncio.Event
    emit: Callable[[str | None, str], None]
    progress: Callable[[Mapping[str, Any]], None]

    @property
    def cancelled(self) -> bool:
        return self.cancellation.is_set()


class ProjectAdapter(Protocol):
    """Implement business tasks here; auth and storage are separate host ports."""
    project: ProjectDescriptor

    def tasks(self) -> Sequence[TaskDefinition]: ...
    async def execute(self, request: RunRequest, context: ExecutionContext) -> RunResult: ...
    async def health(self) -> Mapping[str, Any]: ...
