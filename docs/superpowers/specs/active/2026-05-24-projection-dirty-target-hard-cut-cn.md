# Spec — Projection Dirty Target Hard Cut

**Status**: Draft
**Date**: 2026-05-24
**Owner**: Codex
**Related**:
- `docs/RELIABILITY.md`
- `docs/WORKERS.md`
- `docs/superpowers/plans/active/2026-05-24-projection-dirty-target-hard-cut-plan-cn.md`

## Background

The service architecture is Kappa/CQRS: PostgreSQL material facts are business truth, and derived read models are rebuildable. The runtime docs require every listener to use `NOTIFY` only as a wake hint and to recover through a bounded `interval_seconds` catch-up loop, see `docs/RELIABILITY.md:160` and `docs/WORKERS.md:31`. The runtime tests already enforce single writer ownership for read models through `SINGLE_WRITER_READ_MODELS`, see `tests/architecture/test_worker_runtime_contracts.py:202`.

The missing invariant is the idle-cost boundary of those catch-up loops. `WorkerBase.run()` always calls `run_once()` and then waits `interval_seconds`, see `src/gmgn_twitter_intel/app/runtime/worker_base.py:96`. A worker can therefore be a correct single writer and still burn CPU if its no-work path scans all material facts every few seconds.

Equity Page exposed this design gap. `EquityEventPageProjectionWorker` currently decides whether to scan by reading a source summary, then calls `repos.equity_events.list_events_for_page_projection(...)` when the summary changed or coverage looks incomplete, see `src/gmgn_twitter_intel/domains/equity_event_intel/runtime/equity_event_page_projection_worker.py:45`. The heavyweight query joins `equity_company_events`, universe rows, story rows, briefs, documents, alert rows, page rows, timeline rows, and per-event fact state, see `src/gmgn_twitter_intel/domains/equity_event_intel/repositories/equity_event_repository.py:1559`. The current summary guard stopped the severe every-3-second empty full scan, but it remains a runtime heuristic and still performs broad discovery on restart or watermark changes.

News Page has the same shape at smaller scale. `NewsPageProjectionWorker` calls `repos.news.list_items_for_page_projection(...)` every run, see `src/gmgn_twitter_intel/domains/news_intel/runtime/news_page_projection_worker.py:35`. That repository query joins `news_items`, sources, story members, story groups, token mentions, fact candidates, briefs, and `news_page_rows` to discover stale projections, see `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:1326`.

News Source Quality also uses interval-triggered broad aggregation. `NewsSourceQualityProjectionWorker` recalculates every configured window by calling `list_source_quality_inputs(...)`, see `src/gmgn_twitter_intel/domains/news_intel/runtime/news_source_quality_projection_worker.py:36` and `src/gmgn_twitter_intel/domains/news_intel/repositories/news_repository.py:1815`. Current live scale is small enough that this is cheap, but the pattern grows with `news_items` and `news_fetch_runs`, not with changed sources.

Token Radar already demonstrates the desired pattern. It writes durable `token_radar_dirty_targets`, claims due rows with `FOR UPDATE SKIP LOCKED`, and projects only claimed targets, see `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_dirty_target_repository.py:14` and `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:62`. This spec promotes that pattern from a local Token Radar solution into a project-wide read-model projection contract.

## Problem

Some projection workers discover work by repeatedly comparing material facts against read models through broad SQL joins. This is fragile because the idle path is proportional to table size, not to the number of changed targets. It causes "no data but CPU is high" failures, hides cost behind harmless-looking `interval_seconds`, and lets new domains reintroduce the same issue despite the single-writer architecture tests.

## First Principles

PostgreSQL facts remain the only business truth. Dirty targets are control-plane rows that say a read model target needs recomputation; they are not facts and cannot be served directly as product data.

`NOTIFY` remains only a wake hint. A dropped wake must not lose work because durable dirty targets are claimed from the database on the next bounded catch-up.

Every derived read model still has exactly one runtime writer. This work changes how the writer discovers work, not who owns the write.

