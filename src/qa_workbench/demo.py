"""A synthetic second system: no NewsCout, provider, database or repository paths."""
from __future__ import annotations

import asyncio

from .contracts import ProjectDescriptor, RunResult, TaskDefinition


class DemoAdapter:
    project = ProjectDescriptor("example-system", "Example system", description="Offline adapter demonstration")

    def tasks(self):
        return [TaskDefinition("contract-check", "Run example contract checks",
                               "Checks a deterministic document round trip. Synthetic evidence only.",
                               input_schema={"type": "object", "properties": {"message": {"type": "string"}},
                                             "additionalProperties": False})]

    async def execute(self, request, context):
        if set(request.options) - {"message"} or not isinstance(request.options.get("message", "hello"), str):
            raise ValueError("invalid_demo_options")
        context.emit("contract", "Starting synthetic contract checks\n")
        await asyncio.sleep(0)
        if context.cancelled:
            return RunResult({}, status="cancelled", evidence_kind="synthetic")
        message = request.options.get("message", "hello")
        row = {"case_id": "document-round-trip", "input": message, "observed": message,
               "structural_pass": True, "evidence_kind": "synthetic"}
        context.emit("contract", "Document round trip completed\n")
        return RunResult({"rows": [row], "structural": {"passed": 1, "failed": 0},
                          "semantic_acceptance": "not_evaluated"},
                         structural_status="passed", evidence_kind="synthetic",
                         gaps=["live_system_not_evaluated"])

    async def health(self):
        return {"project_id": self.project.id, "status": "available", "evidence_kind": "synthetic",
                "checks": [{"id": "demo", "status": "available"}]}
