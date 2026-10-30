# QA Workbench

An independent, adapter-driven testing and QA project. The canonical repository is
[asdfghj1237890/qa-workbench](https://github.com/asdfghj1237890/qa-workbench). It includes the backend, Vue workbench, layered test
framework, a separate RAG evaluation package, examples, tests and CI.

The bundled demonstration uses synthetic evidence and makes no provider requests.
NewsCout integrates through host-owned adapters; it is not required to install,
build or run this project.

Python wheels/source distributions contain the backend and test framework; see
[backend distribution instructions](BACKEND.md). The complete-project ZIP also
contains the frontend, evaluation package, Dockerfile and standalone CI.

## Run locally

Use Python 3.11+, the Node version supported by `frontend/package.json`, and Yarn 4.18.1 (`npm install --global @yarnpkg/cli-dist@4.18.1`).

```sh
python -m venv .venv
# POSIX: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --no-deps -r requirements-test.lock
python -m pip install --no-deps -e . -e ./packages/rag-evalkit
qa-workbench
```

In another terminal:

```sh
cd frontend
yarn install --immutable
yarn dev
```

Open the frontend URL printed by Vite. It proxies `/api` to the local backend at
`http://127.0.0.1:8765`. Choose a task, inspect its settings and press Start. Task
selection and history reads never start execution. Paid tasks require explicit
consent and a bounded budget, even when a project adapter exposes one.

For a single server, build the frontend then serve its output:

```sh
cd frontend
yarn install --immutable
yarn build
cd ..
qa-workbench --frontend-dir frontend/dist
```

The container runs as UID/GID `10001:10001` and owns `/data/qa-workbench`.
New named volumes inherit that directory's ownership. Bind-mounted directories
must be writable by `10001:10001` on the host.

## Connect a system

Implement `ProjectAdapter` with task descriptors, async execution and health
observations. The frontend renders arbitrary task IDs and option schemas. Inject
authentication and project-specific APIs rather than importing them into core.
See [adapter guide](docs/adapters.md), [architecture](docs/architecture.md) and the
[strict test template](templates/python-project/README.md).

```sh
qa-workbench --adapter your_system_qa:create_adapter --token-env QA_ACCESS_TOKEN
```

`QA_ACCESS_TOKEN` is an operator-provided environment variable. For multi-user SSO,
mount `create_router(service, authenticate)` in your host and return its verified
owner ID. NewsCout's host adapter demonstrates Firebase ownership, real ES/API
validation, model evaluation, corpus evaluation and its existing semantic review
workflows. Its generic API is mounted at `/qa/workbench`; specialized panels keep
their existing project APIs.

## Verify

```sh
qa-test-layers --config testing.json
python scripts/check_evalkit_layers.py
python -m pytest tests -q
python -m pytest packages/rag-evalkit/tests -q
cd frontend
yarn lint
yarn test
yarn build
```

Run the two Python suites as separate commands because each owns its own
`test_support` namespace. Database integration, external framework integration,
live model evaluation and human calibration have explicit, separate requirements;
see the [evaluation package](packages/rag-evalkit/README.md). Normal tests do not
start paid calls. Structural success and synthetic examples are not semantic
quality acceptance.

## Move this project

```sh
python scripts/export_project.py --output dist/qa-workbench.zip
```

The archive contains this project's source and its independent RAG package. It
excludes Git metadata, dependency environments, caches, build output, run data and
environment files. Unzip it anywhere, initialize a repository if desired, and use
the same install/build/test commands. No source path outside the extracted folder
is needed.

## Evidence and persistence

Each authenticated owner can see only their runs. Reports and case reviews bind to
exact SHA-256 hashes; source revisions, partial results, skipped work, sanitized
logs and cancellation remain inspectable. Atomic archives retain bounded history.
Restarting restores evidence and marks abandoned executions interrupted; it does
not rerun a job. Imported evidence stays historical and cannot certify the current
release. Real-world quality still needs independent human review and calibration.
