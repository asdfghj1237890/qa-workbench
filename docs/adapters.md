# Connect another system

Implement the `qa_workbench.contracts.ProjectAdapter` protocol in your own package.
Use `ProjectDescriptor` to identify the project and optional full source commit;
return `TaskDefinition` values from `tasks()`. Each task declares an input JSON
schema, whether it can incur charges, a budget ceiling, and its review requirement.
Schemas use local references only. Task discovery is read-only.

`execute(request, context)` performs the business operation and returns `RunResult`.
Use `context.emit(step, text)` for bounded sanitized logs and `context.progress`
for detached progress. Observe `context.cancelled`; propagate cancellation to real
child processes and remote operations. Store provider credentials in the host's
private runtime, not task schemas, reports or manifest files.

```python
from qa_workbench.contracts import ProjectDescriptor, RunResult, TaskDefinition

class InventoryAdapter:
    project = ProjectDescriptor("inventory", "Inventory QA")

    def tasks(self):
        return [TaskDefinition("stock-contract", "Stock API contract",
            input_schema={"type": "object", "additionalProperties": False},
            requires_review=False)]

    async def execute(self, request, context):
        # Call your real test/adapter here; measure its behavior and preserve
        # per-case evidence. This illustrative result makes no quality claim.
        context.emit("contract", "Inventory integration is not configured.\n")
        return RunResult({"rows": [], "reason": "integration_not_configured"},
            status="incomplete", structural_status="not_run",
            gaps=("integration_not_configured",))

    async def health(self):
        return {"project_id": self.project.id, "status": "unmeasured"}

def create_adapter():
    return InventoryAdapter()
```

Install your adapter package, set an access token in an environment variable, then
run `qa-workbench --adapter inventory_qa:create_adapter --token-env QA_ACCESS_TOKEN`.
The standalone UI prompts for this token when authentication is required and keeps
it only in memory. For SSO, inject an authenticated frontend request provider.
The CLI accepts an explicitly installed `module:factory`; manifests do not execute
arbitrary import paths. For SSO or multi-user ownership, embed `create_app(adapter,
authenticate=...)` or mount `create_router(service, authenticate)` in your host.
The auth callback returns the authenticated owner ID and may be asynchronous.

The standalone frontend reads `/api/capabilities` and renders arbitrary task
descriptors. An embedded frontend may provide an authenticated client and a
different API base. NewsCout demonstrates this with its `/qa/workbench` API and
Firebase-backed frontend adapter; the core does not depend on Firebase.

Use `templates/python-project` for the strict test architecture. Keep business
scenarios in scripts, compose public actions, and implement I/O and mock wiring in
physical adapters. Bind observation dataclasses to your own contracts namespace.
Changing a backend implementation can preserve a scenario; changing the business
domain usually requires new scripts and action vocabulary too.

The [cart project template](../templates/python-project/README.md) is a complete
second-system example: install its adapter and execute its own layered pytest
scenarios through the workbench, with measured JUnit results and bounded cleanup.
