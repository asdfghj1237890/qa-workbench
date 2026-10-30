"""Contract: qa_workbench.cli.main resolves module:factory before starting uvicorn."""

import importlib
import io
import os
import sys
import tempfile
import uuid
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from qa_workbench.cli import main


def load_adapter(case):
    package = "qa_review_adapter_" + uuid.uuid4().hex
    sources = {
        "__init__": "from qa_workbench.demo import DemoAdapter\ncalls = 0\nnot_callable = 1\ndef create():\n    global calls\n    calls += 1\n    return DemoAdapter()\n",
        "factory_value": "def create():\n    raise ValueError('bad adapter setting')\n",
        "factory_import": "def create():\n    raise ImportError('factory SDK unavailable')\n",
        "factory_attribute": "def create():\n    raise AttributeError('factory setting missing')\n",
        "dependency_missing": "import qa_review_missing_dependency\n",
        "dependency_import": "raise ImportError('dependency initialization failed')\n",
        "module_value": "raise ValueError('module setting invalid')\n",
        "module_attribute": "raise AttributeError('module setting missing')\n",
    }
    names = {
        "no_separator": package, "empty": "", "empty_module": ":create",
        "empty_factory": package + ":", "missing_module": package + "_absent:create",
        "missing_parent": package + "_absent.child:create", "missing_child": package + ".absent:create",
        "missing_attribute": package + ":absent", "noncallable": package + ":not_callable",
        "valid": package + ":create",
    }
    stderr = io.StringIO()
    result = {"error_type": None, "exit_code": None, "message": ""}
    with tempfile.TemporaryDirectory(prefix="qa-cli-") as directory:
        root = Path(directory)
        (root / package).mkdir()
        for name, source in sources.items():
            (root / package / (name + ".py")).write_text(source, encoding="utf-8")
        try:
            with patch.object(sys, "path", [directory, *sys.path]), redirect_stderr(stderr), patch.dict(
                os.environ, {"QA_REVIEW_TOKEN": "review-fixture-token-at-least-24-characters"}
            ), patch("uvicorn.run") as server:
                importlib.invalidate_caches()
                try:
                    main(["--adapter", names.get(case, package + "." + case + ":create"),
                          "--token-env", "QA_REVIEW_TOKEN", "--archive-root", str(root / "archive")])
                except (ValueError, ImportError, AttributeError, TypeError, SystemExit) as error:
                    result.update(error_type=type(error).__name__, message=str(error),
                                  exit_code=error.code if isinstance(error, SystemExit) else None)
                result["server_calls"] = server.call_count
                result["factory_calls"] = getattr(sys.modules.get(package), "calls", 0)
        finally:
            for name in list(sys.modules):
                if name == package or name.startswith(package + "."):
                    del sys.modules[name]
    return {**result, "stderr": stderr.getvalue()}
