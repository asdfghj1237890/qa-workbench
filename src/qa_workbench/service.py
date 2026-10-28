"""Owner-isolated explicit execution, immutable reports and restart evidence.

The archive and sanitized capture primitives are extracted from the original
workbench. Adapters own task side effects; reading any endpoint never runs one.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .archive import ArchiveStore
from .contracts import ExecutionContext, ProjectAdapter, RunRequest, RunResult
from .logs import PAGE_BYTES, RunLog

TERMINAL = {"completed", "failed", "cancelled", "interrupted", "incomplete", "timed_out"}
IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")
STORAGE_ERRORS = (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError)


def timestamp():
    return datetime.now(UTC).isoformat()


def detached(value):
    """Reject live objects, nonfinite values and oversized payloads at the port."""
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(raw.encode()) > 16 * 1024 * 1024:
        raise ValueError("oversized_evidence")
    return json.loads(raw)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def checked_schema(schema):
    """Task definitions are local contracts; validation must not fetch a URL."""
    schema = detached(dict(schema))
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"$ref", "$dynamicRef"} and (not isinstance(child, str) or not child.startswith("#")):
                    raise ValueError("external_schema_references_not_supported")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(schema)
    Draft202012Validator.check_schema(schema)
    return schema


def _request_secrets(options):
    values = []
    if isinstance(options, dict):
        for key, value in options.items():
            if re.search(r"key|secret|password|token|credential|authorization|cookie", key, re.IGNORECASE) and isinstance(value, str):
                values.append(value)
            values.extend(_request_secrets(value))
    elif isinstance(options, list):
        for value in options:
            values.extend(_request_secrets(value))
    return values


class ExecutionStore(ArchiveStore):
    max_bytes = 64 * 1024 * 1024


class WorkbenchService:
    def __init__(self, adapter: ProjectAdapter, archive_root: str | Path, *,
                 history_limit=20, timeout_seconds=900, cancellation_grace_seconds=2,
                 store_factory=ExecutionStore):
        self.adapter = adapter
        self.project = asdict(adapter.project)
        if not IDENTIFIER.fullmatch(self.project["id"]):
            raise ValueError("invalid_project_id")
        if self.project["source_sha"] is not None and (not isinstance(self.project["source_sha"], str)
                or not re.fullmatch(r"[0-9a-fA-F]{40}", self.project["source_sha"])):
            raise ValueError("source_sha_must_be_full_commit_hash")
        self.definitions = list(adapter.tasks())
        ids = [task.id for task in self.definitions]
        if len(ids) != len(set(ids)) or not ids or any(not IDENTIFIER.fullmatch(i) for i in ids):
            raise ValueError("invalid_task_definitions")
        self.tasks = {task.id: task for task in self.definitions}
        for task in self.definitions:
            if task.review_rows_key is not None and (not isinstance(task.review_rows_key, str)
                    or not IDENTIFIER.fullmatch(task.review_rows_key)):
                raise ValueError("invalid_review_rows_key")
            try:
                checked_schema(task.input_schema)
            except SchemaError as exc:
                raise ValueError("invalid_task_input_schema") from exc
            budget = task.max_budget_usd
            if task.paid and (budget is None or type(budget) not in (int, float)
                              or not math.isfinite(budget) or budget <= 0):
                raise ValueError("paid_task_requires_budget_ceiling")
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValueError("invalid_history_limit")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("invalid_timeout")
        self.store = store_factory(Path(archive_root) / self.project["id"])
        self.limit, self.timeout, self.grace = history_limit, timeout_seconds, cancellation_grace_seconds
        self.jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.logs: dict[str, RunLog] = {}
        self.reports: dict[str, dict[str, Any]] = {}
        self.reviews: dict[str, dict[str, Any]] = {}
        self.workers: dict[str, asyncio.Task[None]] = {}
        self.cancellations: dict[str, asyncio.Event] = {}
        self.checkpointed: dict[str, float] = {}
        self.lock = asyncio.Lock()
        self.active_id: str | None = None
        self.closed = False

    def capabilities(self):
        return detached({"project": self.project, "source_sha": self.project["source_sha"],
                         "tasks": [asdict(task) for task in self.definitions],
                         "execution": {"explicit_start": True, "paid_consent_required": True,
                                       "timeout_seconds": self.timeout}})

    @staticmethod
    def _public(job):
        return detached({key: value for key, value in job.items() if key != "owner"})

    def _save(self, job, *, strict=False, force=True):
        if not force and time.monotonic() - self.checkpointed.get(job["id"], -10) < 2:
            return
        try:
            log = self.logs.get(job["id"])
            # Outer timestamp is an archive ordering field; the preserved job in
            # report retains its true unfinished timestamp throughout execution.
            payload = {"owner": job["owner"],
                       "job": {"id": job["id"], "finished_at": job["finished_at"] or job["created_at"]},
                       "report": self._public(job), "review": self.reviews.get(job["id"], {}),
                       "state": {"project": self.project["id"], "report": self.reports.get(job["id"]),
                                 "log": log.snapshot() if log else None}}
            self.store.save(job["owner"], job["id"], payload, self.limit)
            job.pop("archive_error", None)
            self.checkpointed[job["id"]] = time.monotonic()
        except STORAGE_ERRORS:
            job["archive_error"] = "execution_archive_unavailable"
            if strict:
                raise HTTPException(503, "execution_archive_unavailable") from None

    def _restore(self, payload, owner):
        job, state = detached(payload["report"]), payload["state"]
        if (payload["owner"] != owner or state.get("project") != self.project["id"]
                or job.get("id") != payload["job"]["id"] or "owner" in job
                or job.get("status") not in TERMINAL | {"queued", "running"}
                or job.get("project_id") != self.project["id"]
                or job.get("task_id") not in self.tasks
                or not isinstance(job.get("created_at"), str)
                or not isinstance(job.get("gaps"), list)):
            raise ValueError("invalid_execution_archive")
        report = state.get("report")
        if report is not None and digest(report) != job.get("report_sha256"):
            raise ValueError("report_hash_mismatch")
        job["owner"] = owner
        run_id = job["id"]
        review = detached(payload["review"])
        if review:
            try:
                self._checked_review(job, report, review)
            except (HTTPException, TypeError):
                raise ValueError("invalid_archived_review") from None
        job["semantic_status"] = "reviewed" if review else "pending_review"
        job["quality_passed"] = self._quality_passed(job, review)
        log = RunLog.restore(state["log"]) if state.get("log") is not None else RunLog()
        self.jobs[run_id], self.logs[run_id], self.reviews[run_id] = job, log, review
        if report is not None:
            self.reports[run_id] = detached(report)
        if job["status"] not in TERMINAL:
            job.update(status="interrupted", finished_at=timestamp(), error="execution_interrupted",
                       quality_passed=False, semantic_status="pending_review")
            log.mark_loss("execution_interrupted")
            log.finish()
            try:
                self._save(job, strict=True)
            except HTTPException:
                self.jobs.pop(run_id, None)
                self.reports.pop(run_id, None)
                self.reviews.pop(run_id, None)
                self.logs.pop(run_id).close()
                raise
        self._trim()
        return job

    def _owned(self, run_id, owner):
        job = self.jobs.get(run_id)
        if job is None and re.fullmatch(r"[0-9a-f]{32}", run_id):
            try:
                payload = self.store.load(owner, run_id)
                if payload:
                    job = self._restore(payload, owner)
            except STORAGE_ERRORS:
                raise HTTPException(503, "execution_archive_unavailable") from None
        if job is None or job["owner"] != owner:
            raise HTTPException(404, "run_not_found")
        return job

    def get(self, run_id, owner):
        return self._public(self._owned(run_id, owner))

    def recent(self, owner):
        try:
            for payload in reversed(self.store.recent(owner, self.limit)):
                if payload["job"]["id"] not in self.jobs:
                    self._restore(payload, owner)
        except STORAGE_ERRORS:
            raise HTTPException(503, "execution_archive_unavailable") from None
        rows = [self._public(job) for job in self.jobs.values() if job["owner"] == owner]
        return {"runs": sorted(rows, key=lambda row: row["created_at"], reverse=True)[:self.limit]}

    async def start(self, owner, request: RunRequest):
        task = self.tasks.get(request.task_id)
        if task is None:
            raise HTTPException(404, "task_not_found")
        options = detached(dict(request.options))
        if len(json.dumps(options).encode()) > 65536:
            raise HTTPException(422, "oversized_task_options")
        try:
            Draft202012Validator(task.input_schema).validate(options)
        except ValidationError:
            raise HTTPException(422, "invalid_task_options") from None
        if task.paid:
            amount, ceiling = request.max_usd, task.max_budget_usd
            if (request.acknowledge_cost is not True or amount is None or ceiling is None
                    or type(amount) not in (float, int)
                    or not math.isfinite(amount) or not 0 < amount <= ceiling):
                raise HTTPException(422, "explicit_cost_acknowledgement_and_budget_required")
        elif request.acknowledge_cost or request.max_usd is not None:
            raise HTTPException(422, "paid_options_only_for_paid_task")
        request = RunRequest(request.task_id, options, request.acknowledge_cost, request.max_usd)
        async with self.lock:
            if self.closed:
                raise HTTPException(503, "workbench_closed")
            if self.active_id is not None:
                raise HTTPException(409, "execution_busy")
            run_id = uuid.uuid4().hex
            job = {"id": run_id, "owner": owner, "task_id": task.id, "status": "queued",
                   "source_sha": self.project["source_sha"], "project_id": self.project["id"],
                   "created_at": timestamp(), "started_at": None, "finished_at": None,
                   "structural_status": "not_run", "semantic_status": "pending_review",
                   "quality_passed": False, "report_available": False, "report_sha256": None,
                   "paid": task.paid, "max_usd": request.max_usd, "evidence_kind": "not_run",
                   "review_rows_key": task.review_rows_key,
                   "gaps": ["human_semantic_review_pending"] if task.requires_review else []}
            self.jobs[run_id], self.logs[run_id] = job, RunLog(secrets=_request_secrets(options))
            try:
                self._save(job, strict=True)
            except HTTPException:
                self.jobs.pop(run_id)
                self.logs.pop(run_id).close()
                raise
            self.active_id = run_id
            cancel = self.cancellations[run_id] = asyncio.Event()
            self.workers[run_id] = asyncio.create_task(self._execute(job, request, cancel))
            return self._public(job)

    async def _execute(self, job, request, cancel):
        run_id, log = job["id"], self.logs[job["id"]]
        def emit(step, text):
            log.append(step, str(text).encode("utf-8"))
            self._save(job, force=False)
        def progress(fields):
            allowed = {"phase", "steps", "completed_cases", "total_cases", "progress"}
            job.update(detached({key: value for key, value in fields.items() if key in allowed}))
            self._save(job, force=False)
        context = ExecutionContext(job["owner"], run_id, job["source_sha"], cancel, emit, progress)
        job.update(status="running", started_at=timestamp())
        self._save(job)
        try:
            if cancel.is_set():
                raise asyncio.CancelledError
            result = await asyncio.wait_for(self.adapter.execute(request, context), self.timeout)
            if not isinstance(result, RunResult) or result.status not in TERMINAL - {"interrupted"}:
                raise ValueError("invalid_adapter_result")
            if result.structural_status not in {"not_run", "passed", "failed", "partial"}:
                raise ValueError("invalid_structural_status")
            report = detached(dict(result.report))
            self.reports[run_id] = report
            job.update(status="cancelled" if cancel.is_set() else result.status,
                       structural_status=result.structural_status, evidence_kind=result.evidence_kind,
                       report_available=True, report_sha256=digest(report),
                       gaps=list(dict.fromkeys([*result.gaps, *job["gaps"]])))
        except TimeoutError:
            cancel.set()
            job.update(status="timed_out", error="execution_timeout")
        except asyncio.CancelledError:
            cancel.set()
            job.update(status="cancelled", error="execution_cancelled")
        except Exception:  # noqa: BLE001 - contain arbitrary adapter failures without publishing credential-bearing exception text.
            # Adapter exception text can contain secrets. Logs must be explicit
            # sanitized observations, not traceback or credential-bearing repr.
            job.update(status="failed", error="adapter_execution_failed")
        finally:
            job["finished_at"] = timestamp()
            log.event(None, "run_finished", status=job["status"],
                      structural_status=job["structural_status"],
                      semantic_status=job["semantic_status"], quality_passed=False)
            log.finish()
            self._save(job)
            self.active_id = None
            self.workers.pop(run_id, None)
            self.cancellations.pop(run_id, None)
            self._trim()

    def _trim(self):
        while len(self.jobs) > self.limit:
            run_id = next((key for key in self.jobs if key != self.active_id), None)
            if run_id is None:
                break
            self.jobs.pop(run_id)
            self.logs.pop(run_id).close()
            self.reports.pop(run_id, None)
            self.reviews.pop(run_id, None)
            self.checkpointed.pop(run_id, None)

    async def cancel(self, run_id, owner):
        job = self._owned(run_id, owner)
        if job["status"] not in TERMINAL:
            self.cancellations[run_id].set()
            worker = self.workers[run_id]
            try:
                await asyncio.wait_for(asyncio.shield(worker), self.grace)
            except TimeoutError:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
        return self._public(job)

    def report(self, run_id, owner):
        job = self._owned(run_id, owner)
        if run_id not in self.reports:
            raise HTTPException(409, "report_not_ready")
        key = job.get("review_rows_key", self.tasks[job["task_id"]].review_rows_key)
        rows = self.reports[run_id].get(key, []) if key else []
        fingerprints = ([{"index": index, "row_sha256": digest(row)} for index, row in enumerate(rows)]
                        if isinstance(rows, list) and all(isinstance(row, dict) for row in rows) else [])
        return detached({"report": self.reports[run_id], "report_sha256": job["report_sha256"],
                         "job": self._public(job), "review": self.reviews.get(run_id),
                         "review_contract": {"rows_key": key, "rows": fingerprints}})

    def log_page(self, run_id, owner, offset=0, limit=PAGE_BYTES, step=None, download=False):
        self._owned(run_id, owner)
        log = self.logs[run_id]
        return log.download(step) if download else log.read(offset, limit, step)

    def _checked_review(self, job, report, value):
        if job["status"] not in TERMINAL or not job["report_available"]:
            raise HTTPException(409, "report_not_ready")
        if value.get("report_sha256") != job["report_sha256"]:
            raise HTTPException(409, "review_report_hash_mismatch")
        if (value.get("verdict") not in {"passed", "failed"}
                or not isinstance(value.get("reviewer"), str) or not value["reviewer"].strip()
                or not isinstance(value.get("reason"), str) or not value["reason"].strip()):
            raise HTTPException(422, "named_evidence_based_review_required")
        key = job.get("review_rows_key", self.tasks[job["task_id"]].review_rows_key)
        evidence_rows = report.get(key) if key else []
        if key and (not isinstance(evidence_rows, list) or not evidence_rows
                    or any(not isinstance(row, dict) for row in evidence_rows)):
            raise HTTPException(422, "observed_review_rows_required")
        expected = {digest(row) for row in evidence_rows}
        if len(expected) != len(evidence_rows):
            raise HTTPException(422, "duplicate_review_row_identity")
        rows = value.get("rows", [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise HTTPException(422, "invalid_row_reviews")
        if expected and ({row.get("row_sha256") for row in rows} != expected
                         or len(rows) != len(expected)
                         or any(row.get("verdict") not in {"passed", "failed"}
                                or not isinstance(row.get("reason"), str) or not row["reason"].strip() for row in rows)):
            raise HTTPException(422, "exact_row_reviews_required")
        if not expected and rows:
            raise HTTPException(422, "unexpected_row_reviews")
        if any(row.get("verdict") == "failed" for row in rows) and value["verdict"] == "passed":
            raise HTTPException(422, "failed_rows_cannot_pass_review")

    def _quality_passed(self, job, review):
        return bool(review and review.get("verdict") == "passed"
                    and job["status"] == "completed" and job["structural_status"] == "passed"
                    and job["evidence_kind"] == "live" and job.get("source_sha") is not None
                    and job.get("source_sha") == self.project["source_sha"]
                    and not job.get("historical_import")
                    and not [gap for gap in job["gaps"] if gap != "human_semantic_review_pending"])

    def review(self, run_id, owner, review):
        job = self._owned(run_id, owner)
        value = detached(review)
        self._checked_review(job, self.reports.get(run_id), value)
        value["reviewed_at"] = timestamp()
        previous = copy.deepcopy(job), self.reviews.get(run_id)
        self.reviews[run_id] = value
        # Synthetic or partial evidence and stale imports cannot establish a
        # current production quality PASS, even after somebody reviews it.
        job.update(semantic_status="reviewed", quality_passed=self._quality_passed(job, value))
        try:
            self._save(job, strict=True)
        except HTTPException:
            old_job, old_review = previous
            self.jobs[run_id] = old_job
            if old_review is None:
                self.reviews.pop(run_id, None)
            else:
                self.reviews[run_id] = old_review
            raise
        return {"job": self._public(job), "review": detached(value)}

    def import_run(self, owner, bundle):
        value = detached(bundle)
        job, report = value.get("job"), value.get("report")
        if (not isinstance(job, dict) or not isinstance(report, dict)
                or not re.fullmatch(r"[0-9a-f]{32}", str(job.get("id", "")))
                or job.get("project_id") != self.project["id"] or job.get("task_id") not in self.tasks
                or job.get("status") not in TERMINAL or not isinstance(job.get("finished_at"), str)
                or not isinstance(job.get("created_at"), str)
                or job.get("structural_status") not in {"not_run", "passed", "failed", "partial"}
                or not isinstance(job.get("gaps"), list)
                or any(not isinstance(gap, str) or len(gap) > 200 for gap in job.get("gaps", []))
                or value.get("report_sha256") != digest(report)
                or job.get("report_sha256") != value["report_sha256"]):
            raise HTTPException(422, "invalid_import_evidence")
        try:
            for field in ("created_at", "finished_at"):
                if datetime.fromisoformat(job[field]).tzinfo is None:
                    raise ValueError("timezone_required")
        except ValueError:
            raise HTTPException(422, "invalid_import_timestamp") from None
        run_id = job["id"]
        try:
            if run_id in self.jobs or self.store.load(owner, run_id) or self.store.owned_elsewhere(owner, run_id):
                raise HTTPException(409, "import_already_exists")
        except STORAGE_ERRORS:
            raise HTTPException(503, "execution_archive_unavailable") from None
        job.pop("owner", None)
        job.update(owner=owner, historical_import=True, quality_passed=False,
                   semantic_status="pending_review", report_available=True)
        self.jobs[run_id], self.reports[run_id] = job, report
        log = self.logs[run_id] = RunLog()
        log.mark_loss("execution_interrupted")
        log.finish()
        try:
            self._save(job, strict=True)
        except HTTPException:
            self.jobs.pop(run_id)
            self.reports.pop(run_id)
            self.logs.pop(run_id).close()
            raise
        self._trim()
        return self._public(job)

    async def close(self):
        self.closed = True
        for event in self.cancellations.values():
            event.set()
        workers = list(self.workers.values())
        if workers:
            _done, pending = await asyncio.wait(workers, timeout=self.grace)
            for task in pending:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        for log in self.logs.values():
            log.close()
