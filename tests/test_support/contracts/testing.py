"""Data-only contracts for the reusable test architecture."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TestingObservation:
    items: list


VALID_SCRIPT = "from quality_support.actions import orders\ndef test_order():\n    assert orders.total() == 12\n"

POLICY_CASES = [
    ("script_imports_application", "forbidden dependency application"),
    ("script_imports_physical_alias", "forbidden dependency quality_support.physical"),
    ("relative_physical_import", "forbidden dependency quality_support.physical"),
    ("action_exposes_driver", "must use private aliases"),
    ("action_missing_observation", "public actions must use @observed"),
    ("physical_hides_assertion", "behavior assertions belong in scripts"),
    ("physical_missing_contract", "Contract:"),
    ("script_calls_lifecycle", "lifecycle actions belong only"),
    ("unclassified_helper", "unclassified"),
    ("package_reexport", "package initializers"),
    ("script_imports_observation_implementation", "forbidden dependency qa_workbench"),
]