The normal no-work path of a projection worker must be O(due dirty targets) or O(dirty-target table metadata only). It must not be O(material facts), O(read-model rows), or O(fact rows joined to read-model rows). A "summary" that reads material facts, such as the current page projection source summary, is not allowed in normal runtime.

## Goals

- G1. All normal Page, Story, Calendar, Alert, Timeline, and Source Quality projections in Equity and News SHALL discover work from durable dirty-target tables, not by scanning material facts for stale read-model rows.
- G2. Fact writers SHALL enqueue dirty targets in the same database transaction that writes, replaces, rejects, deletes, or reclassifies the source fact whenever the affected target id is known.
- G3. Projection workers SHALL claim dirty targets with bounded leases, project by explicit target ids, and mark targets done or retryable without relying on `NOTIFY` delivery.
- G4. Projection writes SHALL be target-scoped and no-op safe through `payload_hash`, `source_watermark_ms`, and version checks; unchanged payloads must not advance `computed_at_ms`.
- G5. The hard cut SHALL remove the old runtime scan paths instead of keeping compatibility fallbacks or feature flags.
- G6. Architecture tests SHALL prevent new projection workers from calling broad `list_*_for_*_projection` or `list_*_missing_*` discovery methods in normal runtime code.
- G7. Live idle verification SHALL show no repeating broad Equity or News projection scan in `pg_stat_activity`, and worker notes SHALL report `claimed=0` rather than `event_scan=skipped`.

## Non-goals

- N1. Do not change frontend API contracts or UI behavior.
- N2. Do not change provider ingestion, OKX WS behavior, market tick semantics, Token Radar scoring, Pulse agent behavior, or LLM prompts.
- N3. Do not preserve old scan-based projection discovery behind a config flag, fallback branch, or temporary compatibility mode.
- N4. Do not create a global cross-domain dirty queue. Each domain owns its own projection-control table and repository.
- N5. Do not make dirty-target rows a product surface. They are only operational control state.

## Target Architecture

Equity and News projections move to domain-owned durable control queues:

- `equity_event_projection_dirty_targets`
- `news_projection_dirty_targets`

Each row identifies one projection target. The target can be an event, expected calendar event, news item, source/window aggregate, or story candidate. Multiple source mutations coalesce into the same target row by unique key. The dirty table stores enough control data to claim, lease, retry, and observe the work, but not enough to replace source facts.

Fact writers enqueue targets immediately:

- Equity document processing enqueues current and previously affected `company_event` page, timeline, alert, story, brief-input, and matching calendar targets.
- Equity story projection enqueues page and brief targets for affected company events.
- Equity brief writes enqueue page, timeline, and alert targets for the company event.
- Equity source reconcile enqueues calendar targets for expected events and page/timeline/alert/calendar targets for existing company events affected by universe metadata changes.
- Equity calendar targets use `due_at_ms` for time-driven expected-to-missed transitions, so correctness does not depend on an audit scan.
- News fetch and item processing enqueue news page, story, and source-quality targets for current and previously affected news items.
- News source metadata reconciliation enqueues page targets for existing items from changed sources and source-quality targets for changed sources.
- News story projection and brief writes enqueue page targets.
- News Source Quality writes that change `news_sources.source_quality_status` enqueue page targets for existing items from that source.
- News fetch, item processing, fact writes, and brief writes enqueue `source_quality` targets by `source_id` and configured windows. Source-quality targets also reschedule themselves through durable `due_at_ms` for sliding-window expiry and freshness transitions.

Projection workers change shape:

```text
run_once()
  -> claim_due_dirty_targets(limit, lease_ms)
  -> load source payloads by claimed target ids only
  -> build read-model rows
  -> write target-scoped rows with payload_hash/source_watermark guard
  -> delete target-scoped stale rows when the target is now ineligible
  -> mark_done or mark_error
  -> notify downstream only when writes changed visible rows
```

Coverage and repair become explicit manual maintenance, not normal projection discovery. A one-shot operator command can enqueue dirty targets from existing facts during rollout or repair. There is no scheduled audit worker, cron, low-frequency runtime loop, or compatibility fallback that scans material facts to discover projection work.

