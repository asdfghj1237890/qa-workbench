# QA Workbench contributor contract

Read docs/testing-framework.md before changing tests. Keep test scripts, actions,
physical adapters and independent contracts separate. Scripts own meaningful
assertions; actions describe operations and return detached observations;
physical modules own application calls, I/O and fixture cleanup and document a
`Contract:` anchor. Never hide a whole test or its verdict in a physical adapter.

The core and frontend must not import a host application, its authentication SDK,
business taxonomy, repository paths or production credentials. Host-specific code
belongs in an explicitly injected adapter. A bundled example must work after this
directory is copied outside its source repository.

Reading capabilities or selecting a task never executes work. Starting paid work
requires explicit acknowledgement, budget and limits. Keep execution, structural
checks, semantic reviews, stale/partial evidence and historical imports distinct.
No live paid evaluations run during ordinary tests or CI.
