"""Check the portable suite's import direction and application independence.

This is a structural guard, not a sandbox or proof of semantic test quality.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages/rag-evalkit"


def _matches(name, prefixes):
    return any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)


def _module_name(path, root):
    parts = path.relative_to(root).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(node, path, root):
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
        return names, names
    if not isinstance(node, ast.ImportFrom):
        return [], []
    package = list(path.parent.relative_to(root).parts)
    if node.level:
        package = package[:len(package) - node.level + 1]
    else:
        package = []
    module = ".".join([*package, *([node.module] if node.module else [])])
    targets = [".".join(filter(None, (module, alias.name))) for alias in node.names]
    return [module, *targets], targets


def check(package_root=PACKAGE):
    package_root = Path(package_root)
    tests = package_root / "tests"
    paths = sorted(tests.rglob("*.py"))
    scripts = {_module_name(path, tests) for path in paths if path.name.startswith("test_")
               and not path.relative_to(tests).as_posix().startswith(("test_support/actions/", "test_support/physical/"))}
    errors = []
    for path in paths:
        relative = path.relative_to(tests).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        script = _module_name(path, tests) in scripts
        action = relative.startswith("test_support/actions/")
        physical = relative.startswith("test_support/physical/")
        for node in ast.walk(tree):
            names, targets = _imports(node, path, tests)
            if script and any(_matches(name, ("rag_evalkit", "test_support.physical", "app", "unittest.mock")) for name in names):
                errors.append(f"{relative}:{node.lineno}: script bypasses actions")
            if action and any(not _matches(name, ("test_support.observed", "test_support.physical")) for name in targets):
                errors.append(f"{relative}:{node.lineno}: action performs physical work")
            if physical and any(_matches(name, ("test_support.actions", *scripts)) for name in names):
                errors.append(f"{relative}:{node.lineno}: physical reverses dependency")
            if (action and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not node.name.startswith("_")
                    and not any(isinstance(decorator, ast.Name) and decorator.id == "observed" for decorator in node.decorator_list)):
                errors.append(f"{relative}:{node.lineno}: public action requires @observed")
    for path in (package_root / "src/rag_evalkit").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names, _ = _imports(node, path, package_root / "src")
            if any(_matches(name, ("app", "test_support", "firebase_admin")) for name in names):
                errors.append(f"{path.relative_to(package_root)}:{node.lineno}: portable core depends on application")
    return errors


if __name__ == "__main__":
    failures = check()
    for failure in failures:
        print(failure)
    print("EVALKIT-LAYERS: " + ("FAIL" if failures else "PASS"))
    raise SystemExit(bool(failures))
