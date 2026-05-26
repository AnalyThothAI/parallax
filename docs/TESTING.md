# Testing

> **Scope.** Owns testing rules and the verification commands that gate completion. Lane workflow lives in `WORKFLOW.md`; design-discipline rules live in `DESIGN_DISCIPLINE.md`.

## Backend (`src/`, `tests/`)

- Every behaviour change must include a test in `tests/`.
- Bug fixes must include a regression test that fails before the fix and passes after it.
- Test files must live in an explicit lane. Do not add root-level `tests/test_*.py` files.
- Unit tests live under `tests/unit/`. They must be deterministic, in-process, and must not reference live DSNs or `connect_postgres_test`.
- Integration tests should hit a real PostgreSQL instance through the project test harness when they touch storage, query paths, worker runtime behavior, API read models, or derived read-model writes. They live under `tests/integration/` and may use fake external providers/clients. Do not replace runtime repositories with `FakeRuntime`, `FakeRepository`, or `without_postgres` in integration tests.
- Architecture tests live under `tests/architecture/`. They enforce repository structure, lane boundaries, and other static contracts. They should not require network services.
- Contract tests live under `tests/contract/`. They protect public surfaces such as OpenAPI, provider schema drift, and other documented IO contracts. Provider live drift checks are opt-in diagnostics and are not required for normal CI.
- E2E tests live under `tests/e2e/`. They exercise the running service boundary and may use testcontainers, subprocesses, and real PostgreSQL.
- Golden tests live under `tests/golden/`. They exercise curated corpus expectations against the real ingest/projection pipeline, provision PostgreSQL like integration tests, and are covered by `make check-all`.
- Business skips are not a long-term state. Do not leave `@pytest.mark.skip` or `pytest.skip(...)` in business tests; move environment-dependent skips into lane conftests or the shared PostgreSQL test harness.

## Frontend (`web/tests/`)

- Component and hook tests use Vitest + Testing Library; place them in `web/tests/component/` or `web/tests/unit/` per the layout in `docs/FRONTEND.md`.
- Pure model and helper units under `web/src/features/<name>/model/` and `web/src/shared/` should have unit tests independent of React, placed in `web/tests/unit/` mirroring the source path.
- Feature API hooks under `web/src/features/<name>/api/` and the typed client under `web/src/lib/api/` should have contract tests asserting the shapes documented in `CONTRACTS.md`.
- Frontend architecture harness tests live under `web/tests/architecture/`.
  `npm run lint` runs both ESLint and this harness. CSS and responsive work
  must keep these gates green: side-effect CSS must be locally imported by its
  owner, feature class names must stay in their namespace, shared UI selectors
  cannot be redefined by features, and retired global CSS buckets cannot return.

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

Macro hard-cut UI/API changes need an additional targeted smoke before final
review when `make check-all` cannot exercise operator data:

```bash
uv run gmgn-twitter-intel config
uv run gmgn-twitter-intel db health
uv run gmgn-twitter-intel macro status
```

Record only redacted paths, booleans, migration status, history readiness,
coverage, and data-gap summaries. Do not paste full config JSON, handles,
tokens, provider URLs with credentials, API keys, or secret-bearing DSNs.
Manual macro page verification should cover `/macro`, `/macro/assets`,
`/macro/rates`, `/macro/fed`, `/macro/liquidity`, `/macro/volatility`,
`/macro/credit`, and `/macro/assets/crypto-derivatives`, with checks that raw
concept keys, raw gap codes, JSON provenance, and old v1/v3 field names are not
visible.

## Worker inventory

Cross-domain runtime worker inventory (fact writes, wake channels, catch-up
cadence) lives in `app/runtime/worker_manifest.py` and is documented in
`docs/WORKERS.md`. A new worker must appear in the manifest, in that inventory,
in `WorkersSettings` / the default `workers.yaml`, and in the owning domain's
`ARCHITECTURE.md` in the same change. All long-running workers must
inherit `WorkerBase`; `IngestService` is a transactional service, not a
worker.

Architecture guards enforce that `worker_manifest.py`,
`WorkersSettings`, `workers.yaml`, and the `docs/WORKERS.md`
`worker-inventory-keys` marker stay in lockstep. They also guard that
`/readyz` and `/api/status` expose worker state under the `workers` map
instead of old top-level worker sections, and that worker runtime
settings live in `workers.yaml` rather than application config models.

Worker tests must keep external IO outside DB worker sessions. Provider
clients, publishers, wake waits, and other network/process IO cannot run
inside `DBPoolBundle.worker_session()` blocks.
