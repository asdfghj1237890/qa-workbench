"""Contract: qa_workbench.report_io.write_json atomic publication and Windows retry."""

import errno
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, BrokenBarrierError, Event, Lock, Thread
from unittest.mock import patch

from qa_workbench import report_io


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _temporary_files(path):
    return sorted(item.name for item in path.parent.glob("*.tmp"))


def publish_unicode():
    with tempfile.TemporaryDirectory(prefix="qa-report-") as directory:
        path = Path(directory) / "report.json"
        ordinary = Path(directory) / "ordinary.json"
        ordinary.write_text("{}", encoding="utf-8")
        original_write = Path.write_text
        encodings = []

        def legacy_write(target, data, *args, **kwargs):
            encodings.append(kwargs.get("encoding"))
            kwargs.setdefault("encoding", "cp1252")
            return original_write(target, data, *args, **kwargs)

        with patch.object(Path, "write_text", legacy_write):
            report_io.write_json(path, {"text": "繁體中文 café 🌏"})
        return {"encoding": encodings[0], "report": _read(path),
                "text": path.read_bytes().decode("utf-8"), "mode": path.stat().st_mode & 0o777,
                "ordinary_mode": ordinary.stat().st_mode & 0o777, "temporary_files": _temporary_files(path)}


def publish_concurrently():
    with tempfile.TemporaryDirectory(prefix="qa-report-concurrent-") as directory:
        path = Path(directory) / "report.json"
        seed = {"writer": -1, "round": -1, "text": "previous"}
        report_io.write_json(path, seed)
        candidates = [seed]
        write_errors, read_errors, reads, names, sharing_violations = [], [], [], [], []
        barrier, lock, stopped = Barrier(4), Lock(), Event()
        original_write = Path.write_text

        def synchronized_write(target, *args, **kwargs):
            count = original_write(target, *args, **kwargs)
            with lock:
                names.append(target.name)
            barrier.wait(timeout=5)
            return count

        def writer(number):
            for round_number in range(4):
                value = {"writer": number, "round": round_number, "text": str(number) * 16384}
                with lock:
                    candidates.append(value)
                try:
                    report_io.write_json(path, value)
                except (OSError, ValueError, BrokenBarrierError) as error:
                    with lock:
                        write_errors.append(type(error).__name__ + ": " + str(error))

        def reader():
            while not stopped.is_set():
                try:
                    reads.append(_read(path))
                except PermissionError as error:
                    # Windows can deny opening the target during rename. This
                    # is a sharing retry, not a sample of invalid report bytes.
                    if os.name == "nt" and (getattr(error, "winerror", None) in (5, 32, 33)
                                            or (getattr(error, "winerror", None) is None and error.errno == errno.EACCES)):
                        sharing_violations.append(error.errno)
                    else:
                        read_errors.append(type(error).__name__ + ": " + str(error))
                except (OSError, UnicodeError, json.JSONDecodeError) as error:
                    read_errors.append(type(error).__name__ + ": " + str(error))

        reader_thread = Thread(target=reader)
        reader_thread.start()
        try:
            with patch.object(Path, "write_text", synchronized_write), ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(writer, range(4)))
        finally:
            stopped.set()
            reader_thread.join(timeout=5)
        return {"write_errors": write_errors, "read_errors": read_errors,
                "reads": len(reads), "published": _read(path), "candidates": candidates,
                "reader_sharing_retries": len(sharing_violations),
                "temporary_names": names, "writes": 16, "temporary_files": _temporary_files(path)}


def fail_publication(failure):
    with tempfile.TemporaryDirectory(prefix="qa-report-failure-") as directory:
        path = Path(directory) / "report.json"
        report_io.write_json(path, {"generation": "previous"})
        original_write = Path.write_text
        attempts = []

        def failed_write(target, *args, **kwargs):
            original_write(target, "partial", encoding="utf-8")
            raise OSError("controlled write failure")

        def failed_replace(target, destination):
            attempts.append(target.name)
            if failure.startswith("windows"):
                error = PermissionError("controlled rename failure")
                error.winerror = 32 if failure == "windows_permanent" else 87
                raise error
            raise OSError("controlled rename failure")

        error_type = None
        with patch.object(report_io, "_WINDOWS", True), patch.object(report_io.time, "sleep"), patch.object(
            Path, "write_text", failed_write if failure == "write" else original_write
        ), patch.object(Path, "replace", failed_replace):
            try:
                report_io.write_json(path, {"bad": object()} if failure == "serialization" else {"generation": "new"})
            except (OSError, TypeError, ValueError) as error:
                error_type = type(error).__name__
        return {"error_type": error_type, "report": _read(path), "attempts": len(attempts),
                "temporary_files": _temporary_files(path)}


def retry_publication(winerror):
    with tempfile.TemporaryDirectory(prefix="qa-report-retry-") as directory:
        path = Path(directory) / "report.json"
        report_io.write_json(path, {"generation": "previous"})
        original_replace = Path.replace
        attempts = []

        def retry_replace(target, destination):
            attempts.append(target.name)
            if len(attempts) < 3:
                error = PermissionError("controlled sharing violation")
                error.winerror = winerror
                raise error
            return original_replace(target, destination)

        with patch.object(report_io, "_WINDOWS", True), patch.object(Path, "replace", retry_replace), patch.object(
            report_io.time, "sleep"
        ) as delay:
            report_io.write_json(path, {"generation": "published"})
        return {"attempts": len(attempts), "delays": [call.args[0] for call in delay.call_args_list],
                "report": _read(path), "temporary_files": _temporary_files(path)}
