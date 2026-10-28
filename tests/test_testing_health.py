"""Health evidence stays explicit, portable and detached from host adapters."""

from test_support.actions import testing


def test_unknown_health_remains_unmeasured_without_fabricated_success():
    row = testing.health_evidence("unknown")
    assert row["id"] == "billing"
    assert row["status"] == "unknown"
    assert row["freshness"] == "unmeasured"
    assert row["observed_at"] is None
    assert row["last_success_at"] is None
    assert row["measurement"]["value"] is None


def test_adapter_status_and_measurement_provenance_are_preserved_independently():
    row = testing.health_evidence("measured")
    assert row["status"] == "critical"
    assert row["reason"] == "probe_failed"
    assert row["source"] == "adapter_probe"
    assert row["observed_at"] == "2026-01-01T12:00:00+00:00"
    assert row["last_success_at"] is None
    assert row["measurement"] == {"key": "response_duration", "value": 15,
                                  "unit": "milliseconds", "threshold": 1000}


def test_mutating_public_health_details_cannot_change_adapter_owned_evidence():
    result = testing.health_evidence("detached")
    assert result["original"] == {"checks": [{"status": "failed"}]}
    assert result["observation"]["details"] == {"checks": [{"status": "changed"}]}


def test_independent_health_reader_needs_no_web_framework_or_host_application():
    result = testing.health_evidence("isolated")
    assert result["unwanted_imports"] == []
    assert result["row"]["id"] == "billing"
    assert result["row"]["status"] == "unknown"
