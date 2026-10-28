"""Detached observations of the public workflows."""

from ..observed import observed
from ..physical import workflows as _driver

runtime_embedding_cli = observed(_driver.runtime_embedding_cli)
runtime_validation = observed(_driver.runtime_validation)
prompt_tools = observed(_driver.prompt_tools)
judge_config_rejection = observed(_driver.judge_config_rejection)
partial_embedding_cost = observed(_driver.partial_embedding_cost)
