"""Contract: qa_workbench ProjectAdapter ports, service lifecycle and /api routes.

This adapter measures effects, HTTP results and persisted data; assertions about
the scenario remain in scripts. The test system has no NewsCout dependency.
"""
import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from functools import wraps
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from qa_workbench.app import create_app
from qa_workbench.contracts import (
    ProjectDescriptor,
    RunRequest,
    RunResult,
    TaskDefinition,
)
from qa_workbench.service import WorkbenchService, digest


def _isolated(operation):
    @wraps(operation)
    def observe():
        with tempfile.TemporaryDirectory(prefix="qa-core-") as directory:
            return operation(directory)
    return observe


class AlternateSystem:
    project = ProjectDescriptor("inventory-system", "Inventory system", "a" * 40)

    def __init__(self, waiting=False):
        self.executions = 0
        self.waiting = waiting
        self.later_side_effects = 0

    def tasks(self):
        schema = {"type": "object", "properties": {"count": {"type": "integer", "minimum": 1}},
                  "additionalProperties": False}
        return [TaskDefinition("check", "Verify inventory", input_schema=schema),
                TaskDefinition("paid-check", "Run paid evaluation", paid=True, max_budget_usd=0.2,
                               input_schema=schema)]

    async def execute(self, request, context):
        self.executions += 1
        context.emit("inventory", "Authorization: Bearer confidential-value\n")
        if self.waiting:
            try:
                await asyncio.wait_for(context.cancellation.wait(), 0.05)
            except TimeoutError:
                self.later_side_effects += 1
            else:
                return RunResult({}, status="cancelled", evidence_kind="synthetic")
        await asyncio.sleep(0)
        row = {"case_id": "inventory-round-trip", "expected": 3, "observed": 3}
        return RunResult({"rows": [row]}, structural_status="passed", evidence_kind="synthetic")

    async def health(self):
        return {"status": "available", "evidence_kind": "synthetic"}


async def _settle(service):
    workers = list(service.workers.values())
    if workers:
        await asyncio.gather(*workers)


def _code(operation):
    try:
        operation()
    except HTTPException as error:
        return error.status_code
    return None


async def _async_code(operation):
    try:
        await operation()
    except HTTPException as error:
        return error.status_code
    return None


@_isolated
def inspect_workbench(directory):
    async def scenario():
        adapter = AlternateSystem()
        service = WorkbenchService(adapter, directory)
        result = {"tasks": [row["id"] for row in service.capabilities()["tasks"]],
                  "history": service.recent("alice")["runs"], "executions": adapter.executions}
        await service.close()
        return result
    return asyncio.run(scenario())


@_isolated
def run_and_review(directory):
    async def scenario():
        service = WorkbenchService(AlternateSystem(), directory)
        job = await service.start("alice", RunRequest("check"))
        await _settle(service)
        job = service.get(job["id"], "alice")
        report = service.report(job["id"], "alice")
        review = {"report_sha256": "0" * 64, "reviewer": "Independent reviewer", "reason": "Compared exact source row",
                  "verdict": "passed"}
        wrong_hash = _code(lambda: service.review(job["id"], "alice", review))
        review["report_sha256"] = report["report_sha256"]
        missing = _code(lambda: service.review(job["id"], "alice", review))
        review["rows"] = [{"row_sha256": digest(row), "verdict": "passed", "reason": "Values agree"}
                          for row in report["report"]["rows"]]
        reviewed = service.review(job["id"], "alice", review)["job"]
        result = {"status": job["status"], "structural_status": job["structural_status"],
                  "initial_semantic_status": job["semantic_status"], "wrong_hash_status": wrong_hash,
                  "missing_row_status": missing,
                  "wrong_owner_status": _code(lambda: service.get(job["id"], "bob")),
                  "reviewed_semantic_status": reviewed["semantic_status"], "quality_passed": reviewed["quality_passed"],
                  "hash_matches": digest(report["report"]) == report["report_sha256"]}
        await service.close()
        return result
    return asyncio.run(scenario())


