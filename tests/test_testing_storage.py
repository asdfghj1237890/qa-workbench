"""A host can bind storage without changing discovery or retention semantics."""

from test_support.actions import testing


def test_operator_supplied_store_keeps_read_only_discovery_and_retained_restart_evidence():
    result = testing.storage_factory_contract()
    assert result["storage_exists_after_discovery"] is False
    assert result["factory_projects"] == ["example-system", "example-system"]
    assert result["save_calls"] > 0
    assert result["archive_files"] == 1
    assert result["retained_run_ids"] == [result["newest_run_id"]]
    assert result["restored_run_ids"] == result["retained_run_ids"]
