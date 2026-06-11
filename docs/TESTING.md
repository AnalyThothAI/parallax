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
- Makefile pytest targets must fail on an empty pytest collection; do not translate pytest exit code 5 into success for any test lane.
- Business skips are not a long-term state. Do not leave `@pytest.mark.skip` or `pytest.skip(...)` in business tests; move environment-dependent skips into lane conftests or the shared PostgreSQL test harness.

## Harness Test Taxonomy

Architecture tests must declare what kind of harness pressure they apply. A test may appear in more than one class, but the dominant class determines how reviewers judge brittleness:

| Class | Purpose | Expiry condition | Replacement behavior test |
|-------|---------|------------------|---------------------------|
| Permanent invariant | Enforce stable project boundaries such as facts vs read models, router size, worker ownership, and public runtime contracts. | None unless the canonical architecture doc changes in the same PR. | Required before changing or deleting the invariant. |
| Migration tripwire | Prevent a retired table, command, prompt, compatibility layer, or old identity scheme from returning. | Delete or relax only when the replacement has shipped and a behavior contract proves the replacement path. | Required; the test must name the runtime behavior that replaces the old surface. |
| Behavior contract | Assert observable behavior at a boundary without pinning incidental wording, alias names, or call order. | None; prefer refactoring toward this class. | The test itself is the replacement. |
| Generated hygiene | Prove generated files are current, deterministic, and sourced from the expected generator. | None while the generated artifact remains published. | A stale-generation or semantic-content check must replace file-list checks. |

Current architecture test inventory:

| Test file | Class | Review note |
|-----------|-------|-------------|
| `tests/architecture/test_agent_execution_plane_contracts.py` | Permanent invariant | Product LLM agent runtime boundary. |
| `tests/architecture/test_agent_harness_cleanup_contracts.py` | Migration tripwire | Retired agent harness cleanup; keep paired with execution-plane behavior. |
| `tests/architecture/test_agent_input_identity_contracts.py` | Permanent invariant | Input identity and provenance boundaries. |
| `tests/architecture/test_agent_model_capability_contracts.py` | Permanent invariant | Model capability registry contract. |
| `tests/architecture/test_agent_playbook_contracts.py` | Generated hygiene | Agent router, SDD index, and playbook freshness. |
| `tests/architecture/test_api_read_paths_provider_free.py` | Permanent invariant | API reads do not call providers. |
| `tests/architecture/test_cex_oi_kappa_contract.py` | Permanent invariant | CEX OI Kappa/CQRS ownership. |
| `tests/architecture/test_completion_gates.py` | Permanent invariant | Completion evidence requirements. |
| `tests/architecture/test_earnings_hard_delete_contracts.py` | Migration tripwire | Retired earnings runtime surfaces. |
| `tests/architecture/test_equity_runtime_hard_delete_contract.py` | Migration tripwire | Retired equity runtime compatibility. |
| `tests/architecture/test_event_anchor_capture_redesign_contracts.py` | Migration tripwire | Event-anchor redesign hard cut. |
| `tests/architecture/test_harness_structure.py` | Permanent invariant | Documentation harness and SDD lane structure. |
| `tests/architecture/test_macro_kappa_contract.py` | Permanent invariant | Macro Kappa/CQRS boundaries. |
| `tests/architecture/test_macro_no_compatibility_contract.py` | Migration tripwire | Macro compatibility surfaces stay deleted. |
| `tests/architecture/test_news_active_spec_hygiene.py` | Generated hygiene | Active news SDD hygiene. |
| `tests/architecture/test_news_intel_boundaries.py` | Permanent invariant | News domain boundaries. |
| `tests/architecture/test_news_intel_kiss_simplification.py` | Migration tripwire | News simplification hard cut. |
| `tests/architecture/test_no_factor_snapshot_fallback.py` | Migration tripwire | Factor snapshot fallback stays deleted. |
| `tests/architecture/test_notifications_hard_cut.py` | Migration tripwire | Notification hard-cut surfaces. |
| `tests/architecture/test_project_structure.py` | Permanent invariant | Repository and source tree boundaries. |
| `tests/architecture/test_projection_worker_idle_cost_contract.py` | Behavior contract | Idle projection workers avoid broad work. |
| `tests/architecture/test_public_contracts_doc_alignment.py` | Generated hygiene | Public contract docs stay source-aligned. |
| `tests/architecture/test_public_event_token_projection.py` | Behavior contract | Public event token projection contract. |
| `tests/architecture/test_pulse_no_compat.py` | Migration tripwire | Pulse compatibility code stays deleted. |
| `tests/architecture/test_runtime_lifecycle_hard_cut.py` | Migration tripwire | Runtime lifecycle hard cut. |
| `tests/architecture/test_runtime_performance_architecture_hard_cut.py` | Migration tripwire | Runtime performance hard cut. |
| `tests/architecture/test_runtime_worker_constraint_hard_cut.py` | Permanent invariant | Worker runtime constraints. |
| `tests/architecture/test_sdd_artifact_validator.py` | Generated hygiene | Executable SDD artifact truth. |
| `tests/architecture/test_src_domain_architecture.py` | Permanent invariant | Source/domain architecture boundaries. |
| `tests/architecture/test_test_lane_contracts.py` | Permanent invariant | Test lane and taxonomy contract. |
| `tests/architecture/test_token_profile_current_hard_cut.py` | Migration tripwire | Token profile current-row hard cut. |
| `tests/architecture/test_token_pulse_equity_cpu_hard_cut_contract.py` | Migration tripwire | Token pulse CPU hard cut. |
| `tests/architecture/test_token_radar_publication_state_hard_cut.py` | Migration tripwire | Token Radar publication state hard cut. |
| `tests/architecture/test_token_radar_source_width_contract.py` | Permanent invariant | Token Radar source width. |
| `tests/architecture/test_token_radar_sql_surface_inventory_contract.py` | Generated hygiene | Token Radar SQL surface inventory. |
| `tests/architecture/test_token_radar_venue_leaderboard_contract.py` | Behavior contract | Venue leaderboard behavior. |
| `tests/architecture/test_watchlist_agent_hard_cut.py` | Migration tripwire | Watchlist agent hard cut. |
| `tests/architecture/test_worker_inventory_contract.py` | Generated hygiene | Worker inventory lockstep. |
| `tests/architecture/test_worker_manifest_static_contracts.py` | Permanent invariant | Worker manifest static ownership. |
| `tests/architecture/test_worker_runtime_contracts.py` | Permanent invariant | Worker runtime behavior constraints. |

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
`docs/sdd/_templates/verification-template.md` are required.

