"""Business actions; public observations are detached from live store clients."""

from test_support.observed import observed
from test_support.physical.stores import (
    StoreDriver,
    construction_failure,
    existing_index_collision,
    integration_available,
    redirect_observation,
    resolved_postgres_targets,
)


class StoreSession:
    def __init__(self, backend="memory", dimensions=3, ann_metric=None):
        self._driver = StoreDriver(backend, dimensions, ann_metric)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._driver.dispose()

    @observed
    def upsert(self, documents):
        return self._driver.upsert(documents)

    @observed
    def search(self, vector, **settings):
        return self._driver.search(vector, **settings)

    @observed
    def delete(self, ids):
        return self._driver.delete(ids)

    @observed
    def describe(self):
        return self._driver.describe()

    @observed
    def capture(self):
        return self._driver.capture()

    @observed
    def close(self):
        return self._driver.close()

    @observed
    def fault(self, kind):
        return self._driver.fault(kind)

    @observed
    def tamper_owner(self, owner):
        return self._driver.tamper_owner(owner)

    @observed
    def owner(self):
        return self._driver.owner()


@observed
def live_store_available(backend):
    return integration_available(backend)


@observed
def observe_construction_failure(backend):
    return construction_failure(backend)


@observed
def observe_existing_index_collision():
    return existing_index_collision()


@observed
def observe_resolved_postgres_targets():
    return resolved_postgres_targets()


@observed
def observe_database_redirect(status):
    return redirect_observation(status)
