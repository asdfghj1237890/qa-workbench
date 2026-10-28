"""Public, validated source identity for QA capabilities and execution evidence."""
from __future__ import annotations

import os
import re
from pathlib import Path


def execution_busy(service):
    """All QA execution families share one event-loop admission boundary."""
    return any(getattr(peer, 'active_id', None) is not None
               for peer in (service, *getattr(service, 'peers', ())))


def read_source_sha(version_file=None) -> str | None:
    """Read the health/version VERSION_FILE contract without exposing its content.

    Development, missing, malformed or oversized files identify no source commit.
    Callers capture this value once when a job is accepted; history must not be
    relabelled when the running service's version subsequently changes.
    """
    try:
        with Path(version_file or os.environ.get("VERSION_FILE", "/app/VERSION")).open("rb") as stream:
            raw = stream.read(129)
        if len(raw) > 128:
            return None
        value = raw.decode("utf-8").strip()
    except (OSError, UnicodeError, ValueError):
        return None
    return value.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", value) else None
