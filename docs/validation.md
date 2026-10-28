# Validation scope

This project is extracted from an existing host and verified as a separate
installable application. Its core does not import NewsCout, Firebase or a host
repository. The cart example supplies a second system with its own actual layered
pytest tests, fixed task commands, bounded execution and JUnit measurements.

The standalone frontend was copied outside the source repository and installed
with a matching pinned Yarn lock completely offline. Its node_modules is a real
directory; dependency realpaths stay inside the copy. That pre-publication copied snapshot
has source manifest SHA-256
`87a520cb3fb10381e5e9cb2ccfda44996876dd66938de780367ff35283916355`.
That copy passed 391 unit tests (3 existing skips), lint, production build and four
Chromium journeys, including real local HTTP authentication and mobile views.

The pre-publication standalone Python suite passed 58 tests. Later regression
coverage is recorded by the CI run for its exact commit. Backend tests cover another-system adapters, explicit start, strict schema and
paid consent, owner isolation, cancellation, atomic persistence, source identity,
hash-bound report/case review, historical imports, export privacy and no fallback
to a host checkout. The project's locked requirements and complete-source ZIP
support separate installation; wheel/sdist contain the backend scope described
in `BACKEND.md`.

The public CI workflows run independent backend/frontend jobs, installed-wheel
acceptance, and real database/offline SDK integrations. Results are bound to each
commit in [GitHub Actions](https://github.com/asdfghj1237890/qa-workbench/actions);
the local evidence above does not establish remote results for a later commit.
Live model quality, independent human calibration and Docker image builds require
their own evidence.
They cannot be inferred from synthetic examples or successful structural checks.
