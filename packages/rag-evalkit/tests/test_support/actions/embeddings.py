"""Embedding behavior vocabulary over detached physical observations."""

from test_support.observed import observed
from test_support.physical import embeddings as driver


@observed
def embed_texts(backend="openai", scenario="valid", **options):
    return driver.observe_embeddings(backend, scenario, **options)


@observed
def rejected_configuration(case):
    return driver.observe_configuration(case)


@observed
def live_service_available(backend):
    return driver.live_available(backend)


@observed
def embed_live_texts(backend):
    return driver.observe_live(backend)


@observed
def delayed_body_dispatch(backend="tei", *, inherited=True, scenario="timeout"):
    return driver.observe_dispatch_gate(backend, inherited=inherited, scenario=scenario)


@observed
def timeout_override(backend="tei"):
    return driver.observe_timeout_override(backend)
