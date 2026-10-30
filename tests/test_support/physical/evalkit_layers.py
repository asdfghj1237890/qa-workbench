"""Contract: scripts/check_evalkit_layers.py check(package_root) parses imports without executing them."""

import importlib.util
import tempfile
from pathlib import Path


def _check(relative, source):
    checker_path = Path(__file__).resolve().parents[3] / "scripts/check_evalkit_layers.py"
    spec = importlib.util.spec_from_file_location("qa_review_evalkit_layers", checker_path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    with tempfile.TemporaryDirectory(prefix="qa-evalkit-layers-") as directory:
        root = Path(directory)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        (root / "tests").mkdir(exist_ok=True)
        (root / "tests/test_probe.py").write_text("", encoding="utf-8")
        target.write_text(source, encoding="utf-8")
        return checker.check(root)


def inspect_case(case):
    script = "tests/test_probe.py"
    action = "tests/test_support/actions/probe.py"
    physical = "tests/test_support/physical/probe.py"
    core = "src/rag_evalkit/probe.py"
    cases = {
        "script_from_physical": (script, "from test_support import physical"),
        "script_relative_physical": (script, "from .test_support import physical"),
        "nested_script_relative_physical": ("tests/test_support/scenarios/test_probe.py", "from ..physical import probe"),
        "script_from_mock": (script, "from unittest import mock"),
        "script_from_core": (script, "from rag_evalkit import serialization"),
        "script_app": (script, "import app.settings"),
        "script_prefix_neighbors": (script, "import appdirs, rag_evalkit_helpers, unittest.mockup, test_support.physicality"),
        "physical_from_actions": (physical, "from test_support import actions"),
        "physical_relative_actions": (physical, "from ..actions import probe"),
        "physical_from_script": (physical, "from test_probe import run"),
        "physical_prefix_neighbors": (physical, "import transactions, third_party.actions, test_support.actions_extra"),
        "action_absolute": (action, "from test_support.observed import observed\nfrom test_support.physical import probe\n@observed\ndef read():\n    return probe.read()"),
        "action_relative": (action, "from ..observed import observed\nfrom ..physical import probe\n@observed\ndef read():\n    return probe.read()"),
        "action_from_support": (action, "from test_support import physical"),
        "action_unobserved": (action, "def read():\n    return 1"),
        "core_app": (core, "from app import settings"),
        "core_prefix_neighbors": (core, "import appdirs, test_support_helpers, firebase_admin_helpers"),
    }
    return _check(*cases[case])


def inspect_action_import(module):
    return _check("tests/test_support/actions/probe.py", "import " + module)
