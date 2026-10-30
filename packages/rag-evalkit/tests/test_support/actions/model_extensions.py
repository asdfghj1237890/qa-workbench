"""Behavioral vocabulary for model capabilities; physical owns all wiring."""

from test_support.observed import observed
from test_support.physical import model_extensions as physical

EXPECTED_CREDENTIAL = physical.EXPECTED_CREDENTIAL
REQUESTED_MODEL = physical.REQUESTED_MODEL
OBSERVED_MODEL = physical.OBSERVED_MODEL


@observed
def observe_model_identity(provider, actual_mode, *, streaming=False):
    return physical.model_identity_run(provider, actual_mode, streaming)


@observed
def persist_observed_model_identity(output, provider, actual_mode, *, streaming=False):
    return physical.model_identity_experiment(output, provider, actual_mode, streaming)


@observed
def consume_fragmented_credential(provider, channel, fragment_size, *, escaped=False, partial_prefix=False):
    return physical.split_credential_stream(provider, channel, fragment_size, escaped, partial_prefix)


@observed
def stream_answer(provider, mode="normal", *, iterator=False):
    return physical.streaming_run(provider, mode, iterator=iterator)


@observed
def read_progressively_over_http(provider):
    return physical.progressive_loopback(provider)


@observed
def describe_image(provider, mode="url"):
    return physical.image_run(provider, mode)


@observed
def research_with_hosted_tools(mode="normal"):
    return physical.hosted_run(mode)


@observed
def reject_invalid_content(mode):
    return physical.invalid_content(mode)


@observed
def retain_private_reasoning():
    return physical.opaque_stream()


@observed
def fail_after_a_metered_turn():
    return physical.failure_after_paid_turn()
