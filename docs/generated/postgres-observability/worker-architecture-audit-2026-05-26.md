# Worker Architecture Audit, 2026-05-26

## Current Shape

The runtime currently has 34 entries in `/readyz`: 30 enabled/running workers and
4 disabled workers. The codebase keeps the main Kappa/CQRS invariant intact:
material facts are business truth, and rebuildable read models have a single
runtime writer. The worker count feels high because workers mix four different
responsibilities in one flat namespace:

- ingest adapters: continuous streams, polling, fetchers
- fact normalizers: resolution, processing, enrichment lifecycle updates
- projection builders: current rows, radar rows, pages, stories, summaries
- side-effect agents: LLM calls and notification delivery

## Recommended Target Shape

Keep the small worker implementations, but organize them behind six explicit
runtime lanes instead of treating each worker as an equal top-level daemon:

1. `ingest-lane`: collector, market tick stream/poll, news fetch, equity fetch
2. `identity-lane`: token capture tier, resolution refresh, asset/profile/image
3. `projection-lane`: current projections, token radar, news/equity pages/stories
4. `agent-lane`: enrichment, narrative semantics/digests, briefs, pulse candidate
5. `notification-lane`: rule evaluation and durable delivery
6. `maintenance-lane`: macro/cex boards, partition/retention/backfill jobs

Each lane should expose one queue health surface, one concurrency budget, and one
database pool budget. Individual workers can remain modular internally, but the
operator should see lanes first and workers second.

## Design Rules

- Every read model has exactly one owner worker and a documented rebuild command.
- Every fact/lifecycle table with multiple writers must have a logical idempotency
  key and a table-level conflict policy.
- Every external side effect must write a durable attempt ledger before or during
  execution, and must retry from that ledger.
- Dirty-target tables are control plane, not business truth; they should have
  retention and queue-depth SLOs.
- NOTIFY remains a wake hint only; every listener must run bounded catch-up.
- Worker config should group defaults by lane, then allow per-worker overrides.

## Consolidation Candidates

- Combine news projection workers under one `news-projection-lane` supervisor:
  item process, story projection, page projection, source quality, brief enqueue.
- Combine equity event projection workers under one `equity-projection-lane`
  supervisor with separate bounded steps.
- Keep LLM workers separate internally, but put them behind one `agent-lane`
  scheduler because they share the same provider circuit breakers and RPM budget.
- Keep stream and poll market tick workers separate for failure isolation, but
  report them together as `market-ingest`.

## Risk Hotspots

- `token_radar_projection` owns large audit/history tables and needs partition
  retention plus index-reviewed settlement queries.
- `target_posts_recent`, radar factor settlement, and short trigram search are
  current query hotspots.
- `equity_event_agent_runs` and related equity polling tables show excessive
  sequential scan volume and need query/index review.
- The current lock/wake design is correct but connection-heavy; lane-level pool
  budgets or PgBouncer should be considered before adding more workers.
