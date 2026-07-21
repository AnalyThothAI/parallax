# Testing

Tests prove observable behavior and durable architecture invariants. They do not freeze private function names, source wording, call order, or entire implementation files.

## Lanes

| Lane | Location | Contract |
|---|---|---|
| Unit | `tests/unit/` | deterministic, in-process behavior; no live DSN |
| Architecture | `tests/architecture/` | AST/import/ownership invariants; no network or database |
| Contract | `tests/contract/` | generated/public/provider schemas |
| Integration | `tests/integration/` | real PostgreSQL schema, repositories, workers, and API composition |
| Golden | `tests/golden/` | curated end-to-end data expectations on disposable PostgreSQL |
| E2E | `tests/e2e/` | running service and browser/process boundary |
| Frontend | `web/tests/` | component, model, API, and architecture behavior |

Empty collections and empty parameter sets fail. Business tests are not permanently skipped. Environment setup belongs in the shared lane fixture rather than inside individual tests.

## What to test

Repository and service changes should cover the smallest observable boundary:

- material fact writes validate PostgreSQL mutation evidence;
- unchanged current projections write zero serving rows;
- dirty targets use stable product keys and changed work resets retry state;
- writer acknowledgement and projection replacement are atomic;
- `NOTIFY` loss is recovered by bounded catch-up;
- provider/network/model/filesystem I/O happens outside database transactions;
- external delivery follows claim transaction, I/O, then compare-and-set finalization;
- terminal retry/archive/quarantine preserves audit evidence;
- public read paths use persisted facts/read models and never providers;
- schema hard cuts migrate non-empty predecessor state and fail closed on unexpected shape.

Prefer one concise behavior test over a large source-inspection suite. A hard-delete tripwire is useful only when paired with a positive test for the replacement path. Delete migration-only tripwires after the replacement invariant is covered by a stable architecture or behavior test.

## Permanent architecture checks

`tests/architecture/test_kiss_runtime_invariants.py` is the compact root contract:

- domains do not import `parallax.app`;
- runtime composition does not import transport surfaces;
- worker names and current read-model writers are unique;
- current identities exclude run/generation/attempt/timestamp/UUID keys;
- the manifest uses static factories rather than dynamic import;
- hot API status does not query queues or depend on the queue-health operation.

Additional architecture tests may protect a genuine public or data invariant. They must parse semantics with AST or exercise behavior; do not search for incidental strings across whole source files.

## Worker verification

A new or changed worker needs tests for:

- empty/bounded batch behavior;
- stable claim identity and lease ownership;
- retry and terminal attempt budget;
- idempotent replay/catch-up;
- single-writer ownership;
- transaction boundary and external-I/O separation;
- status/result behavior when degraded or failed.

The canonical inventory is `app/runtime/worker_manifest.py`; `docs/WORKERS.md` records its business ownership. There is no separate generated worker inventory gate.

## Frontend verification

For frontend changes, run the scoped unit/component tests plus:

```bash
npm run lint
npm run typecheck
```

The lint command includes the frontend architecture harness. Owner CSS stays beside its component/route, feature namespaces do not restyle shared internals, and retired global CSS buckets do not return. Run browser E2E only when the task explicitly requires it.

## Completion gates

Choose verification in proportion to the change:

```bash
uv run ruff check src tests
uv run pytest -q tests/unit tests/architecture tests/contract
uv run pytest -q tests/integration
git diff --check
```

Schema or repository changes require the relevant PostgreSQL integration tests when a disposable database is available. Public HTTP shape changes also require the OpenAPI drift test and regenerated frontend types. UI changes require frontend lint, typecheck, and scoped tests.

`make check-all` is the comprehensive release gate; it includes integration, golden, E2E, and coverage work. A task may explicitly narrow this matrix—for example, an operator may request no E2E or no build. Report the omitted lanes plainly rather than faking or weakening them.

Do not add environment skip switches, compatibility mocks, or source-text assertions merely to turn a missing completion gate green.
