"""A complete project adapter executing this project's real layered tests.

The only exposed task is a fixed, offline architecture gate plus pytest command.
Commands, paths and environment variables cannot be supplied from the web UI.
This adapter owns its test process; projects adding background processes should
also supply their platform's process-tree ownership mechanism.
"""
from __future__ import annotations

import asyncio
import codecs
import os
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from qa_workbench.contracts import ProjectDescriptor, RunResult, TaskDefinition
from qa_workbench.runtime import read_source_sha


def _environment(scratch):
    # Credentials, provider opt-ins and arbitrary pytest plugins from the QA host
    # do not belong in a business test subprocess.
    values = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
              "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
              "HOME": str(scratch), "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch)}
    if os.name == "nt":
        values["SystemRoot"] = os.environ.get("SystemRoot", r"C:\Windows")
        values["PATH"] = str(Path(values["SystemRoot"]) / "System32")
    else:
        values["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    return values


async def _stop(process):
    if os.name == "nt":
        if process.returncode is None:
            executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/taskkill.exe"
            await asyncio.to_thread(subprocess.run, [str(executable), "/PID", str(process.pid), "/T", "/F"],
                                    capture_output=True, timeout=3, check=False)
    else:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                break
            await asyncio.sleep(.05)
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await asyncio.wait_for(process.wait(), 3)


async def _run(command, root, scratch, context, deadline, step):
    if context.cancelled:
        return {"status": "cancelled", "exit_code": None, "capture_complete": True}
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return {"status": "timed_out", "exit_code": None, "capture_complete": True}
    process = await asyncio.create_subprocess_exec(
        sys.executable, *command, cwd=root, env=_environment(scratch),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}),
    )
    async def capture():
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        while chunk := await process.stdout.read(4096):
            context.emit(step, decoder.decode(chunk))
        context.emit(step, decoder.decode(b"", final=True))
    reader = asyncio.create_task(capture())
    waiter = asyncio.create_task(process.wait())
    cancelled = asyncio.create_task(context.cancellation.wait())
    status, complete = "completed", True
    try:
        done, _pending = await asyncio.wait({waiter, cancelled}, timeout=remaining,
                                            return_when=asyncio.FIRST_COMPLETED)
        if cancelled in done:
            status = "cancelled"
        elif waiter not in done:
            status = "timed_out"
        elif process.returncode:
            status = "failed"
        if status in {"cancelled", "timed_out"}:
            await _stop(process)
        try:
            await asyncio.wait_for(reader, 2)
        except TimeoutError:
            complete, status = False, "failed"
            await _stop(process)
    finally:
        cancelled.cancel()
        if process.returncode is None:
            await asyncio.shield(_stop(process))
        for task in (reader, waiter):
            if not task.done():
                task.cancel()
        await asyncio.gather(reader, waiter, cancelled, return_exceptions=True)
    return {"status": status, "exit_code": process.returncode, "capture_complete": complete}


def _junit(path):
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("missing_or_oversized_junit")
    root = ET.fromstring(path.read_bytes())
    if root.tag not in {"testsuites", "testsuite"}:
        raise ValueError("invalid_junit_root")
    rows = []
    for case in root.iter("testcase"):
        if not case.get("name"):
            raise ValueError("missing_case_identity")
        tags = [node.tag for node in case]
        outcome = ("error" if "error" in tags else "failed" if "failure" in tags
                   else "skipped" if "skipped" in tags else "passed")
        rows.append({"case_id": case.get("classname", "") + "::" + case.get("name"),
                     "outcome": outcome, "duration_seconds": float(case.get("time", "0")),
                     "evidence_kind": "offline_pytest"})
    return rows


class CartProjectAdapter:
    def __init__(self, root=None, *, timeout_seconds=30):
        self.root = Path(root or Path.cwd()).resolve()
        if not (self.root / "testing.json").is_file() or not (self.root / "tests/test_cart.py").is_file():
            raise ValueError("launch_from_the_cart_project_directory")
        if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 300:
            raise ValueError("invalid_adapter_timeout")
        self.timeout = timeout_seconds
        self.project = ProjectDescriptor("cart-example", "Cart project",
                                         read_source_sha(self.root / "VERSION"),
                                         "Real offline business tests, no provider calls")

    def tasks(self):
        return [TaskDefinition("cart-regression", "Run cart regression tests",
                               "Check layered architecture and execute the project's real pytest tests.",
                               paid=False, requires_review=True,
                               input_schema={"type": "object", "additionalProperties": False},
                               review_rows_key="rows")]

    async def execute(self, request, context):
        if request.task_id != "cart-regression" or request.options:
            raise ValueError("unsupported_cart_task")
        deadline = time.monotonic() + self.timeout
        report = {"project_id": self.project.id, "rows": [], "steps": [],
                  "evidence_kind": "offline_pytest", "semantic_acceptance": "not_evaluated"}
        with tempfile.TemporaryDirectory(prefix="cart-qa-") as directory:
            scratch = Path(directory)
            architecture = await _run(["-I", "-m", "qa_workbench.testing.layers", "--config", "testing.json"],
                                      self.root, scratch, context, deadline, "architecture")
            report["steps"].append({"id": "architecture", **architecture})
            if architecture["status"] != "completed":
                return RunResult(report, status=architecture["status"],
                                 structural_status="failed" if architecture["status"] == "failed" else "not_run",
                                 evidence_kind="offline", gaps=["business_tests_not_executed"])
            junit = scratch / "pytest.xml"
            execution = await _run(["-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", "--junitxml", str(junit)],
                                   self.root, scratch, context, deadline, "business-tests")
            report["steps"].append({"id": "business-tests", **execution})
            try:
                rows = report["rows"] = _junit(junit)
            except (OSError, ValueError, ET.ParseError):
                rows = []
                report["report_error"] = "junit_not_available"
            counts = {key: sum(row["outcome"] == key for row in rows)
                      for key in ("passed", "failed", "error", "skipped")}
            report["counts"] = {"tests": len(rows), **counts}
            structural = ("failed" if counts["failed"] or counts["error"] else "not_run" if not counts["passed"]
                          else "partial" if counts["skipped"] or execution["status"] != "completed" else "passed")
            return RunResult(report, status=execution["status"], structural_status=structural,
                             evidence_kind="offline", gaps=["live_system_not_evaluated", "human_semantic_review_pending"])

    async def health(self):
        available = (self.root / "testing.json").is_file() and (self.root / "tests/test_cart.py").is_file()
        return {"project_id": self.project.id, "status": "available" if available else "unavailable",
                "evidence_kind": "filesystem_observation", "business_tests_executed": False}


def create_adapter():
    return CartProjectAdapter()
