"""Report publication keeps complete UTF-8 generations under concurrency and failure."""

import pytest
from test_support.actions import report_io as act


def test_report_text_is_utf8_even_with_a_legacy_locale_default():
    result = act.publish_unicode()
    assert result["encoding"] == "utf-8"
    assert result["report"] == {"text": "繁體中文 café 🌏"}
    assert result["text"].endswith("\n")
    assert result["mode"] == result["ordinary_mode"]
    assert result["temporary_files"] == []


def test_concurrent_writers_publish_only_complete_reports_and_remove_their_temporary_files():
    result = act.publish_concurrently()
    assert result["write_errors"] == []
    assert result["read_errors"] == []
    assert result["reads"] > 0
    assert result["published"] in result["candidates"]
    assert len(set(result["temporary_names"])) == result["writes"]
    assert result["temporary_files"] == []


@pytest.mark.parametrize("failure,error_type", [
    ("serialization", "TypeError"), ("write", "OSError"),
    ("replace", "OSError"), ("windows_permanent", "PermissionError"),
    ("windows_other", "PermissionError"),
])
def test_failed_publication_keeps_the_previous_report_and_cleans_partial_files(failure, error_type):
    result = act.fail_publication(failure)
    assert result["error_type"] == error_type
    assert result["report"] == {"generation": "previous"}
    assert result["temporary_files"] == []
    if failure == "windows_permanent":
        assert result["attempts"] == 50
    if failure == "windows_other":
        assert result["attempts"] == 1


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_windows_sharing_violations_retry_the_same_complete_report(winerror):
    result = act.retry_publication(winerror)
    assert result["attempts"] == 3
    assert result["delays"] == [0.01, 0.01]
    assert result["report"] == {"generation": "published"}
    assert result["temporary_files"] == []
