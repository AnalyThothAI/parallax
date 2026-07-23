# Plan — Signal Pulse Hard Cut And Architecture Simplification

**Status**: Superseded
**Superseded by**: `docs/ARCHITECTURE.md`
**Date**: 2026-07-21
**Owning spec**: `docs/sdd/features/completed/2026-07-21-signal-pulse-hard-cut/spec.md`
**Worktree**: `main`
**Branch**: `main`
**Approved by**: delegated goal
**Approved at**: 2026-07-21

## Pre-flight

- [x] Spec is approved by delegated goal.
- [x] Work is isolated from the dirty main checkout and the stale Kappa/CQRS worktree.
- [x] `uv run pytest tests/architecture/test_pulse_no_compat.py -q` baseline passes with the feature still present: 59 passed.
- [x] SDD validation passes after repairing the pre-existing AC429/AC448 record defect.
- [x] Generated SDD index check passes.
- [x] `make check` passes; final command evidence is recorded in verification.

Known-failing baseline checks:

- `uv run python scripts/validate_sdd_artifacts.py` fails in the pre-existing active `2026-06-12-kappa-cqrs-governance-root-fix` record because AC429 is not `WHEN ... THEN ... SHALL` shaped and its plan combines `AC429/AC448`, breaking contiguous command numbering.
- `uv run python scripts/regen_sdd_work_index.py --check` reports the pre-existing generated index is stale.

## File-level edits

### Hard-delete architecture guard and migration tests

- Replace Pulse implementation-preservation tests with a hard-delete guard scoped to current runtime, public, config, and frontend surfaces.
- Add head-schema tests proving all current Pulse tables are absent while material facts and supported read models remain.
- Keep historical-migration chain tests only where they verify immutable Alembic history; remove tests that require Pulse at current head.

### `src/parallax/domains/pulse_lab/**` and Pulse integration client

- Delete the full Pulse domain, prompt, query, service, repository, worker, types, and architecture map.
- Delete the Pulse model-execution client and remove only its provider adapter from shared model-execution wiring.

### Runtime, worker, repository and config wiring

- Remove Pulse from bootstrap, provider bundles, worker factories/registry/manifest, repository sessions, DB pool options, queue descriptors/health, diagnostics, settings/default YAML/example YAML, telemetry labels, and the shared agent lane registry.
- Preserve the shared gateway and News model-execution lanes.

### Token Radar, notifications, API and CLI

- Remove Pulse dirty-target fan-out from Token Radar while preserving Token Radar current-row publication and Narrative admission wake/catch-up.
- Remove Signal Pulse notification evaluation, card formatting, rule configuration, and navigation metadata while preserving watchlist and News rules.
- Delete Pulse routes and replay commands; remove Pulse validators, schemas, Token Case overlay, router/parser/handler registration, queue retry branches, and public tests.

### Database migration

- Add Alembic revision `20260721_0184` after `20260713_0183`.
- Purge `signal_pulse_candidate` notifications and their cascading reads/deliveries, plus Pulse source rows in the shared queue-terminal ledger.
- Drop the 13 Pulse tables present at `0183` in foreign-key-safe order without `CASCADE` or broad patterns.
- Make downgrade explicitly irreversible with pre-migration-backup guidance.

### Frontend Live route and contracts

- Delete `web/src/features/signal-lab/**` and its tests/fixtures.
- Remove the Live bottom-deck Lab panel, fixed Pulse polling, query keys, OpenAPI/manual contracts, Token Case overlay, notification navigation, Ops Pulse queue/lane fixtures, and E2E scenarios.
- Move remaining Live selection/task ownership out of global shell state when no cross-route consumer remains; delete dead account-event/Pulse selection unions.
- Preserve Radar/Tape desktop and mobile behavior.

### Canonical docs, audit and generated artifacts

- Update `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/FRONTEND.md`, `docs/RELIABILITY.md`, `docs/WORKERS.md`, `docs/WORKER_FLOW.md`, `docs/AGENT_EXECUTION.md`, domain maps, and current performance/tech-debt docs.
- Add `docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md` with measured keep/remove/defer decisions.
- Remove obsolete generated Pulse reports and regenerate OpenAPI, frontend types, database schema, CLI help, and SDD index.
- Repair the pre-existing AC429/AC448 SDD formatting defect only enough to restore repository-wide SDD validation.

