# QA Workbench backend distribution

The Python wheel and source distribution contain the backend, layered testing
framework, backend tests, documentation and the Python project/adapter template.
They do not bundle the separately built Vue frontend or the independent
`rag-evalkit` distribution. Use the complete-project ZIP or source repository for
the combined frontend, evaluation package, Docker build and project CI.

```sh
python -m pip install qa_workbench-0.1.0-py3-none-any.whl
qa-workbench
```

The default server binds to localhost and runs a synthetic demonstration without
provider calls. Its API is at `/api`; interactive API documentation is at `/docs`.
Use an independently built frontend with `--frontend-dir /path/to/frontend/dist`.

For an installed project adapter:

```sh
qa-workbench --adapter your_system_qa:create_adapter --token-env QA_ACCESS_TOKEN
```

The environment variable holds an operator-provided token. The standalone UI
accepts a token in memory for this session; it is not saved to browser storage.
Embedded hosts may supply their existing authenticated fetch/SSO adapter instead.
For multiple authenticated owners, embed `create_app` or `create_router` with an
identity callback returning each verified owner ID.

The source distribution can run backend and framework validation. Docker-context
and complete-project export checks require the full source ZIP, including its
frontend and independent RAG package:

```sh
python -m pip install -e '.[test]'
qa-test-layers --config testing.json
python -m pytest tests/test_backend.py tests/test_testing_layers.py tests/test_testing_observations.py -q
```

See `docs/adapters.md` and `templates/python-project/README.md` for a real second
system that executes its own layered test suite. Structural success remains
separate from model quality and independent evidence review.
