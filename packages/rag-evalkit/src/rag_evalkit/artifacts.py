"""Durable SQLite trial journal, immutable inputs and atomic JSON exports."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

from .contracts import ContractError
from .serialization import canonical, digest, read_json


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
            target.write(canonical(value) + "\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RunStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.path = self.directory / "trials.sqlite3"
        if not self.path.is_file():
            raise ContractError("run database does not exist")
        self.inputs = read_json(self.directory / "inputs.json")
        if self.inputs.get("schema_version") != 1 or self.inputs.get("sha") != digest(self.inputs.get("payload")):
            raise ContractError("run inputs are corrupt or unsupported")

    @classmethod
    def create(cls, output, manifest, dataset, schedule, metadata):
        directory = Path(output).resolve() / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:12])
        directory.mkdir(parents=True, exist_ok=False)
        payload = {"manifest": manifest, "dataset": dataset, "metadata": metadata}
        atomic_json(directory / "inputs.json", {"schema_version": 1, "payload": payload, "sha": digest(payload)})
        with contextlib.closing(sqlite3.connect(directory / "trials.sqlite3")) as connection, connection:
            connection.execute("CREATE TABLE trials (ordinal INTEGER PRIMARY KEY, variant TEXT NOT NULL, case_id TEXT NOT NULL, trial INTEGER NOT NULL, status TEXT NOT NULL, observation TEXT, observation_sha TEXT, UNIQUE(variant,case_id,trial))")
            connection.executemany("INSERT INTO trials VALUES(?,?,?,?, 'pending',NULL,NULL)", [(i, variant, case, trial) for i, (variant, case, trial) in enumerate(schedule)])
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO metadata VALUES('inputs_sha',?)", (digest(payload),))
        return cls(directory)

    @contextlib.contextmanager
    def lease(self):
        """OS releases the lease on crash. A stale file never blocks recovery."""
        handle = open(self.directory / ".lease", "a+b")
        locked = False
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise ContractError("run already has an active executor") from exc
            else:
                import fcntl
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise ContractError("run already has an active executor") from exc
            locked = True
            yield self
        finally:
            if locked:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    @contextlib.contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        stored = connection.execute("SELECT value FROM metadata WHERE key='inputs_sha'").fetchone()
        if stored is None or stored[0] != self.inputs["sha"]:
            connection.close()
            raise ContractError("run journal/input fingerprint mismatch")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def recover(self):
        # A process may die after a paid request but before journal commit.
        # Replay can be retried safely. Live/plugin outcomes remain uncertain,
        # never automatically resubmitted and charged again on resume.
        variants = {row["id"]: row for row in self.inputs["payload"]["manifest"]["variants"]}
        with self._connection() as connection:
            for row in connection.execute("SELECT ordinal,variant FROM trials WHERE status='running'").fetchall():
                variant = variants[row["variant"]]
                safe_replay = (variant["model"]["type"] == "replay" and variant["rag"]["type"] in {"vector", "lexical"} and variant["store"]["type"] == "memory" and variant["harness"]["type"] in {"single_turn", "tool_loop"} and variant["embedding"]["type"] == "fixture" and not variant.get("tools"))
                if safe_replay:
                    connection.execute("UPDATE trials SET status='pending' WHERE ordinal=?", (row["ordinal"],))
                else:
                    observation = {"error": {"type": "InterruptedOutcomeUnknown", "message": "request may have completed; automatic retry disabled"}, "cleanup": {"status": "unknown"}, "usage": {"cost_usd": None}, "semantic_verdict": "not_evaluated"}
                    connection.execute("UPDATE trials SET status='failed',observation=?,observation_sha=? WHERE ordinal=?", (canonical(observation), digest(observation), row["ordinal"]))

    def rows(self):
        with self._connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM trials ORDER BY ordinal")]
        for row in rows:
            if row["status"] not in {"pending", "running", "completed", "failed", "unsupported", "cancelled"} or ((row["status"] in {"pending", "running"}) != (row["observation"] is None)):
                raise ContractError("invalid trial journal state")
            if row["observation"] is not None:
                row["observation"] = json.loads(row["observation"])
                if digest(row["observation"]) != row["observation_sha"]:
                    raise ContractError("corrupt trial observation")
        expected = {(variant["id"], case["id"], trial) for variant in self.inputs["payload"]["manifest"]["variants"] for case in self.inputs["payload"]["dataset"]["cases"] if self.inputs["payload"]["manifest"]["split"] == "all" or case["split"] == self.inputs["payload"]["manifest"]["split"] for trial in range(self.inputs["payload"]["manifest"]["repeats"])}
        if {(row["variant"], row["case_id"], row["trial"]) for row in rows} != expected:
            raise ContractError("missing or unexpected trial rows")
        return rows

    def start(self, ordinal):
        with self._connection() as connection:
            changed = connection.execute("UPDATE trials SET status='running' WHERE ordinal=? AND status='pending'", (ordinal,)).rowcount
            if changed != 1:
                raise ContractError("trial is not pending")

    def finish(self, ordinal, status, observation):
        if status not in {"completed", "failed", "unsupported", "cancelled"}:
            raise ContractError("invalid terminal trial status")
        with self._connection() as connection:
            changed = connection.execute("UPDATE trials SET status=?,observation=?,observation_sha=? WHERE ordinal=? AND status='running'", (status, canonical(observation), digest(observation), ordinal)).rowcount
            if changed != 1:
                raise ContractError("trial is not running")

    def export(self):
        rows = self.rows()
        report = {"schema_version": 1, "run_id": self.directory.name, "inputs_sha": self.inputs["sha"], "metadata": self.inputs["payload"]["metadata"], "complete": all(row["status"] not in {"pending", "running"} for row in rows), "rows": rows}
        atomic_json(self.directory / "report.json", report)
        return report


def list_runs(output):
    rows = []
    for path in sorted(Path(output).glob("*/inputs.json")):
        store = RunStore(path.parent)
        counts = {}
        for row in store.rows():
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        rows.append({"run_id": path.parent.name, "counts": counts})
    return rows
