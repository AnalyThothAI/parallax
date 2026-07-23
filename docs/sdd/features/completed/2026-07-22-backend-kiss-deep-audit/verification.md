# Verification — Backend KISS whole-chain simplification

**Status**: Verified
**Date**: 2026-07-22
**Owning spec**: `docs/sdd/features/completed/2026-07-22-backend-kiss-deep-audit/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-07-22-backend-kiss-deep-audit/plan.md`
**Branch**: `codex/backend-kiss-deep-audit`
**Worktree**: `.worktrees/backend-kiss-deep-audit/`
**Merged branch**: `main`
**Approved by**: delegated `/goal`, followed by the user's explicit instruction to omit complete `check-all`, merge to `main`, build/start, probe the real chain, and summarize exact gaps
**Approved at**: 2026-07-22
**Base**: `main@c397affb`
**Hard-cut commit**: `a7ad09df`

This record is verified under the current risk-selected evidence contract. The
targeted/static, Docker, physical PostgreSQL, HTTP, and WebSocket checks below
passed; omitted repository-wide lanes remain recorded as historical risks.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - whole-chain classified ownership map | Pass | `uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py` exited 0 after the ownership audit. |
| AC2 - retained single owner/transaction/recovery after cuts | Pass | `uv run pytest -q tests/unit/test_collector_service.py tests/contract/test_provider_protocol_fixtures.py tests/unit/test_token_intent_rebuild_runtime.py tests/integration/test_token_intent_rebuild.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/news_intel/test_news_projection_work.py` exited 0. |
| AC3 - behavior-focused simplified tests | Pass | `uv run pytest -q tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py tests/unit/test_ops_projection_dirty_targets.py tests/unit/test_queue_health.py tests/unit/test_providers_wiring.py tests/unit/domains/asset_market/test_chain_identity.py tests/architecture/test_kiss_runtime_invariants.py` exited 0. |
| AC4 - exact proportional verification | Pass | `make docker-status` exited 0; interrupted or unrun lanes remain explicitly recorded below. |
| AC5 - conflict set preserved and net-negative targeted diff | Pass | `uv run python scripts/validate_sdd_artifacts.py` exited 0 after the reciprocal coordination rule was recorded. |

## Deviations

- Complete `make check-all` was intentionally stopped by user direction after
  its second attempt reached the frontend dependency/toolchain mismatch.
- Real validation found two defects that static gates had not exposed. The scope
  was extended narrowly to the event-token read query and new revision `0188`.
- `tests/integration/test_api_websocket.py` was attempted, hung during the first
  in-process `TestClient` shutdown, and was interrupted after 185.98 seconds;
  zero tests completed. The changed replay path was instead verified against the
  running production image and real PostgreSQL.

## Verification commands

The following blocks preserve the exact task-bound commands and exit status.

```text
$ uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py
............                                                             [100%]
12 passed
exit code: 0
```

```text
$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0
```

```text
$ uv run pytest -q tests/unit/test_worker_base_runtime.py tests/unit/test_run_worker_once.py tests/unit/test_worker_settings.py tests/unit/test_settings.py
........................................................................ [ 77%]
.....................                                                    [100%]
93 passed
exit code: 0
```

```text
$ uv run pytest -q tests/unit/test_collector_service.py tests/contract/test_provider_protocol_fixtures.py tests/unit/test_token_intent_rebuild_runtime.py tests/integration/test_token_intent_rebuild.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/news_intel/test_news_projection_work.py
...........................................                              [100%]
43 passed
exit code: 0
```

```text
$ uv run pytest -q tests/unit/test_provider_capabilities.py tests/unit/test_providers_wiring.py tests/unit/test_binance_usdm_futures_client.py tests/unit/test_okx_clients.py tests/unit/integrations/news_feeds tests/unit/test_queue_terminal.py tests/integration/test_postgres_audit.py
........................................................................ [ 71%]
.............................                                            [100%]
101 passed
exit code: 0
```

```text
$ uv run pytest -q tests/unit/test_providers_wiring.py tests/unit/test_binance_usdm_futures_client.py tests/unit/integrations/news_feeds/test_opennews_client.py tests/unit/test_queue_terminal.py
........................................................................ [ 86%]
...........                                                              [100%]
83 passed
exit code: 0
```

```text
$ uv run pytest -q tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py tests/unit/test_ops_projection_dirty_targets.py tests/unit/test_queue_health.py tests/unit/test_providers_wiring.py tests/unit/domains/asset_market/test_chain_identity.py tests/architecture/test_kiss_runtime_invariants.py
........................................................................ [ 79%]
...................                                                      [100%]
91 passed
exit code: 0
```

