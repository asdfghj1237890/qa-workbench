# QA Workbench frontend

This directory builds and runs without the NewsCout checkout. Use Node 22.22.2+
or Node 24+, install dependencies with `yarn install --immutable` using Yarn 4.18.1,
then run `yarn dev`.
Start the Python workbench API separately on `127.0.0.1:8765`; Vite proxies `/api`
to that address. Set `QA_API_PROXY` to use another local backend. `yarn build`
produces `dist/`, which can be served by any static server with an `/api` reverse
proxy. `yarn test` exercises task selection, consent and evidence boundaries;
`yarn e2e` runs the independent Chromium flows and responsive health-history panels.

The default app discovers arbitrary task descriptors from `/api/capabilities`.
Selecting a task only opens settings. Only Start run sends a POST. Paid tasks
require an explicit USD limit and fresh consent. Execution status, structural
checks, semantic review, quality, source revision and evidence kind remain
separate. Logs, cancellation, history, JSON report export/import, hash-bound
reviews and adapter health observations use the same generic API.

When the API requires bearer authentication, its first 401 opens the sign-in
form. Enter the authorized token there; it stays in memory and is cleared by
sign-out, page reload or an authentication failure. Login and task selection only
read configuration and history. No credential is written to browser storage,
project configuration, reports or execution artifacts. Signing out aborts pending
requests and unmounts the previous identity's private execution state.

For an SSO host, set `window.QA_WORKBENCH_CONFIG` before `src/main.js` loads,
with `apiBase`, `projectId`, `name` and an optional async `tokenProvider` or
authenticated `request` function. The host owns identity acquisition; the backend
owns authorization. Keep actual credentials out of configuration files. The
NewsCout embedding continues to use its existing Firebase identity adapter.

## Embedding existing panels

`src/components`, `src/pages/QaPage.vue` and `src/lib/qa*.js` contain the extracted
panel library, including validation, model/corpus evaluation, semantic review,
execution logs/history, health and vector projections. The host calls
`configureQaAdapter` in `src/lib/runtime.js` before mounting the panels and supplies
API transport, identity session, challenge provider, task/evidence descriptions,
branding and category presentation. Project-specific legacy wire formats are
handled by these panels; new systems may implement the generic API instead.

An optional `healthPanel` Vue component adds host-specific, read-only monitoring
above the standard health workspace. Pass a component definition (for example,
`markRaw(MyScheduleStatus)`) through the adapter before mounting. It receives the
`dark` prop and owns its authenticated reads and cleanup. It is not mounted in
design preview. The core health inventory and measurement contract stay unchanged;
the extension must never start work or send model requests when it is mounted.

The NewsCout adapter lives in `frontend/app/src/adapters/newscoutQa.js` in the host
repository. Firebase, site taxonomy, Cloudflare script loading and project links
are confined there and are absent from this frontend's dependency graph.

`src/index.js` exports the public embedding entry. Import `panel-base.css`,
`qa.css`, `qa-fonts.css`, `qa-typography.css` and Quasar's compiled CSS when
embedding individual panels in a host without those styles.
Shared styles are under `src/css`; licensed font subsets and their original
licenses are under `public/fonts/qa`. Host compatibility entries forward to this
single implementation, so fixes apply to both the host and independent project.

## Views and execution composables

`App.vue` assembles the standalone task settings, execution evidence/review,
history and health views under `src/components/workbench/`. Those views accept
data and emit user actions; they do not fetch data or schedule execution.
`StandaloneShell.vue` continues to own identity and authenticated transport.

Execution cores take explicit transport ports and run inside a Vue effect scope,
including in Node without a component, DOM, locale plugin or configured host:

| Composable | Responsibility | Injected dependency |
| --- | --- | --- |
| `useWorkbenchExecution` | Generic task lifecycle, polling, cancellation, logs and evidence transport | `{ client }` implementing `createWorkbenchClient` |
| `useWorkbenchReview` | Review preparation and submission bound to the selected report and row hashes | `{ execution }` report/review port and selection state |
| `useValidationExecution` | Validation modes/consent, deadlines, polling and cancellation | `{ request, base, requestedMode?, security?, onStatus?, onObservation?, onModeChange? }` |
| `useLiveExecution` | Model evaluation consent, polling/backoff, cancellation and review/archive submission | `{ request, base, onStatus?, onObservation? }` |

Each execution core returns `state` (read-only observations), `form` (editable
configuration), `actions` and `lifecycle` (`signal` and idempotent `dispose`).
After construction, call `actions.initialize()` for the workbench or
`actions.refresh()` for the specialized protocols. Stopping the effect scope
aborts requests and clears timers. A late polling or start response cannot restore
an obsolete execution state. Review preparation also checks the selection revision.

`useWorkbenchPanel`, `useValidationPanel` and `useLivePanel` assemble those cores
for Vue views. Components consume four or five groups: `state`, `form`, `ui`,
`actions`, and optional `dom` refs. These presentation modules own locale-dependent
text, visibility, history focus/scrolling and component events. Challenge-widget
handling and browser artifact files have separate adapters; `useArtifactFiles`
owns object URLs and cleanup and accepts an independent file port. Execution cores
receive parsed data or a deferred reader and never access file inputs or anchors.

The original `useWorkbench`, `useValidationRun` and `useLiveEvaluation` exports
remain flat compatibility facades. Their optional transport defaults still use
the configured adapter or `apiFetch`. Existing panel props, events, exposed methods,
HTTP payloads and scoped styles remain intact. Preparing settings never starts a
run or preserves paid consent. ESLint guards execution/review cores against
presentation imports, host singletons and browser globals.

`tests/composables.test.js` exercises the composables through actions and physical
adapters using a Node effect scope, frozen protocol fixtures and fake time. It
covers disposal, late responses after cancellation, transient failures, fresh
consent, review payloads and independent instances. The fake API checks exact
routes, methods, base boundaries, payload keys and types against an independent
contract; unknown requests fail instead of fabricating a queued job.
`tests/artifacts.test.js` separately checks browser file parsing and URL ownership.
The existing component and browser suites verify presentation and public events.

## Sharing browser test helpers

A host that reuses `e2e/observatory-physical.cjs` calls
`createObservatoryPhysical(require("@playwright/test"))` from its own physical
bridge. The factory also binds the nested validation and live helpers to that
same runner, including screenshot output paths and test attachments. Direct
consumers of those modules use `createValidationPhysical` or
`createLiveEvaluationPhysical` with the same host API. The default exports remain
self-contained for this project's own installed Playwright dependencies.

Keep SDK resolution in the physical bridge. For host Vitest component tests,
include `@vue/test-utils` in the host's Vite `resolve.dedupe` alongside Vue and
Quasar so the shared test sources use the host installation. A second dependency
installation inside the vendored source is not required.
