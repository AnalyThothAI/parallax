# Spec — Runtime Worker Constraint Hard Cut

**Status**: Implemented for listed P0/P1/P2 runtime hard-cut scope; live Docker verification pending
**Date**: 2026-05-25
**Owner**: Codex
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/RELIABILITY.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- `docs/superpowers/specs/active/2026-05-24-projection-dirty-target-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-25-runtime-performance-root-fix-cn.md`

## Implementation Progress

- 2026-05-25: `pulse_candidate` and `narrative_admission` converted to claim-first dirty target consumers; admission now enqueues semantic and digest downstream work in the same transaction.
- 2026-05-26: `mention_semantics` converted to leased semantic-row claims with stale-completion protection and no runtime admission scan. `token_discussion_digest` converted to `discussion_digest_dirty_targets` claims, exact target payload loads, dirty-row reschedule/error completion, and bounded `--work discussion_digest` repair.
- 2026-05-26: `token_profile_current`, `token_image_mirror`, `asset_profile_refresh`, `token_capture_tier`, and `live_price_gateway` converted to claim/control-row first execution. Runtime compatibility scan methods and wrappers were removed (`recent_profile_targets`, `candidate_sources`, `PendingAssetProfileQuery`, `select_due_asset_profile_rows`, `active_live_market_targets`, `demote_absent_hot_rows`).
- 2026-05-26: `enqueue-runtime-worker-dirty-targets` now covers profile/image/profile-refresh/capture/live control rows as bounded, dry-run-default, enqueue-only repair. `handle_summary` no longer runs runtime reconcile and is a leased-job consumer. CEX OI and macro scheduled tail workers expose compact cost counters. Worker status notes are compacted before `/readyz`, `/status`, and CLI status serialization.
- Still open: Docker/live idle verification after applying migration in the running environment.

## Background

The service is a PostgreSQL-first Kappa/CQRS pipeline. Material fact tables are
business truth, read models are rebuildable, and `NOTIFY` is only a wake hint.
This architecture works only if normal runtime worker cost is proportional to
changed work, not to total historical data.

Recent production incidents exposed the same class of failure in multiple
workers. The immediate hot spot was fixed by moving `news_item_brief` and
`equity_event_brief` from runtime broad-scan discovery to `brief_input` dirty
target claims. That was the correct local hard cut, but it does not close the
architecture class across the system.

Remaining workers still use periodic runtime discovery over facts or read
models. Examples include `pulse_candidate`, `narrative_admission`,
`mention_semantics`, `token_discussion_digest`, `asset_profile_refresh`,
`token_image_mirror`, `token_profile_current`, `token_capture_tier`,
`live_price_gateway`, and `handle_summary`.

## Problem

Some workers still answer "what work should I do?" by scanning business facts
or current read models inside their normal `interval_seconds` loop. This creates
an idle-cost bug:

```text
no new work
  -> worker still scans facts/read models
  -> database CPU grows with historical data size
  -> missed wake recovery becomes a broad query
  -> production fixes drift toward longer intervals and disabled workers
```

This is an architecture bug, not a worker-count bug. Lowering concurrency,
increasing intervals, or disabling workers can reduce symptoms, but it does not
change the asymptotic cost model.

## Root Cause

Runtime discovery, input assembly, freshness checks, retry policy, and repair
logic are mixed together. In the old shape, one repository query often tries to:

- find stale or missing work;
- join the source facts needed for execution;
- compare current read-model state;
- check prior agent attempts or retries;
- compensate for missed wakes;
- decide if a target is still eligible.

When there is no actual work, that query still has to prove the absence of work
by reading facts or read models.

## First Principles

1. Facts remain the only business truth.
2. Dirty targets, jobs, leases, and retries are control-plane state, not product
   truth.
3. Normal runtime catch-up may read control-plane queues or bounded scheduler
   partitions only.
4. Runtime catch-up must not scan broad fact windows to discover work.
5. Missed enqueue repair is an explicit ops command with a domain, projection,
   and time/window bound.
6. A worker that has no due control rows must return quickly without loading
   source facts.
7. A worker that needs expensive source payloads must claim a target before it
   loads them.

