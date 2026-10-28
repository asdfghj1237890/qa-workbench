"""FastAPI host for the portable adapter contract; authentication is injected."""
from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .contracts import RunRequest
from .demo import DemoAdapter
from .logs import PAGE_BYTES
from .service import WorkbenchService, detached


class StartBody(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    task_id: Annotated[str, Field(min_length=1, max_length=100)]
    options: dict = Field(default_factory=dict)
    acknowledge_cost: StrictBool = False
    max_usd: Annotated[float, Field(strict=True, gt=0)] | None = None


class RowReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    verdict: Literal["passed", "failed"]
    reason: Annotated[str, Field(min_length=1, max_length=4000)]


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    reviewer: Annotated[str, Field(min_length=1, max_length=200)]
    reason: Annotated[str, Field(min_length=1, max_length=4000)]
    verdict: Literal["passed", "failed"]
    rows: list[RowReview] = Field(default_factory=list, max_length=10000)


class PrivateInputRoute(APIRoute):
    """Bound bytes before decoding; validation errors never echo credentials."""
    def get_route_handler(self):
        original = super().get_route_handler()
        async def guarded(request):
            try:
                if request.method in {"POST", "PUT", "PATCH"}:
                    maximum = (20 * 1024 * 1024 if request.url.path.endswith("/import")
                               else 1024 * 1024 if request.url.path.endswith("/review") else 96 * 1024)
                    raw = bytearray()
                    async for chunk in request.stream():
                        raw.extend(chunk)
                        if len(raw) > maximum:
                            raise HTTPException(413, "request_body_too_large")
                    request._body = bytes(raw)
                response = await original(request)
            except RequestValidationError:
                response = JSONResponse(status_code=422, content={"detail": "invalid_workbench_request"})
            except HTTPException as error:
                response = JSONResponse(status_code=error.status_code, content={"detail": error.detail},
                                        headers=error.headers)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        return guarded


def create_router(service, authenticate, *, prefix="/api"):
    router = APIRouter(prefix=prefix, route_class=PrivateInputRoute)

    async def owner(request: Request):
        identity = authenticate(request)
        if inspect.isawaitable(identity):
            identity = await identity
        if not isinstance(identity, str) or not identity or len(identity) > 512:
            raise HTTPException(401, "authentication_required")
        return identity

    owner_dependency = Depends(owner)

    @router.get("/projects")
    async def projects(identity=owner_dependency):
        return {"projects": [service.capabilities()["project"]]}

    @router.get("/capabilities")
    @router.get("/tasks")
    async def capabilities(identity=owner_dependency):
        return service.capabilities()

    @router.get("/runs")
    async def runs(identity=owner_dependency):
        return service.recent(identity)

    @router.post("/runs", status_code=202)
    async def start(body: StartBody, identity=owner_dependency):
        return await service.start(identity, RunRequest(**body.model_dump()))

    @router.post("/runs/import", status_code=201)
    async def import_run(body: dict, identity=owner_dependency):
        return service.import_run(identity, body)

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str, identity=owner_dependency):
        return service.get(run_id, identity)

    @router.post("/runs/{run_id}/cancel")
    async def cancel(run_id: str, identity=owner_dependency):
        return await service.cancel(run_id, identity)

    @router.get("/runs/{run_id}/report")
    async def report(run_id: str, identity=owner_dependency):
        return service.report(run_id, identity)

    @router.get("/runs/{run_id}/logs")
    async def logs(run_id: str, identity=owner_dependency,
                   offset: Annotated[int, Query(ge=0)] = 0,
                   limit: Annotated[int, Query(ge=4, le=PAGE_BYTES)] = PAGE_BYTES,
                   step: Annotated[str | None, Query(max_length=200)] = None,
                   download: bool = False):
        return service.log_page(run_id, identity, offset, limit, step, download)

    @router.post("/runs/{run_id}/review")
    async def review(run_id: str, body: ReviewBody, identity=owner_dependency):
        return service.review(run_id, identity, body.model_dump())

    @router.get("/health")
    async def health(identity=owner_dependency):
        return detached(await service.adapter.health())

    return router


def create_app(adapter=None, *, archive_root=".qa-workbench/data", authenticate=None,
               allow_unauthenticated=False, frontend_dir=None, **service_options):
    is_demo = adapter is None
    adapter = adapter or DemoAdapter()
    if authenticate is None:
        if not is_demo and not allow_unauthenticated:
            raise ValueError("custom_adapter_requires_authentication")
        authenticate = lambda request: "local-demo"
    service = WorkbenchService(adapter, archive_root, **service_options)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await service.close()

    app = FastAPI(title="QA Workbench", lifespan=lifespan)
    app.state.workbench = service
    app.include_router(create_router(service, authenticate))

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    if frontend_dir is not None:
        from fastapi.staticfiles import StaticFiles
        folder = Path(frontend_dir).resolve()
        if not (folder / "index.html").is_file():
            raise ValueError("frontend_build_missing")
        app.mount("/", StaticFiles(directory=folder, html=True), name="workbench-ui")
    return app
