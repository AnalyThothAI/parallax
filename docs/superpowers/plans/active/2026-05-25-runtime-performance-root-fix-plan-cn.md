# Runtime Performance Root Fix Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` for
> independent audit/review tasks and `superpowers:systematic-debugging` for live
> CPU evidence. No runtime broad-scan compatibility code.

**Status:** In progress
**Date:** 2026-05-25
**Owning spec:** `docs/superpowers/specs/active/2026-05-25-runtime-performance-root-fix-cn.md`
**Branch:** `main` local working tree

## Phase 0 — Evidence

- [x] Confirm active runtime config paths with `uv run parallax config`.
- [x] Check Docker CPU split with `docker stats`.
- [x] Check `/readyz` worker p99 and active state.
- [x] Inspect `pg_stat_activity` for active hot SQL.
- [x] Run subagent audit for cross-worker broad-scan patterns.

## Phase 1 — Current Hotspot Hard Cut

- [x] Add `brief_input` as a valid dirty projection for news/equity.
- [x] Change `NewsItemBriefWorker` to claim `brief_input` dirty targets.
- [x] Change `EquityEventBriefWorker` to claim `brief_input` dirty targets.
- [x] Add exact-target loaders:
  - `NewsRepository.load_items_for_brief_targets(...)`
  - `EquityEventRepository.load_events_for_brief_targets(...)`
- [x] Enqueue `brief_input` from news item processing, story projection, and
  context fetch persistence.
- [x] Enqueue `brief_input` from equity event processing and story projection.
- [x] Extend ops projection repair to enqueue `brief_input`.
- [x] Add `--projection` and `--since-hours` bounds to ops repair; executing
  repair that includes `brief_input` now requires a time window.
- [x] Delete old `list_items_for_brief` / `list_events_for_brief` broad-scan
  methods and test fakes.
- [x] Add architecture tests banning agent brief broad discovery.
- [x] Add migration/indexes for `brief_input` and exact target/audit lookups.

## Phase 2 — Verification

- [x] Red test: prove old worker did not claim dirty target and architecture
  guard failed.
- [x] Unit tests for news brief worker dirty-claim behavior.
- [x] Unit tests for news/equity dirty-target producer fanout.
- [x] Integration tests for news exact-target brief input packet assembly.
- [x] Integration tests for equity brief worker stale-source handling.
- [x] Architecture tests for projection idle-cost contract.
- [ ] Full changed-area pytest pass after old broad methods are deleted.
- [ ] `uv run ruff check src/parallax tests`.
- [x] Docker rebuild and migration.
- [x] Run explicit repair enqueue; observed that unbounded `--domain all`
  creates excessive historical `brief_input` backlog, then added bounded repair
  controls.
- [ ] Rebuild after bounded repair controls.
- [ ] Clean up over-broad historical `brief_input` repair rows from live dirty
  queues, keeping recent facts and normal producer enqueues.
- [ ] Live data-flow check: dirty queue drains, `/readyz` p99 normalizes,
  Postgres CPU no longer dominated by brief candidate scans.

## Phase 3 — Remaining Similar Root Fixes

- [ ] Cut `narrative_admission` periodic rebuild/cleanup into dirty/scheduled
  bounded partitions.
- [ ] Cut `mention_semantics` admission scans into semantic dirty targets.
- [ ] Cut token profile/image/profile refresh discovery into target queues.
- [ ] Cut token capture tier and pulse candidate scans into bounded dirty work.
- [ ] Cache or bound readyz/API diagnostic serialization.
- [ ] Add global architecture tests banning "empty queue then broad scan" in all
  projection/agent workers.

## Completion Bar

This phase is complete only when the current live CPU hotspot is removed and
verified after Docker rebuild. The broader runtime is not considered fully
performance-root-fixed until Phase 3 removes the remaining similar scan
families.
