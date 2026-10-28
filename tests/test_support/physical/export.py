"""Contract: scripts/export_project.py source allowlist, ZIP and link preflight.

Clone a small complete project and place synthetic private output beside its
code. Inspect actual ZIP bytes; do not calculate a pass verdict for scripts.
"""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

PRIVATE_MARKER = b"PRIVATE-EXECUTION-EVIDENCE-DO-NOT-EXPORT"


def _fixture(directory):
    root = Path(directory) / "project"
    files = {
        "README.md": "# Project", "BACKEND.md": "# Backend distribution",
        "pyproject.toml": "[project]\nname='project'", "MANIFEST.in": "include README.md",
        "AGENTS.md": "Layered testing rules", "testing.json": "{}", "Dockerfile": "FROM python",
        ".dockerignore": ".venv", ".github/workflows/ci.yml": "name: test",
        "requirements.lock": "fastapi==0.139.0", "requirements-test.lock": "pytest==9.1.1",
        "requirements-dev.lock": "build==1.4.0",
        "src/qa_workbench/service.py": "class Service: pass", "src/qa_workbench/new_feature.py": "VALUE=1",
        "tests/test_example.py": "def test_example():\n    assert True", "docs/architecture.md": "# Architecture",
        "templates/python-project/application.py": "def total(values): return sum(values)",
        "templates/python-project/cart_qa.py": "def create_adapter(): return None",
        "templates/python-project/pyproject.toml": "[project]\nname='cart'",
        "templates/python-project/githooks/pre-commit": "#!/bin/sh\nexit 0",
        "frontend/src/App.vue": "<template>Workbench</template>", "frontend/public/logo.svg": "<svg/>",
        "frontend/tests/client.test.js": "test('client',()=>{})", "frontend/e2e/workbench.spec.js": "test('workbench',()=>{})",
        "frontend/scripts/check.js": "console.log('checked')", "frontend/package.json": "{}",
        "frontend/yarn.lock": "# lock", "frontend/.yarnrc.yml": "nodeLinker: node-modules",
        "frontend/vite.config.js": "export default {}", "frontend/index.html": "<div id='app'></div>",
        "packages/rag-evalkit/README.md": "# Evalkit", "packages/rag-evalkit/IMPLEMENTATION.md": "# Boundary",
        "packages/rag-evalkit/pyproject.toml": "[project]\nname='rag-evalkit'",
        "packages/rag-evalkit/MANIFEST.in": "include README.md",
        "packages/rag-evalkit/src/rag_evalkit/metrics.py": "def recall(): return 1",
        "packages/rag-evalkit/tests/test_metrics.py": "def test_metric():\n    assert True",
        "packages/rag-evalkit/examples/experiment.json": "{}",
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    exporter = Path(__file__).resolve().parents[3] / "scripts/export_project.py"
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(exporter, root / "scripts/export_project.py")
    private = (
        "operator-output/run.json", "operator-exports/reviews.json", "secret-output.env",
        "run.env", ".env", ".ENV.local", "private/identity.json", "reviews/rating.json", "runs/trace.json",
        "src/data/raw.json", "src/private/token.json", "src/run.env", "src/.ENV.private/identity.json",
        "tests/__pycache__/cache.pyc", "frontend/node_modules/vendor/token.json", "frontend/dist/index.html",
        "frontend/operator-output/report.json", "frontend/reviews/labels.json", "frontend/src/run.env",
        "packages/rag-evalkit/reviews/private/key.json", "packages/rag-evalkit/review/human.json",
        "packages/rag-evalkit/custom-output/private.json", "packages/rag-evalkit/runs/trace.json",
        "packages/rag-evalkit/examples/private/calibration.json", "packages/rag-evalkit/examples/run.env",
        "packages/unknown-package/secret.json", "agent-service/app/credentials.py",
    )
    for name in private:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PRIVATE_MARKER)
    spec = importlib.util.spec_from_file_location("export_fixture", root / "scripts/export_project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return root, module


def _inspect(destination):
    with zipfile.ZipFile(destination) as archive:
        names = archive.namelist()
        exposed = any(PRIVATE_MARKER in archive.read(name) for name in names)
    return {"paths": [name.removeprefix("qa-workbench/") for name in names],
            "private_marker_exposed": exposed,
            "all_paths_inside_project": all(name.startswith("qa-workbench/") and ".." not in Path(name).parts for name in names)}


def export_project_sources():
    with tempfile.TemporaryDirectory(prefix="qa-source-export-") as directory:
        root, module = _fixture(directory)
        destination = root / "dist/project.zip"
        count = module.export_project(destination)
        result = _inspect(destination)
        names = result["paths"]
        return {**result, "count": count,
                "private_paths": [name for name in names if any(part in {"private", "review", "reviews", "runs", "data"}
                                                                for part in Path(name).parts)],
                "arbitrary_root_output_included": any(name.startswith(("operator-output/", "operator-exports/", "agent-service/")) for name in names),
                "runtime_environment_included": any(name.lower().endswith(".env") or Path(name).name.lower().startswith(".env") for name in names)}


def _link(target, link):
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
        return "junction"


def export_with_source_link():
    with tempfile.TemporaryDirectory(prefix="qa-export-linked-source-") as directory:
        root, module = _fixture(directory)
        external = Path(directory) / "private-files"
        external.mkdir()
        (external / "identity.json").write_bytes(PRIVATE_MARKER)
        kind = _link(external, root / "src/linked-source")
        destination = Path(directory) / "reviewed-project.zip"
        previous = b"previous-reviewed-export"
        destination.write_bytes(previous)
        try:
            module.export_project(destination)
        except ValueError:
            rejected = True
        else:
            rejected = False
        return {"rejected": rejected, "previous_archive_preserved": destination.read_bytes() == previous,
                "link_kind": kind}


def export_with_dependency_link():
    with tempfile.TemporaryDirectory(prefix="qa-export-linked-dependency-") as directory:
        root, module = _fixture(directory)
        dependency = root / "frontend/node_modules"
        if not dependency.resolve().is_relative_to(root.resolve()):
            raise ValueError("dependency_fixture_escaped_project")
        shutil.rmtree(dependency)
        external = Path(directory) / "dependencies"
        external.mkdir()
        (external / "identity.json").write_bytes(PRIVATE_MARKER)
        _link(external, dependency)
        destination = Path(directory) / "project.zip"
        module.export_project(destination)
        result = _inspect(destination)
        return {"exported": destination.is_file(), "private_marker_exposed": result["private_marker_exposed"],
                "dependency_paths": [name for name in result["paths"] if "node_modules" in Path(name).parts]}
