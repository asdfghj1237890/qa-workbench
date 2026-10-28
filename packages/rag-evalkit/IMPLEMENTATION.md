# Implementation boundary

This directory is an installable Python 3.11+ package, independent of NewsCout.
Core imports must never depend on app/, test_support, Firebase, repository paths,
or optional provider SDKs. Optional network adapters use explicit configuration.

Ownership:
- Root: contracts.py, datasets.py, metrics.py, experiments.py, artifacts.py,
  registry.py, cli.py, package metadata, NewsCout bridge, CI, overview docs.
- vector agent: stores/* and test_support/{actions,physical}/stores.py,
  tests/test_stores.py, tests/test_store_integration.py.
- runtime agent: runtime.py, models/*, harnesses/* and runtime test support/tests.
- RAG agent: rag.py, evaluators.py, examples/*, RAG test support/tests, README.md.

Search API is defined by contracts.py. Runtime agent owns model/harness types and
must announce their final public signatures to root and RAG agent immediately.
RAG pipeline must expose describe() and run(query: str), producing answer plus
retrieved document/source evidence and normalized traces/usage. The experiment
runner will call pipeline.run(query) and consume a serializable observation.

Tests follow script -> action -> physical. Test scripts assert observed behavior;
physical helpers perform actual I/O and wiring, never calculate a pass verdict.
Live model/provider requests are opt-in and budget bounded; ordinary tests use
protocol fixtures and must label replay/synthetic evidence explicitly.
Database integration uses uniquely owned ephemeral resources, never production.
Keep raw backend values alongside normalized values. Unsupported is not pass.
