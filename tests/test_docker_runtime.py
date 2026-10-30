"""Opt-in image acceptance runs the same unprivileged identity against a real volume."""

import pytest
from test_support.actions import docker_runtime as act

pytestmark = pytest.mark.skipif(not act.validation_enabled(), reason="set QA_WORKBENCH_DOCKER_IMAGE to a built image")


def test_container_process_uses_the_fixed_unprivileged_identity():
    assert act.process_identity() == {"uid": 10001, "gid": 10001}


def test_fresh_named_volume_preserves_ownership_and_accepts_archive_writes():
    result = act.write_mounted_archive()
    assert result["uid"] == 10001
    assert result["gid"] == 10001
    assert result["directory_owner"] == 10001
    assert result["text"] == "繁體中文 archive"