## Required Runtime Shape

All projection, admission, agent-trigger, profile, media, and digest workers
must move to this shape when their work is target-specific:

```text
producer writes facts/read model
  -> same transaction enqueues dirty target

worker run_once()
  -> claim due targets with lease
  -> if none: return no_due_targets
  -> load exact target payloads by ids from the claim
  -> execute deterministic/provider work
  -> write read model/audit rows
  -> mark target done or retryable
  -> emit wake only when visible output changed
```

The no-work path is allowed to query only the durable control table and cheap
worker metadata. It must not query large material fact tables, broad current
read models, or JSON source-set membership.

## Hard Constraints

- C1. Runtime workers SHALL NOT call broad discovery methods such as
  `list_*_for_*`, `list_*_missing_*`, `*_source_summary`, or full-frontier
  rebuild queries to find work when their queue is empty.
- C2. Runtime workers SHALL claim work with a durable lease or running state
  before any expensive SQL, provider call, or agent call.
- C3. Producers SHALL enqueue dirty targets in the same transaction as the fact
  or read-model mutation that makes downstream work necessary.
- C4. Dirty target rows SHALL coalesce by stable target key and payload/source
  watermark. Duplicate enqueue is a wake hint; material enqueue may clear an
  active lease only when the source watermark or payload changed.
- C5. `mark_done` and `mark_error` SHALL use a completion token from the claim:
  target key, payload hash, lease owner, and attempt count. Stale claims cannot
  delete newer dirty work.
- C6. No-start provider backpressure SHALL NOT burn provider attempts or domain
  retry budgets. The target is released or rescheduled with a bounded cooldown.
- C7. Runtime cleanup SHALL be target-scoped. Global cleanup, historical repair,
  stale-row pruning, and coverage discovery belong to explicit ops commands.
- C8. `NOTIFY` handlers SHALL wake queue consumers only. High-frequency wake
  channels such as `market_tick_written` must not trigger full digest,
  narrative, profile, or Pulse discovery scans.
- C9. JSONB source-set fields may be used as payload/audit data, but not as the
  normal hot-path work-discovery index. If membership is a runtime predicate,
  materialize it into normalized control rows or add a targeted indexed path.
- C10. Every worker SHALL expose status notes that make idle cost visible:
  `claimed`, `queue_depth` when practical, `source_rows_scanned`,
  `targets_loaded`, `rows_written`, and backpressure reason counts.

## No Compatibility Code

This is a hard cut. The implementation SHALL NOT keep old broad-scan runtime
paths behind flags, fallbacks, dual-read compatibility, low-frequency audit
loops, or "just in case" catch-up scans.

Allowed exceptions:

- Alembic migrations may transform existing control/read-model state.
- Explicit ops repair commands may scan facts only when the operator supplies a
  bounded domain/projection/window or time range.
- Tests may reference removed method names only in architecture guards that ban
  them.
- Rollback documentation may describe the old shape, but runtime code must not
  branch back to it.

## Business Capability Impact

The hard cut is not intended to reduce product capability. It changes how work
is discovered, not what the product computes.

Must remain unchanged:

- public HTTP/WebSocket/CLI contracts unless a separate product spec says
  otherwise;
- scoring formulas and admission thresholds;
- agent prompts, output schemas, validation rules, and audit ledger semantics;
- read-model ownership and business interpretation.

Expected product effects:

- fresher outputs under load because new work is explicit and prioritized;
- lower idle database CPU;
- better failure isolation because provider backpressure reschedules targets
  instead of making runtime discovery repeatedly scan;
- more truthful stale states when a producer missed enqueue and ops repair has
  not been run.

Primary correctness risk:

- a producer can forget to enqueue a target. This must be controlled through
  architecture tests, targeted integration tests, and bounded repair commands,
  not through runtime broad-scan compatibility.

## Target Families

### P0 — Pulse Candidate Trigger Discovery

Current problem: `pulse_candidate` scans Token Radar current rows for configured
windows/scopes and then loads target context/timeline before deciding whether to
enqueue `pulse_agent_jobs`.

Required shape:

