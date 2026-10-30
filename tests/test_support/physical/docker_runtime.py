"""Contract: Dockerfile USER and /data/qa-workbench ownership on a fresh named volume."""

import json
import os
import subprocess
import uuid


def validation_enabled():
    return bool(os.environ.get("QA_WORKBENCH_DOCKER_IMAGE"))


def _docker(*arguments):
    return subprocess.run(["docker", *arguments], check=True, capture_output=True, text=True,
                          encoding="utf-8", timeout=60).stdout.strip()


def process_identity():
    image = os.environ["QA_WORKBENCH_DOCKER_IMAGE"]
    return {"uid": int(_docker("run", "--rm", image, "id", "-u")),
            "gid": int(_docker("run", "--rm", image, "id", "-g"))}


def write_mounted_archive():
    image = os.environ["QA_WORKBENCH_DOCKER_IMAGE"]
    volume = "qa-workbench-review-" + uuid.uuid4().hex
    probe = (
        "import json, os; from pathlib import Path; "
        "root = Path('/data/qa-workbench'); report = root / 'acceptance.json'; "
        "report.write_text('繁體中文 archive', encoding='utf-8'); "
        "print(json.dumps(dict(uid=os.getuid(), gid=os.getgid(), directory_owner=root.stat().st_uid, "
        "text=report.read_text(encoding='utf-8'))))"
    )
    _docker("volume", "create", volume)
    try:
        return json.loads(_docker("run", "--rm", "--mount", "type=volume,source=" + volume + ",target=/data/qa-workbench",
                                  image, "python", "-c", probe))
    finally:
        _docker("volume", "rm", volume)