@_isolated
def check_admission(directory):
    async def scenario():
        adapter = AlternateSystem()
        service = WorkbenchService(adapter, directory)
        requests = [RunRequest("paid-check"), RunRequest("paid-check", acknowledge_cost=True, max_usd=0.3),
                    RunRequest("paid-check", acknowledge_cost=True, max_usd=True),
                    RunRequest("check", {"count": "three"}), RunRequest("check", {"unknown": 1})]
        denied = [await _async_code(lambda request=request: service.start("alice", request)) for request in requests]
        before = adapter.executions
        job = await service.start("alice", RunRequest("paid-check", {"count": 3}, True, 0.1))
        await _settle(service)
        result = {"denied_codes": denied, "executions_before_acceptance": before,
                  "executions_after_acceptance": adapter.executions, "accepted_budget": job["max_usd"]}
        await service.close()
        return result
    return asyncio.run(scenario())


@_isolated
def restart_workbench(directory):
    async def scenario():
        adapter = AlternateSystem()
        service = WorkbenchService(adapter, directory)
        job = await service.start("alice", RunRequest("check"))
        await _settle(service)
        before = service.get(job["id"], "alice")
        text = service.log_page(job["id"], "alice")["text"]
        await service.close()
        restored = WorkbenchService(adapter, directory)
        after = restored.get(job["id"], "alice")
        recovered_text = restored.log_page(job["id"], "alice")["text"]
        result = {"executions": adapter.executions, "restored_status": after["status"],
                  "report_hash_unchanged": before["report_sha256"] == after["report_sha256"],
                  "logs_unchanged": text == recovered_text,
                  "credential_exposed": "confidential-value" in recovered_text,
                  "redaction_present": "[REDACTED]" in recovered_text}
        await restored.close()
        return result
    return asyncio.run(scenario())


@_isolated
def recover_abandoned_run(directory):
    async def scenario():
        adapter = AlternateSystem(waiting=True)
        service = WorkbenchService(adapter, directory)
        job = await service.start("alice", RunRequest("check"))
        recovered = WorkbenchService(adapter, directory)
        observed = recovered.get(job["id"], "alice")
        await service.close()
        await recovered.close()
        return {**observed, "executions": adapter.executions}
    return asyncio.run(scenario())


@_isolated
def stop_execution(directory):
    async def scenario():
        adapter = AlternateSystem(waiting=True)
        service = WorkbenchService(adapter, Path(directory) / "cancel")
        job = await service.start("alice", RunRequest("check"))
        await asyncio.sleep(0)
        cancelled = await service.cancel(job["id"], "alice")
        await service.close()
        timeout = WorkbenchService(adapter, Path(directory) / "timeout", timeout_seconds=0.01)
        job = await timeout.start("alice", RunRequest("check"))
        await _settle(timeout)
        result = {"cancel_status": cancelled["status"], "timeout_status": timeout.get(job["id"], "alice")["status"],
                  "later_side_effects": adapter.later_side_effects}
        await timeout.close()
        return result
    return asyncio.run(scenario())


@_isolated
def import_evidence(directory):
    async def scenario():
        service = WorkbenchService(AlternateSystem(), Path(directory) / "original")
        job = await service.start("alice", RunRequest("check"))
        await _settle(service)
        bundle = service.report(job["id"], "alice")
        await service.close()
        target = WorkbenchService(AlternateSystem(), Path(directory) / "imported")
        imported = target.import_run("alice", bundle)
        duplicate = _code(lambda: target.import_run("alice", bundle))
        bundle["report"]["tampered"] = True
        tampered = _code(lambda: target.import_run("alice", bundle))
        result = {"source_sha_preserved": imported["source_sha"] == job["source_sha"],
                  "historical_import": imported["historical_import"], "quality_passed": imported["quality_passed"],
                  "semantic_status": imported["semantic_status"], "duplicate_status": duplicate,
                  "tampered_status": tampered}
        await target.close()
        return result
    return asyncio.run(scenario())


