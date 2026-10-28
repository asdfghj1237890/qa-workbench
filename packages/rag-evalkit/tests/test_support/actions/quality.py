"""Detached quality and end-to-end load observations."""

from ..observed import observed
from ..physical import quality as _driver

review_scenario = observed(_driver.review_scenario)
calibration_scenario = observed(_driver.calibration_scenario)
model_judge = observed(_driver.model_judge)
live_judge_stub = observed(_driver.live_judge_stub)
synthetic_marker = observed(_driver.synthetic_marker)
benchmark_scenario = observed(_driver.benchmark_scenario)
cli_review = observed(_driver.cli_review)
cli_calibration = observed(_driver.cli_calibration)
