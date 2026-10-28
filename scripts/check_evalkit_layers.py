"""Check the portable suite's import direction and application independence.

This is a structural guard, not a sandbox or proof of semantic test quality.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages/rag-evalkit"


def check():
    errors = []
    for path in (PACKAGE / "tests").rglob("*.py"):
        relative = path.relative_to(PACKAGE / "tests").as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        script = path.name.startswith("test_") and "/" not in relative
        action = relative.startswith("test_support/actions/")
        physical = relative.startswith("test_support/physical/")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if script and any(name.startswith(("rag_evalkit", "test_support.physical", "app", "unittest.mock")) for name in names):
                errors.append(f"{relative}:{node.lineno}: script bypasses actions")
            if action and any(name.startswith(("rag_evalkit", "app", "subprocess", "urllib", "sqlite3", "pathlib", "os")) for name in names):
                errors.append(f"{relative}:{node.lineno}: action performs physical work")
            if physical and any("actions" in name or name.startswith("test_") for name in names):
                errors.append(f"{relative}:{node.lineno}: physical reverses dependency")
    for path in (PACKAGE / "src/rag_evalkit").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            if any(name.split(".")[0] in {"app", "test_support", "firebase_admin"} for name in names):
                errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: portable core depends on application")
    return errors


if __name__ == "__main__":
    failures = check()
    for failure in failures:
        print(failure)
    print("EVALKIT-LAYERS: " + ("FAIL" if failures else "PASS"))
    raise SystemExit(bool(failures))
