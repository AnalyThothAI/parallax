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

- `uv run ruff check .`
- `uv run pytest`
- `uv run python -m compileall src tests`
- (When frontend changed) `cd web && npm run test && npm run build`

UI / live-WebSocket flows that cannot be exercised by tests must be exercised manually before completion. Tests verify code correctness, not feature correctness.
