# Script → action → physical

The template and this project's tests enforce a one-way dependency:

```text
scripts → actions → physical
   ↘         ↓         ↙
      independent contracts
```

Scripts express scenarios through public actions and keep meaningful assertions.
They do not import the application, SDKs, clients, physical adapters or mock
builders, and do not parse transport frames. Expected data may come from contracts.

Actions describe business operations and compose physical calls. They do not do
I/O or import application code. Every public value-returning action or method uses
`@observed`; values are detached data rather than clients, mocks or drivers.
Stateful action objects may privately own drivers.

Physical adapters own application calls, serialization, clocks, mock wiring,
network calls and cleanup. Each module documents a `Contract:` anchor to its
implementation or protocol. They return measurements, not behavioral verdicts.

Contracts own independent data, expectation builders and observation schemas.
`ObservationPolicy` only permits explicitly configured contract dataclasses and
detached built-in values. The contract binding imports the pure validator from
`qa_workbench.testing.observations`; it cannot whitelist arbitrary application
imports.

The configurable checker scans every Python test file, including nested scripts.
It rejects unclassified helpers, dependency reversals, hidden wiring, private
drivers, dynamic import bypasses and misplaced assertions. Lifecycle bridges are
explicitly named fixture-only actions; they yield no client to scripts. There are
no per-file exemptions, baseline lists or inline skip directives.

Use `qa-test-layers --config testing.json`. The configuration names the test root,
support namespace and fixture-only lifecycle actions. `--staged` reads the policy
and test tree from the Git index. NewsCout's host hook additionally loads its
checker adapter and shared checker source from the index; an unstaged clean file
or installed package cannot mask staged violations.

This is a structural guard rather than a Python security sandbox or a quality
score. Review scenario clarity, assertion quality and fixture fidelity separately.
Changing a physical adapter preserves scenarios only when the business contract
remains the same.