## Conceptual Data Flow

Equity:

```text
equity_event_fetch
  -> equity_event_process
  -> equity_event_projection_dirty_targets(company_event/story/brief/page)
  -> equity_event_story_projection
  -> equity_event_brief
  -> equity_event_page_projection
  -> equity_event_page_rows / equity_company_timeline_rows / equity_event_alert_candidates / equity_event_calendar_rows
```

News:

```text
news_fetch
  -> news_item_process
  -> news_projection_dirty_targets(news_item/story/source_quality)
  -> news_story_projection
  -> news_item_brief
  -> news_page_projection / news_source_quality_projection
  -> news_page_rows / news_source_quality_rows
```

The changed arrow is the control-plane edge between fact writes and projection workers. It replaces runtime stale-discovery SQL.

## Core Models

`equity_event_projection_dirty_targets`:

- `projection_name`: `story`, `page`, `timeline`, `alert`, `calendar`, or `brief_input`.
- `target_kind`: `company_event`, `expected_event`, or `company`.
- `target_id`: domain id for the target.
- `dirty_reason`: source mutation category, such as `event_processed`, `story_updated`, `brief_updated`, `expected_event_reconciled`, or `projection_backfill`.
- `source_watermark_ms`: latest source timestamp known at enqueue time.
- `payload_hash`: stable coalescing hash for the target and reason.
- `priority`: small integer ordering key.
- `due_at_ms`, `leased_until_ms`, `lease_owner`, `attempt_count`, `last_error`.
- `first_dirty_at_ms`, `updated_at_ms`.
- A claimed row returns a completion token: target key, `payload_hash`, `lease_owner`, and `attempt_count`. `mark_done` and `mark_error` must match the full token so an old claim cannot delete or overwrite a newer re-enqueue.

`news_projection_dirty_targets`:

- `projection_name`: `story`, `page`, or `source_quality`.
- `target_kind`: `news_item` or `source`.
- `target_id`: `news_item_id` or `source_id`.
- `window`: nullable for item targets, required for source-quality targets.
- The same lease, retry, watermark, priority, and audit fields as Equity.
- A claimed row returns the same completion token as Equity.

Projection row invariants:

- `payload_hash` excludes volatile `computed_at_ms`.
- `source_watermark_ms` only moves forward.
- Unchanged payloads do not update `computed_at_ms`.
- Deletes are scoped to claimed target ids.
- News Page and News Source Quality rows must gain the same `payload_hash` and `source_watermark_ms` no-op guard that Equity projection rows already use.

## Interface Contracts

No HTTP, WebSocket, or frontend contracts change.

`/readyz` worker status should expose projection control notes for operators:

- `claimed`: count of dirty targets claimed.
- `projected`: count of source payloads successfully projected.
- `deleted`: count of target-scoped stale rows removed.
- `marked_error`: count of retryable failures.
- `queue_depth`: due dirty-target count when cheaply available.
- `projection_version`: existing read-model version.

CLI/ops contract:

- Add a repair command that enqueues dirty targets from existing facts.
- The command must support dry-run and execute modes.
- The command reports counts by domain, projection, and target kind.
- The command must not print secrets.

## Acceptance Criteria