```text
$ make docker-status
app: healthy
postgres: healthy
readyz: ok=true
migration_version: 20260722_0188
expected_migration_version: 20260722_0188
migration_status: ready
exit code: 0
```

## Targeted and static verification

| Lane | Result |
|------|--------|
| baseline unit + architecture + contract | `3467 passed, 1 skipped` |
| worker/config | `93 passed` |
| ingest/resolution/Radar/News flow | `43 passed` |
| provider/DB exact | `101 passed` |
| provider failing-first subset | `83 passed` |
| ops/canonicalization/root architecture | `91 passed` |
| resolution + News repository | `30 passed` |
| mypy repair behavior suites | `261 passed`; review subset `165 passed` |
| root architecture | `12 passed` |
| post-live query/schema focused tests | `43 passed` |
| `0187 -> 0188` real PostgreSQL migration integration | `1 passed in 65.73s` |
| post-live factor/Radar suites | `157 passed` |
| `uv run mypy src` | `544 source files` clean |
| Ruff / format / `git diff --check` | pass |
| SDD / subagent-report / generated-index checks | pass after final record generation |

The baseline diagnostic `uv run ruff check --select C90 src tests` reported 36
functions above complexity 10. It is not the configured Ruff gate and was used
only to locate candidates; cohesive domain algorithms were not split solely to
reduce this number.

## Complete `check-all` boundary

`make check-all` did not complete and is not reported as passing:

1. The first attempt exposed strict mypy defects in the refactor. Those defects
   were repaired and `uv run mypy src` subsequently passed.
2. The second attempt passed the Python Ruff/format/mypy stages, then reached
   frontend typecheck with no worktree `node_modules`, missing `vitest/globals`,
   and a mismatched TypeScript 6 toolchain.
3. The user explicitly stopped the complete lane and requested main merge plus
   Docker build/start and real-chain verification instead.

During the independent review, a shell-interpolation mistake invoked
`make check-all`; it exited immediately at the first SDD validation step because
the Task 10 report did not yet exist. No Python, frontend, integration, E2E,
golden, coverage, build, container, or database lane ran in that invocation.

Consequently, no pass claim is made for the full integration suite, formal E2E
golden path, coverage threshold, or complete frontend lint/type/test gate. The
Docker production frontend build did pass as part of both image builds.

## Main merge, build, migration, and startup

`main` was fast-forwarded to `a7ad09df`. `make docker-up` was then run twice:

- the first build proved the merged hard cut could build the Python image,
  Playwright runtime, and production React bundle, migrate through `0187`, and
  start healthy;
- the second build included the live-only repairs and migrated
  `20260722_0187 -> 20260722_0188` successfully;
- app and PostgreSQL containers became healthy;
- `make docker-status` returned exit code 0 with both current and expected
  migration version `20260722_0188` and composition readiness true.

```text
$ make docker-status
app: healthy
postgres: healthy
readyz: ok=true
migration_version: 20260722_0188
expected_migration_version: 20260722_0188
migration_status: ready
exit code: 0
```

`/readyz` is intentionally a storage/schema/composition readiness contract; it
does not disguise degraded external providers as healthy business data.

## Real chain evidence

### GMGN input -> PostgreSQL fact -> HTTP -> WebSocket

A post-build, non-synthetic GMGN direct-WebSocket event was observed:

- event id:
  `gmgn:twitter_monitor_basic:8fd4eb6d-d10f-47f6-80c8-b761a340a02a`;
- provider/transport/channel:
  `gmgn` / `direct_ws` / `twitter_monitor_basic`;
- received at: `1784693966537`;
- the same identity and timestamps existed in PostgreSQL `events`;
- authenticated `/api/recent?limit=1` returned it with HTTP 200 in 61 ms;
- authenticated `/ws` returned `ready`, replayed 20 real events in 259 ms, and
  the latest replay identity matched the HTTP event.

Earlier bounded repetitions after the query fix returned `/api/recent?limit=20`
in 89/33/34/23/22 ms and replayed 100 events in 312 ms.

### Stable current models

- `/api/token-radar` returned HTTP 200 in 149 ms from
  `token_radar_current_rows`, status `fresh`, with 20 serving rows and 72 source
  rows at the final probe.
- A prior real probe matched `market_tick_current` to `/api/live-market`, with
  the same target, observed time, provider, and live status.
- The final `/api/status` call returned HTTP 200 in 22 ms; GMGN was `streaming`,
  and the Radar/current-profile workers were running.

