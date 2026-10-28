# Layered tests for a new system

This template has no NewsCout dependency. Copy this directory to your own project,
install an approved QA Workbench wheel or local checkout, then run:

```sh
python -m pip install /path/to/qa-workbench
python -m pip install pytest
python -I -m qa_workbench.testing.layers --config testing.json
python -m pytest tests -q
```

This template is also an installable second system, not only a test skeleton.
From the copied project directory, install its adapter and connect the workbench:

```sh
python -m pip install -e .
# Set QA_ACCESS_TOKEN to your own random secret of at least 24 characters.
qa-workbench --adapter cart_qa:create_adapter --token-env QA_ACCESS_TOKEN
```

Open the standalone workbench frontend and use its authenticated API client.
The `cart-regression` task first checks this project's architecture, then starts
a real pytest subprocess and captures measured JUnit rows and sanitized logs.
The command is fixed; web callers cannot choose commands, paths or environment
variables. Reading capabilities or health never runs tests. Timeout and cancel
stop the owned pytest process; the sample does not create background children.
Systems adding such workers must supply their platform's process ownership and
cleanup contract. The subprocess receives a small fixed environment without
provider keys, QA access tokens or live-evaluation flags.

The factory resolves the project from its launch directory; its code may be
installed as a wheel or editable module while tests stay in the copied project.
`application.py` is real sample business code and assertions remain in test
scripts. Successful offline tests are structural evidence; they do not establish
live-system or model quality, and the platform keeps quality acceptance false.

`application.py` is a tiny sample system. Replace it with your application, adapt
`tests/test_support/physical/cart.py`, and write your business vocabulary in
`actions/cart.py`. Keep meaningful expected behavior and assertions in
`tests/test_cart.py`. A new domain normally requires new scripts/actions; changing
only a database adapter within the same domain can preserve both interfaces.

`testing.json` names your test root, support package and any explicitly reviewed
fixture-only lifecycle actions. The checker scans the entire tree; there are no
legacy exceptions, per-file skips or inline bypasses. Contracts may import the
shared pure observation policy; scripts and actions must use the local contract
binding. Physical modules document the actual implementation/protocol in a
`Contract:` docstring and return measurements instead of pass/fail verdicts.

The optional `githooks/pre-commit` uses an installed, pinned checker in isolated
Python mode and reads both project policy and test sources from the Git index.
On POSIX systems, run `chmod +x githooks/pre-commit` before enabling the hook.
Integrate it with any existing hooks rather than overwriting them. The host
project must pin the installed QA Workbench distribution in its environment.
To develop the checker itself, use QA Workbench's own staged-core regression
checks; do not replace an installed release with an unreviewed local import.
