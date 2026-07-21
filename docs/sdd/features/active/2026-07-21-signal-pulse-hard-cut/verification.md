# Verification — Signal Pulse Hard Cut And Architecture Simplification

**Status**: In Progress
**Date**: 2026-07-21
**Owning spec**: `docs/sdd/features/active/2026-07-21-signal-pulse-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-07-21-signal-pulse-hard-cut/plan.md`
**Branch**: `codex/signal-pulse-hard-cut`
**Worktree**: `.worktrees/signal-pulse-hard-cut`
**Approved by**: delegated goal
**Approved at**: 2026-07-21

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — domain/runtime hard delete. | Pass | Backend hard-delete guard rejects current Pulse domain, client, worker, repositories and wiring; 3/3 passed. |
| AC2 — worker/config/agent-lane removal. | Pass | Worker/config/gateway tests retain News execution and remove `pulse_candidate` / `pulse.decision`. |
| AC3 — Token Radar producer removal. | Pass | Projection tests and source scans prove no Pulse dirty-target fan-out; Narrative wake/catch-up remains. |
| AC4 — public/notification removal. | Pass | Routes, CLI, schemas, overlay and notification rule are absent; generated OpenAPI drift check passes. |
| AC5 — frontend removal and Live simplification. | Pass | Frontend guard 4/4, Vitest 694/694, build, and desktop/mobile Playwright paths pass without Pulse requests. |
| AC6 — exact database hard delete. | Pass | Non-empty real-PostgreSQL 0183→0184 test drops all 13 tables/shared Pulse rows and preserves `events` plus Token Radar current rows. |
| AC7 — explicit irreversible downgrade. | Pass | Static migration test requires backup guidance and rejects `CASCADE` / compatibility recreation. |
| AC8 — docs/generated alignment. | Pass | OpenAPI, frontend types, DB schema, CLI help, worker/docs and generated-artifact checks pass. |
| AC9 — measured architecture audit. | Pass | Chinese audit records measured code, request, relation/index/WAL cost and keep/remove/defer decisions. |
| AC10 — full verification. | In progress | `make check-all` passed every stage through golden tests; the final coverage stage was interrupted on the user's instruction to merge and deploy directly. |

No implementation deviation was accepted. The only verification exception is the explicitly user-directed omission of the final coverage rerun after all functional gates passed.

## Baseline and measured evidence

- Before the cut: 51 dedicated Python files / 13,298 lines; 42 Pulse-named test files / 19,206 lines; eight dedicated frontend files / 1,055 lines.
- Read-only live baseline: 14 Pulse relations, 52 indexes, 35,561,472 bytes, 21,172 all-due dirty targets, 570 producer upserts, 2,703 rows and 6,193,803 WAL bytes in the observed stats window.
- Frontend baseline: three Pulse queries produced approximately 11 requests/minute/client even while the panel was not the active business surface.

## Verification commands

```text
uv run pytest -q tests/architecture
1224 passed

cd web && npm run lint && npm run format:check && npm run typecheck
15 architecture files / 183 tests passed; ESLint, Prettier and TypeScript passed

cd web && npm run test -- --run && npm run build
99 files / 694 tests passed; production Vite build passed

npx playwright test <five affected golden-path specs>
41 passed, 39 device-conditional skipped across desktop-1366, desktop-1920,
tablet-834, mobile-390 and mobile-430

uv run pytest <non-empty migration + no-CASCADE contract>
2 passed

make check-all
SDD validation/index/generators: passed
Ruff/format/mypy/frontend/check: passed
unit + architecture + contract: 7067 passed, 2 explicit conditional skips
integration: 408 passed in 1625.56s
backend E2E: 5 passed
golden corpus: 4 passed
coverage: interrupted before collection at explicit user request to merge/deploy
```

The two fast-lane skips were explicit: a unit path requiring an opt-in PostgreSQL service on port 55432 and the opt-in live GMGN provider drift test. The real PostgreSQL integration lane ran separately and passed all 408 tests.

## Coverage

The final coverage rerun was interrupted before collection at the user's explicit request to merge and deploy directly. Functional, integration, backend E2E and golden gates had already passed.

## Skipped tests

- One fast-lane unit path requires an opt-in PostgreSQL service on port 55432; the complete real-PostgreSQL integration lane passed 408/408 separately.
- The GMGN provider-drift test is opt-in via `GMGN_PROVIDER_DRIFT=1` and was not enabled.

## E2E golden path

- [x] `/readyz` returned 200.
- [x] A writer subprocess wrote a row visible to a separate API process.
- [x] `/api/recent` returned the injected event.
- [x] `/ws/live` pushed within five seconds.
- [x] Testcontainers PostgreSQL and uvicorn subprocesses cleaned up.

## End-to-end and frontend evidence

- Backend hot path proved `/readyz`, cross-process database visibility, `/api/recent`, WebSocket push and subprocess cleanup: 5/5 passed.
- Desktop Live cold load rendered Radar/Tape and retained URL-owned filters; row navigation remained actionable.
- Mobile 390/430 rendered Radar/Tape tasks, routes and token cases without the removed Lab task or overflow.
- Notification navigation uses normal Playwright `.click()` actionability and routes to retained token search without constructing Pulse context.
- Network mocks contain no Signal Pulse endpoint; architecture guards reject reintroduction of its query key, types, fixtures or feature directory.

## Migrations

`20260721_0184_signal_pulse_hard_delete.py` is an exact forward-only migration. It purges feature-owned rows in shared notification/terminal ledgers, drops 13 named tables in FK-safe order, uses neither `CASCADE` nor `IF EXISTS`, and refuses downgrade with pre-migration-backup guidance. Tests use isolated PostgreSQL; no operator database was mutated during implementation verification.

## Independent review

- Kappa/CQRS diff review: no P0 and no code-layer P1; single-writer, stable-key, idempotency and bounded catch-up contracts remain intact.
- `impl-validator`: code, migration, shared-capability retention and hard-delete checks passed. Its stale-SDD/diff-number findings are repaired in this record and the audit before merge.
- Remaining deployment prerequisite: back up PostgreSQL and remove exactly `signal_pulse_candidate`, `pulse.decision` and `pulse_candidate` from operator config before startup.

## Deployment status

The user requested direct merge, Docker rebuild and real-environment inspection after functional gates passed. Deployment validation, current schema version, `/readyz`, and final diff/commit identity will be recorded after startup; the SDD remains active until then.
