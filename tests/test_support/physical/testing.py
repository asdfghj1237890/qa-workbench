"""Contract: qa_workbench.testing.layers and observations public policies.

Temporary repositories have no remotes. Adversarial Python is parsed as text,
never imported. Subprocesses exercise only the checker against temporary files.
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from qa_workbench.health import observation as health_observation
from qa_workbench.testing.layers import LayerPolicy, check_source
from qa_workbench.testing.observations import ObservationPolicy
from test_support.contracts.testing import VALID_SCRIPT, TestingObservation

POLICY = LayerPolicy(
    test_root="acceptance/specs/",
    support_package="quality_support",
    lifecycle_actions=("quality_support.actions.lifecycle.isolated_orders",),
)
SCRIPT = "acceptance/specs/test_orders.py"
ACTION = "acceptance/specs/quality_support/actions/orders.py"
PHYSICAL = "acceptance/specs/quality_support/physical/orders.py"


def inspect_case(name):
    cases = {
        "valid_script": (SCRIPT, VALID_SCRIPT),
        "script_imports_application": (SCRIPT, "from application import service"),
        "script_imports_physical_alias": (SCRIPT, "from quality_support import physical as engine"),
        "relative_physical_import": ("acceptance/specs/integration/test_orders.py", "from ..quality_support.physical import orders"),
        "action_exposes_driver": (ACTION, "from quality_support.physical import orders as engine"),
        "action_missing_observation": (ACTION, "def total():\n    return 12"),
        "physical_hides_assertion": (PHYSICAL, '"""Contract: application.orders."""\nassert True'),
        "physical_missing_contract": (PHYSICAL, "def total():\n    return 12"),
        "script_calls_lifecycle": (SCRIPT, "from quality_support.actions.lifecycle import isolated_orders\ndef test_order():\n    isolated_orders()"),
        "unclassified_helper": ("acceptance/specs/helpers.py", "import application"),
        "package_reexport": ("acceptance/specs/quality_support/__init__.py", "from application import service"),
        "script_imports_observation_implementation": (SCRIPT, "from qa_workbench.testing.observations import snapshot"),
        "lifecycle_action": ("acceptance/specs/quality_support/actions/lifecycle.py", "def isolated_orders():\n    return None"),
        "contract_observation_binding": ("acceptance/specs/quality_support/contracts/observations.py", "from qa_workbench.testing.observations import ObservationPolicy\n_POLICY = ObservationPolicy(('quality_support.contracts',))"),
    }
    path, source = cases[name]
    return {"path": path, "findings": check_source(path, source, POLICY)}


def observation(kind):
    policy = ObservationPolicy(("test_support.contracts",))
    if kind == "live":
        return policy.snapshot(SimpleNamespace(client=True))
    if kind == "callable":
        return policy.snapshot(lambda: 1)
    if kind == "foreign_dataclass":
        foreign = LayerPolicy()
        return policy.snapshot(foreign)
    if kind == "dataclass_type":
        return policy.snapshot(TestingObservation)
    original = TestingObservation(items=[{"value": "original"}])
    detached = policy.snapshot(original)
    detached.items[0]["value"] = "changed"
    return {"original": original.items, "detached": detached.items, "same": original is detached}


def invalid_policy(value):
    try:
        LayerPolicy.from_mapping(value)
    except (ValueError, TypeError) as error:
        return str(error)
    return None


def staged_policy(mode):
    with tempfile.TemporaryDirectory(prefix="qa-layer-policy-") as directory:
        repository = Path(directory)
        root = repository / "nested project" if mode == "nested" else repository
        root.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q", str(repository)], check=True, capture_output=True)
        config = {"test_root": POLICY.test_root, "support_package": POLICY.support_package,
                  "lifecycle_actions": list(POLICY.lifecycle_actions)}
        (root / "testing.json").write_text(json.dumps(config), encoding="utf-8")
        target = root / SCRIPT
        target.parent.mkdir(parents=True)
        target.write_text("from application import service\n" if mode == "overlay" else VALID_SCRIPT, encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
        if mode == "overlay":
            target.write_text(VALID_SCRIPT, encoding="utf-8")
            (root / "testing.json").write_text(json.dumps({"test_root": "other/"}), encoding="utf-8")
        elif mode == "missing_config":
            subprocess.run(["git", "-C", str(root), "rm", "--cached", "testing.json"], check=True, capture_output=True)
        command = [sys.executable, "-m", "qa_workbench.testing.layers", "--root", str(root), "--config", "testing.json", "--staged"]
        result = subprocess.run(command, env=os.environ.copy(), capture_output=True, text=True, check=False)
        return {"code": result.returncode, "output": result.stdout + result.stderr}


def health_evidence(kind):
    if kind == "unknown":
        return health_observation("billing")
    if kind == "measured":
        now = datetime.fromisoformat("2026-01-01T12:00:00+00:00")
        return health_observation("billing", "critical", "probe_failed", observed=now,
                                  freshness="fresh", value=15, unit="milliseconds",
                                  threshold=1000, metric="response_duration",
                                  source="adapter_probe", details={"checks": ["http"]})
    if kind == "detached":
        original = {"checks": [{"status": "failed"}]}
        row = health_observation("billing", details=original)
        row["details"]["checks"][0]["status"] = "changed"
        return {"original": original, "observation": row}
    import qa_workbench.health

    source = Path(qa_workbench.health.__file__).resolve().parents[1]
    code = ("import json,sys; sys.path.insert(0,sys.argv[1]); "
            "from qa_workbench.health import observation; "
            "print(json.dumps({'row':observation('billing'),'unwanted_imports':"
            "sorted(set(sys.modules)&{'fastapi','pydantic','agents','app'})}))")
    result = subprocess.run([sys.executable, "-I", "-c", code, str(source)],
                            capture_output=True, text=True, check=True, timeout=20)
    return json.loads(result.stdout)


def storage_factory_contract():
    import asyncio

    from qa_workbench.contracts import RunRequest
    from qa_workbench.demo import DemoAdapter
    from qa_workbench.service import ExecutionStore, WorkbenchService

    with tempfile.TemporaryDirectory(prefix="qa-store-port-") as directory:
        root = Path(directory) / "operator-storage"
        factories, saved = [], []

        class OperatorStore(ExecutionStore):
            def save(self, owner, run_id, payload, limit=5):
                saved.append(run_id)
                return super().save(owner, run_id, payload, limit)

        def factory(path):
            factories.append(path.name)
            return OperatorStore(path)

        async def scenario():
            service = WorkbenchService(DemoAdapter(), root, history_limit=1, store_factory=factory)
            service.capabilities()
            before = root.exists()
            newest = None
            for _ in range(2):
                newest = await service.start("operator", RunRequest("contract-check"))
                await asyncio.gather(*list(service.workers.values()))
            retained = [job["id"] for job in service.recent("operator")["runs"]]
            files = len(service.store._files())
            await service.close()
            recovered = WorkbenchService(DemoAdapter(), root, history_limit=1, store_factory=factory)
            restored = [job["id"] for job in recovered.recent("operator")["runs"]]
            await recovered.close()
            return {"storage_exists_after_discovery": before, "factory_projects": factories,
                    "save_calls": len(saved), "newest_run_id": newest["id"],
                    "retained_run_ids": retained, "restored_run_ids": restored,
                    "archive_files": files}

        return asyncio.run(scenario())
