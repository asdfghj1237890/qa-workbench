"""Publish and inspect detached report generations."""

from test_support.contracts.observations import observed
from test_support.physical import report_io as _driver


@observed
def publish_unicode():
    return _driver.publish_unicode()


@observed
def publish_concurrently():
    return _driver.publish_concurrently()


@observed
def fail_publication(failure):
    return _driver.fail_publication(failure)


@observed
def retry_publication(winerror):
    return _driver.retry_publication(winerror)
