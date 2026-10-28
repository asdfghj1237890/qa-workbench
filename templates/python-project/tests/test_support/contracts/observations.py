"""Pure local binding to the shared detached-observation contract."""

from qa_workbench.testing.observations import ObservationPolicy

_POLICY = ObservationPolicy(("test_support.contracts",))


def observed(action):
    return _POLICY.observed(action)
