"""Archive evidence survives deep operator directories on every supported OS."""
from test_support.actions import archive as act
from test_support.contracts.archive import archive_payloads, windows_path_cases


def test_deep_archive_paths_preserve_atomic_saves_restart_history_and_retention():
    result = act.persist_deep_archive()
    expected = archive_payloads()
    assert result["logical_record_length"] > 360
    assert result["logical_root_preserved"] is True
    assert result["exists_after_discovery"] is False
    assert result["initial_history"] == []
    assert result["loaded"] == expected[-1]
    assert result["history"] == expected[:0:-1]
    assert result["expired"] is None
    assert result["wrong_owner_load"] is None
    assert result["owned_elsewhere"] is True
    assert result["same_owner_elsewhere"] is False
    assert result["record_count"] == 2
    assert result["temporary_count"] == 0


def test_windows_filesystem_paths_preserve_drive_and_unc_authority_idempotently():
    assert act.windows_archive_paths() == [expected for _, expected in windows_path_cases()]