## Live-only defects and hard cuts

### Event-token recent/replay query

Real PostgreSQL exposed two query mistakes that unit doubles did not:

- the event-captured immutable `market_ticks` join omitted the partition key
  `observed_at_ms`;
- the latest fallback scanned the append-only `market_ticks` fact tape instead
  of the existing `market_tick_current` read model.

The query now joins the immutable capture by its full key and uses
`market_tick_current` only for the latest fallback. No index, cache, second
writer, or compatibility branch was added.

### Token Radar factor-cache contract

Revision `0186` made `normalization.cohort_status` mandatory for newly produced
factor snapshots but left old private cache rows in place. The live database had
1,806 invalid cached rows across 1,025 targets; material facts, rank-source edges,
and serving current rows were intact.

Revision `0188` now:

1. unions affected identities from feature cache, current rows, and rank-source
   edges into the existing dirty-target queue with `repair_dirty=true`;
2. clears stale leases/errors/attempts;
3. truncates only `token_radar_target_features`;
4. relies on the existing bounded worker to rebuild from PostgreSQL facts.

At the final snapshot the worker had rebuilt 1,360 feature rows with zero
missing `normalization.cohort_status`; both dirty and repair queues had drained
to zero. All 48 publication sets were `ready` with zero stored errors. This is
completed bounded recovery, not a second migration-time backfill.

## Explicit runtime warnings

The final runtime snapshot was intentionally not all-green:

- `resolution_refresh` and `news_fetch` were running but `degraded`; real
  provider calls returned HTTP 402 in the earlier diagnostic run;
- GMGN remained `streaming`;
- OKX DEX WebSocket repeatedly returned provider code `60029`, cycling through
  reconnect states with no acknowledged subscriptions at the sampled instant;
- `/api/news/sources/status` returned HTTP 500 after 5,208 ms, and the app log
  showed PostgreSQL `QueryCanceled` due to statement timeout.

These are separate provider/physical-query follow-ups. They are not hidden as
`disabled`, repaired with fallback data, or claimed to be regressions from the
KISS hard cut.

## LOC and directory outcome

The directly targeted production/test scope remains net-negative after the
live-only repairs:

| Metric | `main@c397affb` | Final worktree | Change |
|--------|----------------:|---------------:|-------:|
| runtime Python, excluding migrations | 80,192 | 79,414 | -778 |
| Python tests | 85,871 | 84,860 | -1,011 |
| `app/runtime` Python files | 28 | 24 | -4 |
| `app/operations` Python files | 6 | 9 | +3 responsibility moves |

Revision `0188` is additional migration code and is deliberately excluded from
the runtime metric, consistent with the baseline calculation.

## Skipped and unrun gates

- Formal full integration suite: not run.
- Formal E2E/golden path: not run.
- Coverage line/branch thresholds: not run.
- Complete frontend lint/type/test: not run.
- `tests/integration/test_api_websocket.py`: interrupted; zero completed.
- Full `make check-all`: stopped by explicit user direction.

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line | Not run | repository threshold | Not applicable |
| branch | Not run | repository threshold | Not applicable |

## Skipped tests

The baseline non-live lane reported 1 skipped test. A final repository-wide
skipped-test count was not measured because the full gate was intentionally not
run; no zero-skip completion claim is made.

## E2E golden path

The formal golden-path suite was not run. Real production probes are recorded
above and are not substituted for the unchecked formal subprocess contract.

- [ ] /readyz returned 200
- [ ] writer wrote a row visible to a separate process
- [ ] /api/recent returned the injected event
- [ ] WS /ws/live pushed within 5s
- [ ] testcontainers PG and uvicorn subprocess cleaned up

## Independent validation

The fresh Task 10 review-only validator returned `WARN` with no blocking finding.
It passed the Kappa/CQRS ownership review, event-query correctness, `0188`
migration safety, focused tests/lint, conflict coordination, and current Docker
status. WARN is limited to the intentionally absent full repository gates and
the explicit provider/News runtime follow-ups. The validated report is
`docs/generated/subagent-reports/backend-kiss-deep-audit-task-10.md`.

## Remaining follow-ups

- Diagnose the News source-status physical query using current
  `pg_stat_statements`/`EXPLAIN`; do not add serving fallbacks.
- Correct the external OKX authorization/subscription condition and HTTP 402
  provider entitlement outside this refactor; preserve explicit unavailable or
  degraded semantics.
- Continue monitoring the rebuilt Radar cache for contract violations; do not
  add migration-time JSON repair.
