"""Pure data contract for detached public test observations."""

from qa_workbench.testing.observations import ObservationPolicy

_POLICY = ObservationPolicy(("test_support.contracts",))


def observed(action):
    return _POLICY.observed(action)
