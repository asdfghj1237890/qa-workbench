"""Contract: Dockerfile COPY inputs and ordered .dockerignore source allowlist.

This is a static policy audit of the supported literal/*/** pattern subset,
not a replacement for Docker's context transfer or an actual image build.
"""

import re
import shlex
from pathlib import Path

from test_support.contracts.docker_context import (
    PRIVATE_DOCKER_PATHS,
    REQUIRED_DOCKER_INPUTS,
)

ROOT = Path(__file__).resolve().parents[3]


def _pattern_regex(pattern):
    parts = []
    index = 0
    while index < len(pattern):
        if pattern[index:index + 3] == "**/":
            parts.append("(?:.*/)?")
            index += 3
        elif pattern[index:index + 2] == "**":
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.compile("^" + "".join(parts) + "$")


def _admitted(path, rules):
    names = [path, *(parent.as_posix() for parent in Path(path).parents if parent.as_posix() != ".")]
    included = True
    for rule in rules:
        exception = rule.startswith("!")
        matcher = _pattern_regex(rule.removeprefix("!").strip("/"))
        if any(matcher.fullmatch(name) for name in names):
            included = exception
    return included


def _runtime_sources():
    groups = (("src", {".py"}), ("packages/rag-evalkit/src", {".py", ".md"}),
              ("frontend/src", {".js", ".vue", ".css", ".json"}))
    return [path.relative_to(ROOT).as_posix()
            for prefix, suffixes in groups for path in (ROOT / prefix).rglob("*")
            if path.is_file() and path.suffix in suffixes
            and not {"__tests__", "__pycache__", "private", "review", "reviews", "runs", "data"}.intersection(path.relative_to(ROOT).parts)]


def docker_context_policy():
    rules = [line.strip() for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    copies = []
    for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        if line.startswith("COPY ") and "--from=" not in line:
            copies.extend(shlex.split(line)[1:-1])
    actual = sorted(set(_runtime_sources()) | set(REQUIRED_DOCKER_INPUTS))
    return {
        "rules": rules,
        "copy_sources": copies,
        "denied_copy_sources": [path for path in copies if not _admitted(path, rules)],
        "missing_required_inputs": [path for path in REQUIRED_DOCKER_INPUTS if not (ROOT / path).is_file()],
        "denied_required_inputs": [path for path in actual if not _admitted(path, rules)],
        "admitted_private_paths": [path for path in PRIVATE_DOCKER_PATHS if _admitted(path, rules)],
        "runtime_source_count": len(actual),
    }