@_isolated
def corrupt_archive(directory):
    async def scenario():
        service = WorkbenchService(AlternateSystem(), directory)
        await service.start("alice", RunRequest("check"))
        await _settle(service)
        path = next(service.store.root.glob("*.json"))
        await service.close()
        path.write_text("{}")
        restarted = WorkbenchService(AlternateSystem(), directory)
        code = _code(lambda: restarted.recent("alice"))
        await restarted.close()
        return {"status": code}
    return asyncio.run(scenario())


@_isolated
def exercise_http(directory):
    async def scenario():
        adapter = AlternateSystem()
        def authenticate(request):
            owner = request.headers.get("x-test-owner")
            if not owner:
                raise HTTPException(401, "authentication_required")
            return owner
        app = create_app(adapter, archive_root=directory, authenticate=authenticate)
        service = app.state.workbench
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            unauthenticated = await client.get("/api/capabilities")
            capabilities = await client.get("/api/capabilities", headers={"x-test-owner": "alice"})
            await client.get("/api/runs", headers={"x-test-owner": "alice"})
            before = adapter.executions
            response = await client.post("/api/runs", json={"task_id": "check"}, headers={"x-test-owner": "alice"})
            run_id = response.json()["id"]
            await _settle(service)
            detail = await client.get("/api/runs/" + run_id, headers={"x-test-owner": "alice"})
            other = await client.get("/api/runs/" + run_id, headers={"x-test-owner": "bob"})
            invalid = await client.post("/api/runs", json={"task_id": "check", "unexpected": "private-input-marker"},
                                        headers={"x-test-owner": "alice"})
            oversized = await client.post("/api/runs", json={"task_id": "check", "options": {"message": "x" * 100000}},
                                          headers={"x-test-owner": "alice"})
            result = {"unauthenticated_status": unauthenticated.status_code,
                      "capabilities_status": capabilities.status_code, "executions_after_reads": before,
                      "start_status": response.status_code, "completed": detail.json()["status"] == "completed",
                      "other_owner_status": other.status_code, "cache_control": detail.headers["cache-control"],
                      "invalid_input_status": invalid.status_code,
                      "secret_echoed": "private-input-marker" in invalid.text,
                      "oversized_body_status": oversized.status_code}
        await service.close()
        return result
    return asyncio.run(scenario())


