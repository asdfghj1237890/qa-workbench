"""Export reviewed source locations, never arbitrary operator output folders."""

import argparse
import os
import tempfile
import zipfile
from pathlib import Path

EXCLUDED = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".ruff_cache", "dist", "build", "runs", "data", "test-results",
    "playwright-report", ".DS_Store",
    ".yarn-global", ".yarn", ".quasar", "review", "reviews", "private",
    "run", "cache", ".cache", "coverage", "htmlcov", ".tox", ".nox",
}
ROOT_FILES = {
    "README.md", "BACKEND.md", "AGENTS.md", "pyproject.toml", "MANIFEST.in",
    "testing.json", "Dockerfile", ".dockerignore", ".gitignore", ".gitattributes",
    "compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml",
    "LICENSE", "LICENSE.md", "CHANGELOG.md", "Makefile", "uv.lock",
    "requirements.txt", "requirements.lock", "requirements-dev.txt", "requirements-test.lock", "requirements-dev.lock",
}
ROOT_DIRECTORIES = {"src", "tests", "docs", "scripts", "templates", ".github"}
FRONTEND_FILES = {
    "README.md", "package.json", "yarn.lock", "package-lock.json", "pnpm-lock.yaml",
    ".yarnrc.yml", ".gitignore", "index.html", "vite.config.js", "vite.config.ts",
    "vitest.config.js", "vitest.config.ts", "playwright.config.js", "playwright.config.ts",
    "eslint.config.js", "tsconfig.json", "tsconfig.node.json",
}
FRONTEND_DIRECTORIES = {"src", "public", "tests", "e2e", "scripts"}
PACKAGE_FILES = {
    "README.md", "IMPLEMENTATION.md", "MANIFEST.in", "pyproject.toml", ".gitignore",
    "LICENSE", "LICENSE.md", "CHANGELOG.md", "uv.lock",
    "requirements.txt", "requirements.lock",
}
PACKAGE_DIRECTORIES = {"src", "tests", "examples", "docs"}
PRIVATE_SUFFIXES = {".pyc", ".pyo", ".log", ".env", ".sqlite", ".sqlite3", ".db",
                    ".pem", ".key", ".p12", ".zip", ".tar", ".tgz", ".gz"}
EXCLUDED_NAMES = {name.lower() for name in EXCLUDED}


def _allowed(relative, *, directory=False):
    parts = relative.parts
    if any(part.lower() in EXCLUDED_NAMES or part.lower().endswith(".egg-info")
           or part.lower().startswith((".env", ".test-tmp", ".pytest")) for part in parts):
        return False
    if not directory and (relative.suffix.lower() in PRIVATE_SUFFIXES
                          or relative.name.lower().startswith(".env")):
        return False
    first = parts[0]
    if first in ROOT_DIRECTORIES:
        return True
    if first == "frontend":
        return (directory if len(parts) == 1 else
                parts[1] in FRONTEND_DIRECTORIES or len(parts) == 2 and not directory
                and parts[1] in FRONTEND_FILES)
    if first == "packages":
        if len(parts) == 1:
            return directory
        if parts[1] != "rag-evalkit":
            return False
        if len(parts) == 2:
            return directory
        return (parts[2] in PACKAGE_DIRECTORIES or len(parts) == 3 and not directory
                and parts[2] in PACKAGE_FILES)
    return len(parts) == 1 and not directory and first in ROOT_FILES


def _linked(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _sources(root, destination):
    files = []
    for directory, children, filenames in os.walk(root, topdown=True, followlinks=False):
        folder = Path(directory)
        children[:] = sorted(name for name in children
                             if _allowed((folder / name).relative_to(root), directory=True))
        for name in children:
            child = folder / name
            if _linked(child):
                raise ValueError(f"Export refuses linked directory: {child.relative_to(root)}")
        for name in sorted(filenames):
            path = folder / name
            relative = path.relative_to(root)
            if not _allowed(relative) or path.absolute() == destination:
                continue
            if _linked(path):
                raise ValueError(f"Export refuses symlink: {relative}")
            if path.is_file():
                files.append((path, relative))
    return files


def export_project(destination: Path) -> int:
    root = Path(__file__).resolve().parents[1]
    if destination.is_symlink():
        raise ValueError("Export refuses a linked destination")
    destination = destination.resolve()
    # Preflight all source links before creating a publishable archive.
    sources = _sources(root, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".qa-export-", suffix=".tmp", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, relative in sources:
                archive.write(path, "qa-workbench/" + relative.as_posix())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return len(sources)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "dist/qa-workbench.zip")
    args = parser.parse_args()
    print(f"Exported {export_project(args.output)} files to {args.output.resolve()}")


if __name__ == "__main__":
    main()
