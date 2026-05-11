# Testing

> **Scope.** Owns testing rules and the verification commands that gate completion. Lane workflow lives in `WORKFLOW.md`; design-discipline rules live in `DESIGN_DISCIPLINE.md`.

## Backend (`src/`, `tests/`)

- Every behaviour change must include a test in `tests/`.
- Bug fixes must include a regression test that fails before the fix and passes after it.
- Integration tests should hit a real PostgreSQL instance (Docker Compose), not mocks, when the change touches storage or query paths.

## Frontend (`web/src/test/`)

- Component and hook tests use Vitest + Testing Library; place them in `web/src/test/`.
- Domain-logic units in `web/src/domain/` should have unit tests independent of React.
- API client wrappers in `web/src/api/` should have contract tests asserting the shapes documented in `CONTRACTS.md`.

## Completion verification

Before claiming work is complete, run:

```bash
make check-all
```

This runs all three gates (lint+type, unit+architecture+contract, integration+e2e+coverage)
and is the only command whose output may be pasted as evidence in a verification artefact.
Exit code 0 + the new `Coverage`, `Skipped tests`, and `E2E golden path` sections in
`docs/superpowers/_templates/verification-template.md` are required.

UI flows that genuinely cannot be exercised by `make check-all` (subjective UX,
animations, real-network behaviour) must be exercised manually and recorded under
`Other commands run` in the verification template.