- `TokenRadarProjectionWorker` enqueues `pulse_trigger` dirty targets only when
  a target/window/scope edge materially changes.
- `PulseCandidateWorker` claims `pulse_trigger` targets, loads exact target
  context, applies gate/edge policy, and enqueues or suppresses a job.
- Existing `pulse_agent_jobs` claim path remains the execution queue, but
  trigger discovery must no longer scan all current Radar rows.

### P0 — Narrative Admission

Current problem: `narrative_admission` rebuilds the whole admitted frontier per
window/scope and performs broad stale cleanup.

Required shape:

- Token Radar and resolution updates enqueue `narrative_admission` dirty targets
  by target/window/scope.
- `NarrativeAdmissionWorker` claims targets and recomputes source sets only for
  those targets.
- Frontier removals become target-scoped stale marks from explicit changed
  targets or an ops repair/rebuild command.
- Runtime global delete cleanup is removed.

### P0 — Mention Semantics

Current problem: `mention_semantics` mixes due semantic claims with admission
scans that enqueue missing semantic rows. Semantic rows have retry state but no
running lease.

Required shape:

- Admission writes enqueue normalized semantic input targets or rows.
- `MentionSemanticsWorker` atomically claims semantic rows with lease/running
  state before provider execution.
- Missing semantic discovery moves to admission-target processing, not every
  semantics execution loop.
- JSON source-set membership is removed from hot-path due claim predicates.

### P1 — Token Discussion Digest

Current problem: digest target selection scans due admissions and high-frequency
wakes can repeatedly trigger digest readiness checks.

Required shape:

- Admission and semantics completion enqueue `discussion_digest` dirty targets
  by target/window/scope.
- Market changes enqueue digest refresh only when the target's visible market
  threshold can matter.
- The worker claims digest targets with lease and computes readiness for the
  exact target only.

### P1 — Token Profile Current

Current problem: `token_profile_current` polls Radar/current resolutions to pick
profile targets and may rewrite the same current rows every interval.

Required shape:

- Profile source writes, image readiness changes, resolution updates, and Radar
  target visibility changes enqueue `profile_current` dirty targets.
- `TokenProfileCurrentWorker` claims target ids, loads exact source rows, and
  writes only when payload hash changes.

### P1 — Token Image Mirror

Current problem: source discovery scans Radar rows, recent resolutions, profile
source tables, identity evidence, and CEX profiles every interval. Only the
download queue has leases.

Required shape:

- Profile/evidence/CEX profile producers enqueue image-source targets when logo
  source URLs are created or changed.
- `TokenImageMirrorWorker` claims image-source rows directly. It does not run
  broad logo-source discovery in normal runtime.
- Existing terminal states such as ready/unsupported remain terminal unless a
  new source URL or payload hash is enqueued.

### P1 — Asset Profile Refresh

Current problem: `asset_profile_refresh` uses periodic discovery from Radar and
recent resolutions for each provider.

Required shape:

- Resolution and Radar visibility changes enqueue provider-scoped profile
  refresh targets.
- Refresh backoff lives on the refresh target or source cache row.
- The worker claims provider/asset targets before provider calls.

### P1 — Token Capture Tier

Current problem: capture tier is a projection over active Radar targets and can
recompute by scanning current active market targets.

Required shape:

- Token Radar projection enqueues capture-tier targets when market visibility,
  score, or identity changes materially.
- Capture tier is rank-set semantics, not independent per-target semantics. Dirty
  targets wake a bounded top-N/rank-set recompute that preserves existing Tier 1
  and Tier 2 competition rules.
- Capture tier projects changed rank sets and runs bounded demotion from explicit
  changed/exited target sets or scheduled ops partitions, not an unbounded
  active-target scan.
- `LivePriceGateway` consumes the bounded live target control set produced by
  capture tier. It must not scan active Radar/current rows every interval.

### P2 — Registry Tail Worker Classification

Current problem: a plan that covers only the obvious incident workers can still
miss registered workers with periodic discovery or scheduled projections.

Required shape:

- Every worker in `worker_registry.py` must be classified as a dirty-target
  consumer, leased-job consumer, bounded scheduled source snapshot, target-scoped
  expansion, or explicit conversion target.