- AC1. WHEN Equity Page worker runs with an empty dirty queue THEN it SHALL return `processed=0`, `claimed=0`, and SHALL NOT call `page_projection_source_summary()` or `list_events_for_page_projection()`.
- AC2. WHEN a company event, event fact, document, story, brief, universe member, expected event, or old replaced/rejected event changes THEN the same transaction SHALL enqueue the relevant Equity dirty target.
- AC3. WHEN Equity Page claims a `company_event` dirty target THEN it SHALL load payloads by that explicit `company_event_id` only and SHALL update or delete only rows for that target.
- AC3a. WHEN a new company event matches an expected calendar event, or an expected event crosses its due time, THEN the system SHALL enqueue and process an explicit calendar dirty target without a broad calendar scan.
- AC4. WHEN News Page worker runs with an empty dirty queue THEN it SHALL return `processed=0`, `claimed=0`, and SHALL NOT call `list_items_for_page_projection()`.
- AC5. WHEN a news item, story, fact candidate, token mention, item brief, source metadata row, old replaced news item, or `source_quality_status` changes THEN the same transaction SHALL enqueue the relevant News Page dirty target.
- AC6. WHEN News Source Quality claims a `source_id/window` dirty target THEN it SHALL aggregate only the claimed source/window pair and SHALL not recompute all sources for all windows.
- AC6a. WHEN a source-quality window can change only because time moved forward THEN the source/window dirty target SHALL be durably scheduled with `due_at_ms`; correctness SHALL NOT depend on an audit scan.
- AC7. WHEN an unchanged Equity, News Page, or News Source Quality payload is projected twice THEN the read-model row SHALL keep its prior `computed_at_ms` and avoid a physical update.
- AC7a. WHEN a claimed dirty target is re-enqueued before the old claim finishes THEN the old claim SHALL NOT delete or mark done the newer dirty row.
- AC8. WHEN the architecture test suite scans runtime workers THEN it SHALL fail if a projection worker calls deleted broad discovery methods or introduces a new `list_*_for_*_projection` runtime dependency.
- AC9. WHEN the repair command is executed on an existing database THEN it SHALL enqueue coverage targets without directly writing read-model rows.
- AC10. WHEN Docker is rebuilt and the service runs on live config THEN `/readyz` SHALL show projection workers healthy, dirty queues draining, and no repeating broad Equity or News projection query in `pg_stat_activity`.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Missing enqueue hook leaves a stale read model | High | Add source-writer unit tests plus coverage repair command; architecture docs list every source mutation and dirty target |
| Dirty queue grows without bound after repeated failures | High | Lease, attempt count, error backoff, queue-depth status, and mark-error tests |
| Hard cut breaks fresh database projection because existing facts have no dirty rows | Medium | Rollout includes one-shot enqueue repair command after migration |
| Source Quality still becomes expensive per source/window | Medium | Claim by source/window and add source/time indexes; defer incremental ledger to a separate spec only if source/window aggregation remains hot |
| Too much shared abstraction blurs domains | Medium | Domain-owned dirty repositories; only patterns are shared through docs and tests |
| Architecture tests block legitimate maintenance scans | Low | Allow broad discovery only in manual `app/ops` repair commands, not runtime workers, scheduled audits, or cron loops |

## Evolution Path

After Equity and News use dirty targets, the same idle-cost contract should be applied to any future read-model worker before merge. If Source Quality becomes hot at larger scale, the next evolution is a per-source daily/hourly stats ledger, not a return to broad interval aggregation.

## Alternatives Considered

- Keep the current summary guard for Equity. Rejected because it is an in-memory heuristic, scans after restart, and does not generalize to News or future projections.
- Increase `interval_seconds`. Rejected because it reduces symptom frequency but keeps O(table size) idle cost.
- Use PostgreSQL triggers for all dirty enqueue. Rejected for this codebase because repository-level writes already define domain semantics and can enqueue richer target reasons in the same transaction with clearer tests.
- Use one global dirty queue. Rejected because it centralizes domain-specific target semantics and creates a cross-domain dumping ground.
- Keep old scan methods as fallback. Rejected because the user requirement is a hard cut with no compatibility code, and fallback branches tend to become permanent.
- Add a scheduled low-frequency audit worker. Rejected because it would reintroduce scan-based work discovery under a slower interval and make correctness depend on a compensating path.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Use durable dirty targets for normal projection discovery, claim by lease, project by target id, no-op unchanged payloads, and enforce the rule with architecture tests. |
| Ask first | Add incremental source-quality ledgers, change public API fields, or broaden the repair command to mutate facts. |
| Never | Keep scan-based runtime fallback, add scheduled audit/cron scans, use dirty rows as business truth, print secrets, or let runtime workers scan full fact tables to prove no work. |
