"""Public actions describe durable evidence storage, without owning filesystem I/O."""
from test_support.contracts.observations import observed
from test_support.physical import archive as _driver


@observed
def persist_deep_archive():
    return _driver.persist_deep_archive()


@observed
def windows_archive_paths():
    return _driver.windows_archive_paths()