UI flows that genuinely cannot be exercised by `make check-all` (subjective UX,
animations, real-network behaviour) must be exercised manually and recorded under
`Other commands run` in the verification template.

Macro hard-cut UI/API changes need an additional targeted smoke before final
review when `make check-all` cannot exercise operator data:

```bash
uv run parallax config
uv run parallax db health
uv run parallax macro status
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
settings live in `workers.yaml` rather than application config models. Queue
health tests must keep `worker_manifest.py` queue declarations, dirty-target
ownership, and `app.runtime.queue_health` read-only summaries in sync.

Worker tests must keep external IO outside DB worker sessions. Provider
clients, publishers, wake waits, and other network/process IO cannot run
inside `DBPoolBundle.worker_session()` blocks.

## Worker Development Gates

Worker changes need tests for the runtime contract, not just the happy-path
domain result. Use the smallest lane that exercises each contract:

- Unit tests cover `run_once()` with no work, one claimed target, retryable
  provider failure, terminal failure, cancellation cleanup, and explicit
  no-start backpressure. No-start backpressure must leave dirty/job rows
  unclaimed, not burn attempts, and not write business run ledgers.
- Unit tests call `status_payload()` for any worker that overrides
  `_queue_depth()` or custom details. Queue-depth hooks must be read-only and
  callable by `WorkerBase.status_payload()` with no required arguments.
- Provider wiring tests cover the concrete runtime wrapper for every protocol
  method a worker calls. Fake providers are useful for domain units, but they
  do not prove the real wrapper satisfies the worker contract.
- Integration tests use real PostgreSQL for storage/query/projection behavior:
  claim order, lease release, terminal states, publication state, idempotent
  current-row writes, and stable row counts.
- Architecture tests must be extended when a new worker, queue table, wake
  channel, read model writer, provider protocol, or lifecycle class is added.
  They guard manifest/settings/docs lockstep, no external IO inside DB worker
  sessions, single-writer read models, hard-cut no-compatibility paths, and
  worker status/readiness shape.
- API or runtime-health changes include a `/healthz` and `/readyz` integration
  check. For live/docker verification, also inspect streaming logs for
  Tracebacks, failed workers, queue depth stuck growth, stale migrations, and
  repeated readiness reasons.
- Performance-sensitive projection workers include cardinality and write
  amplification checks: current read-model row counts stay bounded by stable
  product/window keys, unchanged projections write zero serving rows, and idle
  cycles do not run broad fact scans.

These gates would have caught the recent worker regressions earlier: Macro's
generation-based current lifecycle violated stable current-row identity and
bounded idle behavior; the news/equity brief queue-depth drift violated the
`status_payload()` signature; and the narrative provider wrapper passed fake
provider tests while missing concrete audit methods used by the worker.
