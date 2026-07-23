# Testing

Tests prove observable behavior and durable architecture invariants. They do
not freeze private function names, source wording, call order, or entire
implementation files.

## Lanes

| Lane | Location | Contract |
|------|----------|----------|
| Unit | `tests/unit/` | Deterministic in-process behavior; no live DSN. |
| Architecture | `tests/architecture/` | AST/import/ownership invariants. |
| Contract | `tests/contract/` | Generated and public schemas. |
| Integration | `tests/integration/` | Real PostgreSQL, repositories, workers, and API composition. |
| Golden | `tests/golden/` | Curated end-to-end data expectations. |
| E2E | `tests/e2e/` | Running service and process boundaries. |
| Frontend | `web/tests/` | UI, model, route, and architecture behavior. |

Empty collections and empty parameter sets fail. Business tests are not
permanently skipped. Environment setup belongs in shared lane fixtures.

## Select tests by risk

Run the smallest command that crosses the changed seam, then add lanes for the
risks introduced by the change:

```bash
make check
make test-unit
make test-architecture
make test-contract
make test-integration
make test-e2e
make test-golden
```

- Schema or repository changes need relevant PostgreSQL integration tests.
- Public HTTP changes need contract drift checks and regenerated frontend types.
- UI changes need frontend lint, typecheck, scoped tests, and browser checks
  when layout or runtime interaction changed.
- Generated files need their generator's `--check` command.
- Documentation-only changes need focused validators and `git diff --check`.

No command is universally mandatory. The plan names the applicable commands,
and verification records what ran and what was omitted.

## Durable invariants

Repository and worker changes should test the highest observable seam:

- material fact writes produce PostgreSQL mutation evidence;
- unchanged current projections write zero serving rows;
- dirty targets use stable product keys and atomic acknowledgement;
- workers recover pending durable work with bounded catch-up;
- external I/O stays outside database transactions;
- public reads use persisted facts/read models and never providers;
- schema hard cuts migrate non-empty predecessor state and fail closed on drift.

`tests/architecture/test_kiss_runtime_invariants.py` is the compact permanent
architecture contract. Add architecture tests only for durable product or data
invariants; prefer behavior tests over source-text tripwires.

## Worker changes

A new or changed worker should cover:

- empty and bounded batches;
- stable claim and lease ownership;
- retry and terminal evidence;
- idempotent replay;
- single-writer ownership;
- transaction and external-I/O separation;
- degraded and failed status behavior.

The canonical inventory is `app/runtime/worker_manifest.py`.

## Honest evidence

Record each verification command with relevant output and exit status. Map
successful commands to acceptance criteria. Report omitted lanes as risks; do
not add skip switches, compatibility mocks, or source-text assertions to
manufacture green results.
