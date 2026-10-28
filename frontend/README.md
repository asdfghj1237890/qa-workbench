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

The NewsCout adapter lives in `frontend/app/src/adapters/newscoutQa.js` in the host
repository. Firebase, site taxonomy, Cloudflare script loading and project links
are confined there and are absent from this frontend's dependency graph.

`src/index.js` exports the public embedding entry. Import `panel-base.css`,
`qa.css`, `qa-fonts.css`, `qa-typography.css` and Quasar's compiled CSS when
embedding individual panels in a host without those styles.
Shared styles are under `src/css`; licensed font subsets and their original
licenses are under `public/fonts/qa`. Host compatibility entries forward to this
single implementation, so fixes apply to both the host and independent project.