- Agent-adjacent broad reconciliation such as watchlist handle summaries must
  move to dirty/job enqueue or bounded ops repair.
- Scheduled source snapshots such as CEX OI radar and macro projections must
  prove a finite universe/window/limit and expose source-row counters, or move to
  bounded scheduler partitions.

### P2 — Diagnostics And Readiness

Current problem: status and diagnostics can accidentally become expensive by
serializing large worker payloads or running uncached aggregate health queries.

Required shape:

- `/readyz` and diagnostics use bounded summaries.
- Expensive health checks are sampled, cached, or moved to explicit ops
  diagnostics commands.
- Worker details include counters and compact status, not large source payloads.

## Control-Plane Model Requirements

Each dirty target table should include the following fields unless a domain has
an equivalent durable job table:

- `projection_name` or `work_name`;
- `target_kind`;
- `target_id`;
- optional `window` and `scope`;
- `dirty_reason`;
- `payload_hash`;
- `source_watermark_ms`;
- `priority`;
- `due_at_ms`;
- `leased_until_ms`;
- `lease_owner`;
- `attempt_count`;
- `last_error`;
- `first_dirty_at_ms`;
- `updated_at_ms`.

Claim queries must use row-level locking (`FOR UPDATE SKIP LOCKED` or an
equivalent atomic update/returning pattern) and must return enough data for
stale completion protection.

## Repair Command Requirements

Every domain that moves from runtime scan discovery to dirty targets must expose
an explicit repair command.

Repair commands:

- require a domain/work/projection selector;
- require a time range, window/scope, target id list, or bounded partition;
- dry-run by default;
- report candidate counts before enqueueing;
- enqueue dirty targets only, not read-model rows;
- do not call providers or agents;
- refuse unbounded agent/LLM work repairs.

## Architecture Tests

Add or extend architecture tests so regressions fail before runtime:

- runtime worker files must not call banned broad discovery method names;
- dirty-target consumers must claim before loading source payloads;
- producer write paths that mutate downstream inputs must enqueue dirty targets
  in the same transaction;
- agent/provider workers that burn attempts must reserve capacity before claim,
  or must prove their claim path does not burn attempts before provider start;
- ops repair may scan facts, runtime code may not.

## Acceptance Criteria

- AC1. No target family listed as complete has runtime broad-scan discovery in
  its normal worker loop.
- AC2. Empty queue for each converted worker returns quickly and does not query
  source fact tables.
- AC3. Every converted worker claims leased targets before expensive SQL,
  provider, or agent execution.
- AC4. Every source mutation that affects converted downstream work enqueues a
  dirty target in the same transaction.
- AC5. Existing business output contracts remain unchanged for converted
  workers.
- AC6. Bounded repair commands can reconstruct dirty targets from facts without
  writing read models or calling providers.
- AC7. Architecture tests ban removed runtime discovery methods.
- AC8. Live verification shows no repeating active SQL that scans converted
  fact/read-model domains when dirty queues are empty.
- AC9. Worker status exposes enough counters to distinguish queue backlog,
  provider backpressure, and idle scans.
- AC10. No compatibility flags, fallback runtime scan paths, or low-frequency
  audit loops remain for converted families.

## Verification Plan

For each converted worker family:

1. Add red architecture/unit tests proving the old broad-scan path is still
   reachable.
2. Add or migrate the dirty target table/repository.
3. Move producer enqueue to same-transaction write edges.
4. Change worker `run_once()` to claim first and exact-load second.
5. Delete old broad discovery methods and test fakes.
6. Add bounded ops repair.
7. Run targeted unit/integration/architecture tests.
8. Run `uv run ruff check src/parallax tests`.
9. Rebuild Docker, apply migrations, verify `/readyz`, queue counts,
   `pg_stat_activity`, and `docker stats`.

## Completion Bar

This spec is complete only when all P0 and P1 worker families follow the
dirty-target or leased-job model, and live idle CPU is no longer dominated by
runtime discovery queries. Partial completion may close a specific incident, but
it must not be described as whole-system performance root-fixed.
