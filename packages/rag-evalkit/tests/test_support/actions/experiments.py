"""Experiment vocabulary with detached observations."""

from ..observed import observed
from ..physical import experiments as _driver

run_example = observed(_driver.run_example)
resume = observed(_driver.resume)
compare_run = observed(_driver.compare_run)
changed_condition = observed(_driver.changed_condition)
invalid_input = observed(_driver.invalid_input)
journal_corruption = observed(_driver.journal_corruption)
concurrent_executor = observed(_driver.concurrent_executor)
interrupted_trial = observed(_driver.interrupted_trial)
cli_outside_repo = observed(_driver.cli_outside_repo)
metric_observations = observed(_driver.metric_observations)
benchmark = observed(_driver.benchmark)
repeat_schedule = observed(_driver.repeat_schedule)
explicit_unsupported = observed(_driver.explicit_unsupported)
hidden_effective_factor = observed(_driver.hidden_effective_factor)
