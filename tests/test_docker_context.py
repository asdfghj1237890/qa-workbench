"""Docker receives build source while nested private execution artifacts stay out."""
from test_support.actions import docker_context as act


def test_default_deny_context_preserves_every_copy_source_and_runtime_input():
    result = act.inspect_docker_context()
    assert result["rules"][0] == "**"
    assert result["denied_copy_sources"] == []
    assert result["missing_required_inputs"] == []
    assert result["denied_required_inputs"] == []
    assert result["runtime_source_count"] > 70


def test_later_recursive_exclusions_keep_private_outputs_out_of_allowed_trees():
    result = act.inspect_docker_context()
    assert result["admitted_private_paths"] == []
    final_include = max(index for index, rule in enumerate(result["rules"]) if rule.startswith("!"))
    assert all(result["rules"].index(rule) > final_include for rule in (
        "**/review", "**/reviews", "**/private", "**/runs", "**/data", "**/node_modules", "**/.venv", "**/.git", "**/.env",
    ))
