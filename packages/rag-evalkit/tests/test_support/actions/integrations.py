"""Business vocabulary for real, offline framework integration observations."""

from test_support.observed import observed
from test_support.physical import integrations as driver


@observed
def framework_answer(framework, scenario="answer"):
    return driver.observe_rag(framework, scenario)


@observed
def sdk_agent_run(scenario="answer"):
    return driver.observe_agents(scenario)


@observed
def framework_dependency_isolation():
    return driver.observe_import_isolation()


@observed
def example_rejects_unsupported_factor(framework, factor):
    return driver.observe_example_factor(framework, factor)
