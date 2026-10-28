"""Business vocabulary over detached runtime observations."""

from test_support.observed import observed
from test_support.physical import runtime as driver


@observed
def provider_answer(provider, variant="completed", *, live=False):
    return driver.observe_provider(provider, variant, live=live)


@observed
def tool_journey(provider):
    return driver.observe_tool_journey(provider)


@observed
def guarded_run(provider, guard):
    return driver.observe_guard(provider, guard)


@observed
def failed_tool_run(provider, failure):
    return driver.observe_tool_failure(provider, failure)


@observed
def replay_answer(*, tools=False, cancel_before=False):
    return driver.observe_replay(tools=tools, cancel_before=cancel_before)


@observed
def unknown_cost_run():
    return driver.observe_unknown_cost()


@observed
def rejected_configuration(case):
    return driver.observe_configuration_failure(case)


@observed
def summed_usage():
    return driver.observe_usage_sum()


@observed
def cached_usage(provider):
    return driver.observe_cached_usage(provider)


@observed
def mixed_tool_batch():
    return driver.observe_tool_batch()


@observed
def insufficient_continuation_budget(provider):
    return driver.observe_insufficient_continuation_budget(provider)


@observed
def credential_echo(provider, location):
    return driver.observe_credential_echo(provider, location)


@observed
def safe_mapping_keys():
    return driver.observe_safe_mapping_keys()


@observed
def state_continuation(provider, mode="same"):
    return driver.observe_state_continuation(provider, mode)


@observed
def keylike_tool_journey(provider):
    return driver.observe_keylike_tool_journey(provider)


@observed
def slow_count_runs(repetitions=20):
    return driver.observe_slow_count(repetitions)


@observed
def expired_tool_dispatch():
    return driver.observe_expired_tool_dispatch()


@observed
def custom_request_accounting():
    return driver.observe_custom_request_accounting()


@observed
def enum_type_mismatch():
    return driver.observe_enum_type_mismatch()


@observed
def message_state_validation(role):
    return driver.observe_message_state_validation(role)


@observed
def credential_entry(provider, entry):
    return driver.observe_credential_entry(provider, entry)


@observed
def plain_continuation(provider):
    return driver.observe_plain_continuation(provider)
