"""A complete source export must never publish private execution artifacts."""
from test_support.actions import export as act
from test_support.contracts.export import REQUIRED_SOURCE_PATHS


def test_export_preserves_the_complete_project_source_and_build_inputs():
    result = act.export_project_sources()
    assert set(REQUIRED_SOURCE_PATHS) <= set(result["paths"])
    assert result["count"] == len(result["paths"])
    assert result["all_paths_inside_project"] is True


def test_export_excludes_reviews_secrets_and_arbitrary_operator_output_folders():
    result = act.export_project_sources()
    assert result["private_marker_exposed"] is False
    assert result["private_paths"] == []
    assert result["arbitrary_root_output_included"] is False
    assert result["runtime_environment_included"] is False


def test_nonexcluded_source_links_reject_export_and_preserve_the_previous_archive():
    result = act.export_with_source_link()
    assert result["rejected"] is True
    assert result["previous_archive_preserved"] is True
    assert result["link_kind"] in {"symlink", "junction"}


def test_excluded_dependency_links_do_not_prevent_source_export():
    result = act.export_with_dependency_link()
    assert result["exported"] is True
    assert result["dependency_paths"] == []
    assert result["private_marker_exposed"] is False
