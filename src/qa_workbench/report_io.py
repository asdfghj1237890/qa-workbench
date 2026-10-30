"""Atomic evaluation reports shared by the real CLI and protocol fixtures."""

import json
import os
import sys
import time
import uuid
from pathlib import Path

_WINDOWS = sys.platform == "win32"
_REPLACE_ATTEMPTS = 50
_REPLACE_RETRY_SECONDS = 0.01


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                temporary.replace(path)
                return
            except PermissionError as exc:
                # A concurrent Windows reader can briefly deny rename-over-target.
                # Keep the old report intact and surface permanent failures.
                if (not _WINDOWS or getattr(exc, "winerror", None) not in (5, 32, 33)
                        or attempt == _REPLACE_ATTEMPTS - 1):
                    raise
                time.sleep(_REPLACE_RETRY_SECONDS)
    finally:
        temporary.unlink(missing_ok=True)
