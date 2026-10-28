"""Reusable strict script/action/physical checker, including Git-index source trees.

This is a structural guard, not proof of meaningful scenario vocabulary. Review
still owns assertion quality and adapter substitutability. No baselines/noqa exits.
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PURE_IMPORTS = {
    "collections",
    "dataclasses",
    "datetime",
    "enum",
    "functools",
    "itertools",
    "logging",
    "math",
    "re",
    "statistics",
    "typing",
    "copy",
    "contextlib",
}
DYNAMIC_CALLS = {
    "__import__",
    "eval",
    "exec",
    "compile",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "vars",
}
PHYSICAL_CALLS = {"open", "breakpoint", "input"}
PHYSICAL_ATTRIBUTES = {
    "monkeypatch",
    "setattr",
    "setenv",
    "delenv",
    "delattr",
    "undo",
    "Mock",
    "MagicMock",
    "AsyncMock",
    "patch",
    "TestClient",
    "Runner",
    "es",
    "admission",
    "requests",
    "read_text",
    "write_text",
    "read_bytes",
    "write_bytes",
    "mkdir",
    "unlink",
    "on_invoke_tool",
    "run_streamed",
    "urlopen",
    "create_task",
    "driver",
}


@dataclass(frozen=True)
class LayerPolicy:
    """Project adapter settings; no skipped files or relaxed layer boundaries."""

    test_root: str = "tests/"
    support_package: str = "test_support"
    lifecycle_actions: tuple[str, ...] = ()
    observation_modules: tuple[str, ...] = ("qa_workbench.testing.observations",)

    def __post_init__(self):
        if not isinstance(self.test_root, str) or not isinstance(self.support_package, str):
            raise TypeError("test_root and support_package must be strings")
        prefix = self.test_root.replace("\\", "/").rstrip("/")
        path = PurePosixPath(prefix)
        if not prefix or path.is_absolute() or ".." in path.parts or ":" in prefix:
            raise ValueError("test_root must be a nonempty relative directory")
        if not self.support_package.isidentifier():
            raise ValueError("support_package must be a Python package name")
        for action in self.lifecycle_actions:
            if not isinstance(action, str):
                raise TypeError("lifecycle actions must be Python names")
            if not action.startswith(self.support_package + ".actions."):
                raise ValueError("lifecycle actions must name public action functions")
            if not all(part.isidentifier() and not part.startswith("_") for part in action.split(".")):
                raise ValueError("invalid lifecycle action")
        if any(not isinstance(name, str) or not name or
               not all(part.isidentifier() for part in name.split("."))
               for name in self.observation_modules):
            raise ValueError("observation modules must be Python names")
        if set(self.observation_modules) - {"qa_workbench.testing.observations"}:
            raise ValueError("only the shared pure observation module may cross the contracts boundary")
        object.__setattr__(self, "test_root", prefix + "/")
        object.__setattr__(self, "lifecycle_actions", tuple(self.lifecycle_actions))
        object.__setattr__(self, "observation_modules", tuple(self.observation_modules))

    @classmethod
    def from_mapping(cls, value):
        """Decode a small data-only project policy; unknown options fail closed."""
        allowed = {"test_root", "support_package", "lifecycle_actions", "observation_modules"}
        if not isinstance(value, dict) or set(value) - allowed:
            raise ValueError("unknown test-layer policy fields")
        for key in ("lifecycle_actions", "observation_modules"):
            if key in value and not isinstance(value[key], list):
                raise ValueError(key + " must be an array of Python names")
        return cls(**value)


DEFAULT_POLICY = LayerPolicy()


def layer_of(path, policy=DEFAULT_POLICY):
    if not path.startswith(policy.test_root):
        return "unclassified"
    relative = path.removeprefix(policy.test_root)
    parts = relative.split("/")
    if parts[:2] == [policy.support_package, "actions"]:
        return "action"
    if parts[:2] == [policy.support_package, "physical"]:
        return "physical"
    if parts[:2] == [policy.support_package, "contracts"]:
        return "contract"
    if parts[-1] == "conftest.py":
        return "fixture"
    if parts[-1] == "__init__.py":
        return "package"
    if parts[-1].startswith("test_") and policy.support_package not in parts:
        return "script"
    return "unclassified"


def imported_modules(node, path, policy=DEFAULT_POLICY):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    module = node.module or ""
    if node.level:
        package = path.removeprefix(policy.test_root).split("/")[:-1]
        if node.level > len(package) + 1:
            return ["<invalid relative import>"]
        module = ".".join(
            package[: len(package) + 1 - node.level] + ([module] if module else [])
        )
    # Include imported children so `from test_support import physical as p` cannot bypass.
    return [module] + [f"{module}.{alias.name}".lstrip(".") for alias in node.names]


def allowed_import(module, layer, policy=DEFAULT_POLICY):
    parts = module.split(".")
    if parts[:1] == [policy.support_package]:
        if len(parts) == 1:
            return True  # each imported child is checked separately
        target = parts[1]
        return target in {
            "script": {"actions", "contracts"},
            "fixture": {"actions", "contracts"},
            "action": {"physical", "contracts"},
            "physical": {"physical", "contracts"},
            "contract": {"contracts"},
            "package": set(),
        }.get(layer, set())
    if layer == "contract" and any(module == name or module.startswith(name + ".") for name in policy.observation_modules):
        return True
    root = parts[0]
    if layer == "physical":
        return not root.startswith("test_") and root not in {
            "tests",
            "actions",
            "harness_actions",
            "sdk_actions",
            "judge_actions",
        }
    return root in PURE_IMPORTS or (root == "pytest" and layer in {"script", "fixture"})


def check_source(path, source, policy=DEFAULT_POLICY):
    layer = layer_of(path, policy)
    findings = []

    def fail(node, message):
        findings.append(f"{path}:{getattr(node, 'lineno', 1)}: {layer}: {message}")

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno}: syntax: {exc.msg}"]
    if layer == "unclassified":
        return [
            f"{path}:1: unclassified: helpers must live in actions, physical, or contracts"
        ]
    if (
        layer == "package"
        and tree.body
        and any(
            not isinstance(n, ast.Expr) or not isinstance(n.value, ast.Constant)
            for n in tree.body
        )
    ):
        fail(
            tree, "package initializers must not hide wiring or re-export dependencies"
        )
    if layer == "physical" and tree.body:
        doc = ast.get_docstring(tree) or ""
        if "contract:" not in doc.lower():
            fail(
                tree,
                "adapter docstring must name its Contract: implementation/protocol anchor",
            )
    doc_constants = {
        id(n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Constant)
        and isinstance(n.value.value, str)
    }
    lifecycle = {name.rsplit(".", 1)[-1] for name in policy.lifecycle_actions}
    for node in ast.walk(tree):
        if (
            layer == "action"
            and isinstance(node, ast.FunctionDef)
            and not node.name.startswith("_")
        ):
            qualified = path.removeprefix(policy.test_root).removesuffix(".py").replace("/", ".") + "." + node.name
            bridge = qualified in policy.lifecycle_actions
            if not bridge and not any(
                isinstance(d, ast.Name) and d.id == "observed"
                for d in node.decorator_list
            ):
                fail(
                    node,
                    "public actions must use @observed to prevent live object leaks",
                )
        if (
            layer == "script"
            and isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in doc_constants
            and re.search(r"https?://", node.value)
        ):
            fail(
                node,
                "URL expectation data belongs in contracts; transport wiring belongs in physical",
            )
        if layer == "script" and (
            (isinstance(node, ast.Name) and node.id in lifecycle)
            or (isinstance(node, ast.Attribute) and node.attr in lifecycle)
        ):
            fail(node, "lifecycle actions belong only in the conftest fixture bridge")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = imported_modules(node, path, policy)
            if (
                layer == "action"
                and any(m.startswith(policy.support_package + ".physical") for m in modules)
                and any(
                    not (alias.asname or "").startswith("_") for alias in node.names
                )
            ):
                fail(node, "physical imports in actions must use private aliases")
            for module in modules:
                if not allowed_import(module, layer, policy):
                    fail(node, f"forbidden dependency {module}")
            if layer in {"script", "fixture"} and any(
                alias.name.startswith("_") or alias.name == "driver"
                for alias in node.names
            ):
                fail(node, "scripts may import only the public action/data interface")
            if any(alias.name == "*" for alias in node.names):
                fail(node, "star imports hide the dependency boundary")
        if (
            layer in {"action", "physical"}
            and isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "AssertionError"
        ):
            fail(node, "behavior assertions belong in scripts; return observations")
        if isinstance(node, ast.Assert) and layer not in {"script", "fixture"}:
            fail(node, "behavior assertions belong in scripts; return observations")
        if layer in {"script", "fixture", "action", "contract", "package"}:
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id
                in (
                    DYNAMIC_CALLS
                    if layer != "contract"
                    else DYNAMIC_CALLS - {"getattr"}
                )
                | PHYSICAL_CALLS
            ):
                fail(node, f"{node.func.id} bypasses the physical boundary")
            if isinstance(node, ast.Name) and node.id in (
                DYNAMIC_CALLS if layer != "contract" else DYNAMIC_CALLS - {"getattr"}
            ) | {"monkeypatch", "mocker"}:
                fail(node, f"{node.id} is physical wiring")
        if layer in {"script", "fixture"}:
            if isinstance(node, (ast.ClassDef, ast.Lambda, ast.AsyncFunctionDef)):
                fail(
                    node, "classes, callbacks and async wiring belong below the script"
                )
            if isinstance(node, ast.FunctionDef):
                if layer == "script" and not node.name.startswith("test_"):
                    fail(
                        node,
                        "scenario helpers belong in actions; expectation builders in contracts",
                    )
                if any(
                    arg.arg in {"monkeypatch", "mocker", "tmp_path", "tmpdir"}
                    for arg in node.args.args
                ):
                    fail(node, "scripts must not receive physical fixtures")
            if isinstance(node, ast.Attribute):
                if node.attr.startswith("_") or node.attr in PHYSICAL_ATTRIBUTES:
                    fail(node, f".{node.attr} exposes physical details")
                if isinstance(node.ctx, (ast.Store, ast.Del)):
                    fail(node, "scripts cannot mutate object attributes")
    return sorted(set(findings))


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def collect(root, staged=False, policy=DEFAULT_POLICY):
    if staged:
        names = (
            git(root, "ls-files", "--cached", "-z", "--", policy.test_root).decode().split("\0")
        )
        return {
            p: git(root, "show", ":./" + p).decode() for p in names if p.endswith(".py")
        }
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in (root / policy.test_root).rglob("*.py")
        if "__pycache__" not in p.parts
    }


def main(argv=None, *, policy=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--staged",
        action="store_true",
        help="check staged content, ignoring working-tree overlays",
    )
    if policy is None:
        parser.add_argument("--config", help="project-relative JSON policy; read from the index with --staged")
        parser.add_argument("--test-root")
        parser.add_argument("--support-package")
        parser.add_argument("--lifecycle-action", action="append")
    args = parser.parse_args(argv)
    if policy is None:
        try:
            if args.config:
                if args.test_root or args.support_package or args.lifecycle_action:
                    parser.error("--config cannot be combined with policy overrides")
                config_path = PurePosixPath(args.config.replace("\\", "/"))
                if config_path.is_absolute() or ".." in config_path.parts or ":" in str(config_path):
                    raise ValueError("config must be a project-relative path")
                raw = git(args.root, "show", ":./" + config_path.as_posix()) if args.staged else (args.root / config_path).read_bytes()
                policy = LayerPolicy.from_mapping(json.loads(raw))
            else:
                policy = LayerPolicy(args.test_root or "tests/", args.support_package or "test_support", tuple(args.lifecycle_action or ()))
        except (ValueError, TypeError, OSError, subprocess.CalledProcessError) as exc:
            parser.error(str(exc))
    try:
        sources = collect(args.root.resolve(), args.staged, policy)
    except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
        print(f"test layers: cannot read complete tree: {exc}", file=sys.stderr)
        return 2
    if not sources or not any(layer_of(p, policy) == "script" for p in sources):
        print(
            "test layers: no scripts found (wrong root or incomplete index)",
            file=sys.stderr,
        )
        return 2
    findings = [
        finding
        for p, source in sorted(sources.items())
        for finding in check_source(p, source, policy)
    ]
    if findings:
        print("\n".join(findings))
        print(f"test layers: FAIL ({len(findings)} violations)")
        return 1
    print(
        f"test layers: OK ({len(sources)} Python files; {'index' if args.staged else 'working tree'})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