## PR breakdown

1. **PR 1 — Signal Pulse hard cut**: RED guards, database migration, backend/frontend deletion, shared-boundary simplification, docs/audit, generated artifacts, and verification.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: every producer, writer, consumer, schema, config, frontend, test, and generated surface has an owner. |
| Kappa truth is preserved. | Pass: only feature-specific read-model/control/audit state is dropped; material facts and remaining read models are explicit non-targets. |
| Single-writer ownership remains valid. | Pass: removing the Pulse writer and its read models cannot create a second writer; remaining writer mapping is revalidated. |
| Disabled/compatibility code is deleted. | Pass: no feature flag, empty endpoint, ignored config key, alias, redirect, or placeholder is planned. |
| Performance root cause is addressed. | Pass: Token Radar producer fan-out is removed, not merely the disabled consumer; frontend polling and 52 unused indexes/tables are removed. |
| Shared infrastructure has remaining consumers. | Pass: News uses the agent gateway; Token Radar, Narrative admission, notification core, and Live Radar/Tape remain. |
| Parallel touch/conflict sets are explicit. | Pass: this feature coordinates with the active Kappa/CQRS, Macro, and News records for shared docs/generated/runtime/frontend files. |
| Destructive scope is bounded. | Pass: exact Pulse table and shared-row predicates are migration-tested; deployment is not automatic. |

## Rollout order

1. Add RED hard-delete and head-schema tests.
2. Remove upstream producer fan-out, runtime/config/provider/repository wiring, public contracts, and domain implementation.
3. Add the irreversible migration and verify upgrade from `0183` on an isolated PostgreSQL database.
4. Remove frontend polling/UI/state/contracts and run route/component/architecture tests.
5. Update canonical docs and architecture audit; regenerate contract/schema/CLI/index artifacts.
6. Run targeted backend/frontend gates, full `make check-all`, desktop/mobile browser smoke, and independent implementation review.
7. Before deployment, back up PostgreSQL and remove stale operator keys from `~/.parallax/config.yaml` and `~/.parallax/workers.yaml`; deployment itself is outside this code change.

## Rollback

Before merge, revert the branch. After applying migration `0184`, restore a pre-migration database backup and deploy the previous code/config together. Do not downgrade by recreating empty Pulse tables and do not introduce compatibility routes or ignored settings.

## Acceptance test commands

- AC1: `uv run pytest tests/architecture/test_signal_pulse_hard_delete.py -q`
- AC2: `uv run pytest tests/architecture/test_worker_inventory_contract.py tests/architecture/test_agent_execution_plane_contracts.py tests/unit/test_worker_settings.py tests/unit/test_settings.py tests/unit/test_queue_health.py tests/unit/test_ops_diagnostics.py -q`
- AC3: `uv run pytest tests/unit/domains/token_intel/test_token_radar_projection.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_projection_worker_idle_cost_contract.py -q`
- AC4: `uv run pytest tests/integration/test_api_http.py tests/integration/test_cli.py tests/unit/test_notification_rules.py tests/contract/test_openapi_drift.py -q`
- AC5: `cd web && npm run lint && npm run test:architecture && npm run typecheck && npm run test -- --run tests/component/features/live/ui/LivePage.routing.test.tsx tests/routes/notifications.route.test.tsx`
- AC6: `uv run pytest tests/integration/test_postgres_schema_runtime.py::test_runtime_schema_drops_retired_product_tables tests/unit/test_postgres_schema.py::test_signal_pulse_hard_delete_drops_entire_retired_projection_without_cascade -q`
- AC7: `uv run pytest tests/unit/test_postgres_schema.py::test_signal_pulse_hard_delete_drops_entire_retired_projection_without_cascade -q`
- AC8: `make regen-check`
- AC9: `uv run pytest tests/architecture/test_signal_pulse_hard_delete.py::test_architecture_audit_records_measured_hard_cut_evidence -q`
- AC10: `make check-all`

## Verification

Verification evidence lives in `docs/sdd/features/completed/2026-07-21-signal-pulse-hard-cut/verification.md`.
