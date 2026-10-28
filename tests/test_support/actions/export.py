"""Export business actions return measured archive contents, never file handles."""
from test_support.contracts.observations import observed
from test_support.physical import export as _driver


@observed
def export_project_sources():
    return _driver.export_project_sources()


@observed
def export_with_source_link():
    return _driver.export_with_source_link()


@observed
def export_with_dependency_link():
    return _driver.export_with_dependency_link()
