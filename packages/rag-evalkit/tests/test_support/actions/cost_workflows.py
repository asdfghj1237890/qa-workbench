"""Cost and lifetime behavior vocabulary over detached observations."""

from test_support.observed import observed
from test_support.physical import cost_workflows as driver


@observed
def fail_store_construction():
    return driver.constructor_failure()


@observed
def fail_initialization_and_cleanup(failure="ingest_cleanup"):
    return driver.initialization_failure(failure)


@observed
def reuse_failed_pipeline(failure="search"):
    return driver.reused_failures(failure)


@observed
def record_failed_experiment(output, failure="search"):
    return driver.experiment_failure(output, failure)


@observed
def benchmark_failed_requests(failure="ingest"):
    return driver.benchmark_failure(failure)
