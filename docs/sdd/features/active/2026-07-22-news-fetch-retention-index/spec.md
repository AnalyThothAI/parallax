# Spec — News fetch retention foreign-key index

**Status**: In Progress
**Date**: 2026-07-22
**Owner**: Codex
**Approved by**: delegated Docker startup and backend optimization goal
**Approved at**: 2026-07-22
**Related**: `docs/sdd/features/active/2026-07-22-news-fetch-retention-index/plan.md`

## Background

Migration 0185 creates retention indexes before it runs ledger retention (`src/parallax/platform/db/alembic/versions/20260721_0185_backend_kiss_hard_cut.py:34`; `src/parallax/platform/db/alembic/versions/20260721_0185_backend_kiss_hard_cut.py:35`). Its news retention step deletes parent rows from `news_fetch_runs` (`src/parallax/platform/db/alembic/versions/20260721_0185_backend_kiss_hard_cut.py:519`), while the current index set covers the parent retention predicate and other agent/queue references but not the child fetch-run foreign key (`src/parallax/platform/db/alembic/versions/20260721_0185_backend_kiss_hard_cut.py:543`).

## Problem

On the operator database, deleting roughly 53,000 retained parents forces repeated sequential scans of roughly 94,000 child rows, keeping PostgreSQL CPU-bound and preventing Docker startup from reaching the app service.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Is the missing index runtime-useful after migration? | Yes; recurring fetch-run retention deletes the same referenced parents. | delegated goal | 2026-07-22 |
| Should historical payloads or compatibility paths be retained? | No; add one canonical FK index only. | delegated goal | 2026-07-22 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Parent retention cannot trigger full child-table scans. | Schema/unit assertions require the child FK index before retention. |
| 0184-to-head migration remains correct. | PostgreSQL migration integration test passes. |
| Real startup finishes. | Docker migration exits 0 and app becomes ready. |

## First principles

- Every frequently deleted referenced key needs an index on the referencing FK.
- Retention is bounded data lifecycle, not a second control plane.
- The index is canonical schema, not an operational-only workaround.

## Goals

- G1. The FK lookup plan uses the new child index instead of a sequential scan.
- G2. A new migration creates the canonical index while published migration 0185 remains byte-identical.
- G3. The operator database reaches migration head and the app reports ready.

## Non-goals

- N1. No retention-policy, table, worker, API, or read-model semantic change.
- N2. No migration compatibility wrapper or duplicate index.
- N3. No E2E suite.

## Target architecture

`news_provider_items.fetch_run_id` has one retained btree index owned by the schema migration. Parent retention and PostgreSQL FK actions use that index. No new service, table, worker, or queue is introduced.

## Conceptual data flow

```text
news_fetch_runs retention delete -> indexed child FK lookup -> ON DELETE SET NULL
```

## Core models

- Parent key: `news_fetch_runs.fetch_run_id`.
- Referencing key: `news_provider_items.fetch_run_id`.
- Canonical index: `idx_news_provider_items_fetch_run_id`.

## Interface contracts

No HTTP, WebSocket, CLI, or frontend contract changes.

## Acceptance criteria

- AC1. WHEN migration schema checks run THEN the system SHALL prove the child FK index is created before retention.
- AC2. WHEN a nonempty 0184 database upgrades THEN the system SHALL reach current head with the canonical index present.
- AC3. WHEN Docker migration restarts against the operator database THEN the system SHALL complete migration and make the app ready.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Published 0185 cannot itself help an 0184 database cross its slow delete. | Medium | Use one temporary concurrent preflight index, then let 0187 create the permanent canonical index. |
| Index creation blocks live writes. | Low | Operational preflight uses concurrent creation; migration runs before the app starts. |
| Temporary preflight index is left duplicated. | Medium | Drop it after the canonical migration index exists. |

## Evolution path

Audit all foreign keys on retention/deletion paths with PostgreSQL catalog checks; add only indexes backed by observed plans or workload.

## Alternatives considered

- Waiting for the sequential scan was rejected because the measured plan repeats an unindexed child scan for every retained parent.
- Adding a cleanup worker was rejected because it adds a control plane without fixing the schema invariant.
- Editing published 0185 was rejected because released migration history must remain immutable.
- Keeping a permanent manually-created index was rejected because schema ownership must remain reproducible.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve material facts and current retention semantics. |
| Ask first | Any retention-window or deletion-policy change. |
| Never | Add a queue, compatibility branch, or duplicate permanent index. |
