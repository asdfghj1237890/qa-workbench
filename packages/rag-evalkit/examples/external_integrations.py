"""Run installed framework factories with the selected portable replay model.

Install this package's SDK extras and the sibling integrations-plugin package,
then run this file. The installed plugin entry point is also usable with the CLI
through --plugin external_integrations. All calls here are offline and free.
"""

from dataclasses import asdict

from rag_evalkit.models import ReplayModel
from rag_evalkit.registry import Registry
from rag_evalkit.runtime import RunLimits


def main():
    registry = Registry()
    registry.load_plugins(["external_integrations"])
    dataset = {"documents": [{"id": "observatory", "source_id": "observatory-hours",
                              "text": "The observatory opens at nine.", "metadata": {}}]}
    for kind in ("example_langchain", "example_llamaindex"):
        model = ReplayModel(["The observatory opens at nine. [source:observatory-hours]"])
        harness = registry.build("harness", {"type": "example_openai_agents"}, model=model)
        pipeline = registry.build("rag", {"type": kind}, model=model, harness=harness,
                                  dataset=dataset, limits=RunLimits(max_budget_usd=None))
        result = pipeline.run("When does the observatory open?")
        print(kind, asdict(result))


if __name__ == "__main__":
    main()
