# Spec — Runtime Performance Root Fix

**Status**: In progress
**Date**: 2026-05-25
**Owner**: Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/superpowers/specs/active/2026-05-25-kappa-cqrs-runtime-integrity-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-24-projection-dirty-target-hard-cut-cn.md`

## Background

After the Token Radar catch-up and resolution-refresh scans were removed, live
runtime CPU was still high. Docker stats showed PostgreSQL, not the Python app,
as the dominant CPU consumer. `/readyz` showed long p99 loops on
`equity_event_brief`, `news_item_brief`, and `pulse_candidate`.

Subagent review and live `pg_stat_activity` confirmed the immediate hot query:
agent brief workers still discovered work by repeatedly scanning fact/read-model
tables when idle. This is the same architectural class as the removed Token
Radar catch-up: a normal worker loop proves "nothing is missing" by running a
broad query over business facts.

## Root Cause

The issue is not simply "too many workers". The core cause is unbounded runtime
discovery:

- Normal workers use fact-table broad scans to discover derived work.
- Some scan paths run on short intervals and join high-churn tables.
- Work discovery, input-packet assembly, retry policy, and freshness checks are
  coupled inside a single repository query.
- Missed-enqueue insurance is implemented as runtime catch-up instead of
  explicit repair/audit commands.

This violates the intended Kappa/CQRS rule: facts are business truth, but
derived work must be claimed from durable control rows during normal runtime.

## Current Direct Hotspot

The active CPU hotspot was:

- `NewsItemBriefWorker` calling `NewsRepository.list_items_for_brief(...)`.
- `EquityEventBriefWorker` calling
  `EquityEventRepository.list_events_for_brief(...)`.

Both methods scanned candidate tables, joined current briefs, runs, story rows,
facts, context, and source state to discover work. When the queue was empty,
they still spent database CPU searching for work.

## Required Architecture

Agent brief generation must be edge-triggered:

1. Producers that mutate relevant facts enqueue `brief_input` dirty targets in
   the same transaction as the fact write.
2. Story projections enqueue `brief_input` for affected story members because
   story context is part of the brief input.
3. Context fetch/persistence enqueues `brief_input` for affected parent news
   items because context rows are part of the brief input.
4. Brief workers claim `brief_input` targets only.
5. Repositories load exact target IDs and assemble input packets.
6. If a producer misses a target, explicit ops repair enqueues it with a
   projection and time-window bound; runtime loops do not broad-scan facts.

## Goals

- G1. Delete runtime use of news/equity agent brief broad scans.
- G2. Delete the old broad-scan repository methods, not keep compatibility
  entry points.
- G3. Add `brief_input` to news/equity projection dirty-target constraints.
- G4. Make all brief-input producers enqueue dirty rows at the write edge.
- G5. Extend ops repair so human/maintenance repair can enqueue `brief_input`.
- G5a. Require `--since-hours` for any executed repair that includes
  `brief_input`, because agent work is expensive and must be bounded.
- G6. Add architecture tests banning agent brief broad discovery.
- G7. Add targeted indexes for remaining exact-target and due-claim paths.
- G8. Keep business output unchanged: same brief packet, same agent run audit,
  same current brief write contract.

## Non-goals

- N1. Do not lower worker counts as the primary fix.
- N2. Do not increase intervals to hide database work.
- N3. Do not keep broad-scan runtime methods behind config.
- N4. Do not change agent prompts or business classifications.
- N5. Do not claim all future performance risks are solved by this phase.

## Remaining Similar Risks

Subagent review found additional broad-scan families that must be handled as
separate root fixes:

- P0: `narrative_admission` rebuild/cleanup still has periodic broad-table work.
- P0: `mention_semantics` discovers semantic work by scanning admissions and
  JSON membership state.
- P1: token profile/image/profile-refresh workers still have broad radar/fact
  discovery paths.
- P1: token capture tier and pulse candidate workers scan existing radar/read
  models to create downstream work.
- P2: readyz/API diagnostic paths can add CPU through repeated serialization and
  uncached health reads.

These are not the immediate PostgreSQL hot query observed in this incident, but
they belong to the same architecture class and should be cut over to durable
dirty targets or bounded scheduled partitions.

## Acceptance Criteria

- `rg "list_items_for_brief|list_events_for_brief" src tests` finds no runtime
  implementation or test fake compatibility method.
- Agent brief workers call `claim_due(... projection_name="brief_input")` before
  loading inputs.
- Empty dirty queue returns quickly without querying fact candidates.
- Existing news/equity process/story/context writers enqueue `brief_input`.
- `ops enqueue-projection-dirty-targets --domain all --execute` can seed repair.
- `ops enqueue-projection-dirty-targets --projection brief_input --since-hours 24 --execute`
  can seed bounded agent-input repair.
- Targeted unit/integration/architecture tests pass.
- After Docker rebuild and migration, live Postgres CPU drops from the observed
  >100% hot-query state and no active query repeatedly scans brief candidates.
