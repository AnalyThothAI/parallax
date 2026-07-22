# Spec — Docker build contract repair

**Status**: In Progress
**Date**: 2026-07-22
**Owner**: Codex
**Approved by**: user request to build and start the image
**Approved at**: 2026-07-22
**Related**: `docs/sdd/features/active/2026-07-22-docker-build-contract-fix/plan.md`

## Background

The production web build type-checks source and tests before Vite emits assets. The current source imports `WorkerStatusData` through the public type barrel (`web/src/features/cockpit/model/statusCurrentContract.ts:1`), accepts an optional macro payload before a required argument (`web/src/features/macro/model/macroChartModel.ts:162`), and returns an un-narrowed news agent object where the contract requires a string status (`web/src/lib/api/client.ts:251`; `web/src/shared/model/newsIntel.ts:42`). These static contract defects block the Docker build before an image can be created.

## Problem

The repository's frontend tests and lint pass while the production TypeScript build fails, so Docker cannot produce or start the requested current image.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Should this change alter product behaviour? | No; repair static ownership and fixture contracts only. | user delegated goal | 2026-07-22 |
| Should E2E be added to this repair? | No; verify the production build and live container health without broad E2E. | prior explicit user direction | 2026-07-22 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Production web TypeScript compiles. | `npm run typecheck` exits 0. |
| Existing frontend behaviour remains covered. | frontend unit/component tests and architecture checks exit 0. |
| Docker image builds and starts with operator config. | `make docker-up`, `make docker-status`, `/healthz`, and `/readyz` succeed. |

## First principles

- One canonical public type export must serve all frontend consumers; no compatibility alias is introduced (`web/src/lib/types/index.ts`).
- Runtime boundary validators narrow unknown payloads before returning typed models (`web/src/lib/api/client.ts:251`).
- Test fixtures must satisfy the same current contract as production data (`web/src/shared/model/newsIntel.ts:141`).

## Goals

- G1. `npm run typecheck` and `npm run build` exit 0.
- G2. Existing frontend tests, lint, and architecture harness remain green.
- G3. A newly built Docker service reports healthy and ready.

## Non-goals

- N1. No backend, database, HTTP, WebSocket, or product contract redesign.
- N2. No compatibility wrapper or acceptance of retired payload fields.
- N3. No broad frontend architecture refactor in this repair.

## Target architecture

The current strict frontend contracts remain unchanged. Public type exports are complete, boundary normalization returns a proven typed object, function parameters follow TypeScript's required-before-optional rule, and test fixtures express the current contract directly.

## Conceptual data flow

```text
backend current contract -> frontend boundary validator -> typed feature model -> production bundle
```

Only the validator-to-model static typing and build-time fixtures change.

## Core models

- `WorkerStatusData`: the existing canonical current-worker status type.
- `NewsAgentSignal`: an object whose required `status` field is a validated string.
- `NewsRow`: the existing strict current news row including source and classification fields.

## Interface contracts

No public interface semantics change. Invalid current news payloads continue to fail closed at the frontend boundary.

## Acceptance criteria

- AC1. WHEN the frontend production type-check runs THEN the system SHALL report zero TypeScript errors.
- AC2. WHEN the frontend verification lanes run THEN the system SHALL preserve existing behavioural and architecture tests.
- AC3. WHEN the Docker stack is rebuilt and started THEN the app SHALL report healthy and ready using the operator-owned config paths.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| A cast hides a malformed news payload. | High | Construct the typed result from the validated status instead of casting. |
| Fixtures drift from the real current contract again. | Medium | Make fixtures explicit and include type-check in verification. |
| Docker starts an older image. | Medium | Build from the repaired main commit, then inspect compose status and readiness. |

## Evolution path

The separate complexity audit may propose generated-contract ownership and a consolidated frontend verification gate, but those changes require a new approved spec.

## Alternatives considered

- Relaxing strict types was rejected because it would conceal contract drift.
- Adding compatibility fields was rejected because retired shapes are intentionally unsupported.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve strict current-contract validation and build the exact checked source. |
| Ask first | Any product/API contract change or broad architecture refactor. |
| Never | Add compatibility aliases, accept retired fields, or print operator secrets. |