@_isolated
def recover_forged_quality(directory):
    async def scenario():
        service = WorkbenchService(AlternateSystem(), directory)
        job = await service.start("alice", RunRequest("check"))
        await _settle(service)
        path = next(service.store.root.glob("*.json"))
        await service.close()
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope["payload"]["report"]["quality_passed"] = True
        envelope["payload"]["report"]["semantic_status"] = "reviewed"
        encoded = json.dumps(envelope["payload"], ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        envelope["sha256"] = hashlib.sha256(encoded).hexdigest()
        path.write_text(json.dumps(envelope), encoding="utf-8")
        restored = WorkbenchService(AlternateSystem(), directory)
        result = restored.get(job["id"], "alice")
        await restored.close()
        return result
    return asyncio.run(scenario())


@_isolated
def reject_invalid_contract(directory):
    adapter = AlternateSystem()
    adapter.project = ProjectDescriptor("inventory-system", "Inventory", "not-a-commit")
    try:
        WorkbenchService(adapter, directory)
    except ValueError:
        source_rejected = True
    else:
        source_rejected = False
    adapter.project = ProjectDescriptor("inventory-system", "Inventory", "a" * 40)
    adapter.tasks = lambda: [TaskDefinition("check", "Remote", input_schema={"$ref": "https://invalid.local/schema"})]
    try:
        WorkbenchService(adapter, directory)
    except ValueError:
        remote_rejected = True
    else:
        remote_rejected = False
    return {"bad_source_rejected": source_rejected, "remote_reference_rejected": remote_rejected,
            "executions": adapter.executions}


@_isolated
def review_other_report_shape(directory):
    class OtherReportSystem(AlternateSystem):
        def tasks(self):
            return [TaskDefinition("check", "Read another report shape", review_rows_key="samples")]

        async def execute(self, request, context):
            return RunResult({"samples": [{"id": "case-1", "observed": "source-supported"}]},
                             structural_status="passed", evidence_kind="synthetic")
    async def scenario():
        service = WorkbenchService(OtherReportSystem(), directory)
        job = await service.start("alice", RunRequest("check"))
        await _settle(service)
        report = service.report(job["id"], "alice")
        review = {"report_sha256": report["report_sha256"], "reviewer": "Named reviewer",
                  "reason": "Read the case and sources", "verdict": "passed"}
        missing = _code(lambda: service.review(job["id"], "alice", review))
        review["rows"] = [{"row_sha256": row["row_sha256"], "verdict": "passed", "reason": "Read this exact case"}
                          for row in report["review_contract"]["rows"]]
        reviewed = service.review(job["id"], "alice", review)["job"]
        result = {"original_report_preserved": report["report"] == {"samples": [{"id": "case-1", "observed": "source-supported"}]},
                  "rows_key": report["review_contract"]["rows_key"], "missing_rows_status": missing,
                  "reviewed_status": reviewed["semantic_status"], "quality_passed": reviewed["quality_passed"]}
        await service.close()
        return result
    return asyncio.run(scenario())


@_isolated
def run_independently(directory):
    import qa_workbench
    source = Path(qa_workbench.__file__).parent
    copied = Path(directory) / "standalone" / "qa_workbench"
    shutil.copytree(source, copied, ignore=shutil.ignore_patterns("__pycache__"))
    program = """import asyncio,json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from qa_workbench.demo import DemoAdapter
from qa_workbench.contracts import RunRequest
from qa_workbench.service import WorkbenchService
async def scenario():
 service=WorkbenchService(DemoAdapter(),pathlib.Path(sys.argv[1])/'data')
 job=await service.start('reader',RunRequest('contract-check'))
 await asyncio.gather(*service.workers.values())
 print(json.dumps({'project_id':service.project['id'],'status':service.get(job['id'],'reader')['status']}))
 await service.close()
asyncio.run(scenario())
"""
    result = subprocess.run([sys.executable, "-I", "-c", program, str(copied.parent)],
                            cwd=copied.parent, capture_output=True, text=True, check=False)
    observed = json.loads(result.stdout) if result.returncode == 0 else {}
    return {"exit_code": result.returncode, "stderr": result.stderr, **observed}


def _second_system(directory):
    source = Path(__file__).resolve().parents[3] / "templates/python-project"
    target = Path(directory) / "cart-project"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", ".pytest_cache"))
    spec = importlib.util.spec_from_file_location("cart_qa_example", target / "cart_qa.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, target


@_isolated
def run_second_system(directory):
    async def scenario():
        module, target = _second_system(directory)
        adapter = module.CartProjectAdapter(target)
        service = WorkbenchService(adapter, Path(directory) / "evidence")
        job = await service.start("reader", RunRequest("cart-regression"))
        await _settle(service)
        finished = service.get(job["id"], "reader")
        report = service.report(job["id"], "reader")["report"]
        result = {"project_id": adapter.project.id, "status": finished["status"],
                  "structural_status": finished["structural_status"], "quality_passed": finished["quality_passed"],
                  "counts": report.get("counts"), "case_ids": [row["case_id"] for row in report["rows"]],
                  "semantic_acceptance": report["semantic_acceptance"],
                  "logs": service.log_page(job["id"], "reader")["text"]}
        await service.close()
        return result
    return asyncio.run(scenario())


def _process_alive(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@_isolated
def stop_second_system(directory):
    async def scenario():
        module, target = _second_system(directory)
        marker = target / "started.pid"
        physical = target / "tests/test_support/physical/cart.py"
        original = physical.read_text(encoding="utf-8")
        original = original.replace("from application import cart_total", "import os, time\nfrom pathlib import Path\nfrom application import cart_total")
        original = original.replace("    return cart_total(prices)",
                    "    Path(" + repr(str(marker)) + ").write_text(str(os.getpid()))\n    time.sleep(60)\n    return cart_total(prices)")
        physical.write_text(original, encoding="utf-8")
        service = WorkbenchService(module.CartProjectAdapter(target), Path(directory) / "cancel")
        job = await service.start("reader", RunRequest("cart-regression"))
        for _ in range(500):
            if marker.is_file() or service.get(job["id"], "reader")["status"] in {"failed", "timed_out"}:
                break
            await asyncio.sleep(.02)
        pid = int(marker.read_text()) if marker.is_file() else None
        cancelled = await service.cancel(job["id"], "reader")
        await service.close()
        timeout = WorkbenchService(module.CartProjectAdapter(target, timeout_seconds=.01), Path(directory) / "timeout")
        run = await timeout.start("reader", RunRequest("cart-regression"))
        await _settle(timeout)
        timed = timeout.get(run["id"], "reader")
        result = {"business_process_started": pid is not None, "business_process_alive": _process_alive(pid) if pid else False,
                  "cancel_status": cancelled["status"], "timeout_status": timed["status"],
                  "timeout_quality_passed": timed["quality_passed"]}
        await timeout.close()
        return result
    return asyncio.run(scenario())


@_isolated
def check_cli_authentication(directory):
    from qa_workbench.cli import main
    captured = {}
    def capture_host(app, **settings):
        captured["app"] = app
    secret = "local-cli-fixture-token-with-sufficient-length"
    with patch.dict(os.environ, {"QA_AUTH_TEST_TOKEN": secret}), patch("uvicorn.run", side_effect=capture_host):
        main(["--token-env", "QA_AUTH_TEST_TOKEN", "--archive-root", str(directory)])
    async def scenario():
        app = captured["app"]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            valid = await client.get("/api/capabilities", headers={"authorization": "Bearer " + secret})
            malformed = await client.get("/api/capabilities", headers=[(b"authorization", b"Bearer \xff")])
            result = {"valid_status": valid.status_code, "malformed_status": malformed.status_code,
                      "malformed_body": malformed.json()}
        await app.state.workbench.close()
        return result
    return asyncio.run(scenario())


@_isolated
def retry_failed_review_write(directory):
    async def scenario():
        service = WorkbenchService(AlternateSystem(), directory)
        job = await service.start("alice", RunRequest("check"))
        await _settle(service)
        report = service.report(job["id"], "alice")
        review = {"report_sha256": report["report_sha256"], "reviewer": "synthetic fixture reviewer",
                  "reason": "Fixture-only exact case readback", "verdict": "passed",
                  "rows": [{"row_sha256": row["row_sha256"], "verdict": "passed", "reason": "Read exact fixture"}
                           for row in report["review_contract"]["rows"]]}
        with patch.object(service.store, "save", side_effect=OSError("fixture storage unavailable")):
            failure = _code(lambda: service.review(job["id"], "alice", review))
        unchanged = service.report(job["id"], "alice")
        retried = service.review(job["id"], "alice", review)["job"]
        result = {"failed_write_status": failure,
                  "semantic_status_after_failure": unchanged["job"]["semantic_status"],
                  "review_after_failure": unchanged["review"],
                  "report_hash_preserved": report["report_sha256"] == unchanged["report_sha256"],
                  "semantic_status_after_retry": retried["semantic_status"], "quality_passed": retried["quality_passed"]}
        await service.close()
        return result
    return asyncio.run(scenario())
