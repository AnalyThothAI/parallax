# Reliability

> **Scope.** Owns operational invariants that must hold in any deployment of this service. Setup commands live in `SETUP.md`; security policy in `SECURITY.md`.

## Single ASGI worker

One ASGI worker. Multiple workers duplicate the upstream collector. If collector and API must scale separately, split them into distinct processes.

## PostgreSQL pool isolation

`DBPoolBundle` owns separate PostgreSQL pools for HTTP/WebSocket reads
(`api_pool`), background worker SQL (`worker_pool`), long-lived
single-writer advisory locks (`lock_pool`), and wake listeners /
emitters (`wake_pool`). API routes are synchronous FastAPI handlers
because the repository layer uses synchronous psycopg; FastAPI runs
those handlers in its worker threadpool. Do not add per-endpoint
`asyncio.to_thread(...)` wrappers or direct `runtime.repositories()`
calls inside async HTTP handlers. If an API path needs synchronous
repository access, make the route synchronous. If it needs async
streaming, keep synchronous repository work outside the event loop
through a dedicated read model boundary.

Workers must use `DBPoolBundle.worker_session()`, not
`repository_session()` or raw pool connections. External provider IO,
publish calls, and wake waits must happen outside DB sessions so worker
transactions stay short and cancellable.

Workers that require single-writer advisory locks must acquire them via
`DBPoolBundle.acquire_advisory_lock_connection()`. Advisory locks are
session-scoped and may be held for the worker lifetime, so they must not
consume `worker_pool` connections needed for actual worker sessions.

## Foreground-only run model

The foreground service reads two config files:
`~/.gmgn-twitter-intel/config.yaml` for application/provider settings
and `~/.gmgn-twitter-intel/workers.yaml` for worker runtime knobs.
There is no macOS LaunchAgent, systemd unit, or `service` subcommand —
run via foreground CLI or Docker Compose.

## Docker Compose state

Docker Compose bind-mounts the host config directory into the container
and pins PostgreSQL data to the `gmgn-twitter-intel-postgres` named
volume. Local foreground and Docker share the same config directory,
including both YAML files; query Docker data via `/api/*`, `/ws`, or
`docker compose exec app gmgn-twitter-intel ...`.

## Worker lifecycle

All long-running workers inherit `WorkerBase`. `runtime.bootstrap()`
constructs the canonical worker map, provider wiring, `DBPoolBundle`,
and disabled placeholders for unavailable workers. `WorkerScheduler`
starts enabled workers in registry priority order, reports status for
the canonical map, stops workers cooperatively, cancels stragglers,
calls `aclose()`, and closes the pool bundle. Runtime health endpoints
and CLI status must read worker state from the scheduler's `workers`
map, not bespoke top-level runtime fields.

Worker timeout supervision has four layers. `WorkerBase`
`soft_timeout_seconds` is an overrun signal only: it exposes
`active_run_once_age_ms`, records one soft-timeout event, and keeps
waiting for the original task. `WorkerBase` `hard_timeout_seconds` is
cooperative cancellation: the current task is cancelled and awaited
before any replacement task can be created. Agent lane `timeout_seconds`
belongs to `AgentExecutionGateway` and represents provider execution
budget. PostgreSQL `statement_timeout_seconds` remains the final guard
for synchronous SQL because cancelling `asyncio.to_thread(...)` does not
kill the underlying thread or database statement.

Any domain worker interrupted by hard timeout must persist retry or
audit cleanup before re-raising `asyncio.CancelledError`. Claimed jobs
must not be left `running`; model/agent audit rows must be terminal or
retryable according to the domain state machine. If a synchronous
provider or DB call ignores cooperative cancellation, process restart is
the escalation path; Python must not attempt to kill the thread directly.

## Agent execution backpressure

LLM-backed providers share one `AgentExecutionGateway` per process. The
gateway owns provider-side execution mechanics: lane concurrency, RPM
limits, circuit breakers, timeouts, usage capture, safety-net fallback,
and request/result audit metadata. It does not own domain claims,
attempt counters, product audit tables, or read-model writes.

Workers that burn attempts when claiming DB work must reserve agent
capacity before claiming. `pulse_candidate` reserves `pulse.pipeline`;
`enrichment` reserves `social.event_enrichment`; `handle_summary`
reserves `watchlist.handle_summary`. If a reservation is denied, the
worker returns an `agent_backpressure_capacity_denied` note and leaves
the job unclaimed. This preserves retry budgets during provider
congestion and lets the next bounded catch-up cycle retry naturally.
For Pulse, `pulse.pipeline` is a parent reservation: child stages reuse
the parent global slot and acquire only the stage lane bulkhead. A
no-start response from capacity, circuit, RPM, or parent-reservation
pressure is backpressure, not a provider attempt. Provider-started
latency timeouts remain started execution failures and follow the
domain retry/audit policy.
Signal Pulse releases no-start provider/circuit pressure into a bounded
provider cooldown instead of the old 30-second retry loop. The job is returned
to `pending`, its claim attempt is decremented, and `next_run_at_ms` is delayed
by the lane/provider cooldown. This keeps outage noise out of business retries
while preserving the audit row that explains why execution did not start.
Supervisor cancellation is also auditable: the gateway records
`cancelled` result metadata and releases lane/global counters, then
propagates cancellation as `asyncio.CancelledError` so domain cleanup can
run.

Signal Pulse also performs deterministic cost gating before paid stages:
evidence-hard-blocked, source-quality-hidden, duplicate-fingerprint, and
non-public gate-ceiling paths cannot call the DeepSeek judge. The deterministic
eval contract reads the recorded cost-guard stage plan, so Qwen-only and reused
terminal runs are evaluated against the stages they were supposed to execute,
not against the full three-stage public-judge path.

`/api/status` exposes the gateway snapshot under `agent_execution`, and
Prometheus exposes `gmgn_agent_execution_*` metrics. These are ops
signals only. `/api/ops/diagnostics` also exposes a sanitized
`agent_execution` section with policy labels, counters, and status
classification. Lane `priority` is an operator-facing label for
diagnostics and triage, not a strict scheduler. Product readiness still
comes from persisted domain facts and read models.

## Coverage semantics

`coverage=public_stream` flags events as filtered from GMGN's anonymous public stream — not a full Twitter firehose guarantee. Do not advertise broader coverage in payloads or docs.

## MCP boundary

MCP / FastMCP is optional control / query infrastructure only. `/ws` is the production live push channel; do not route real-time events through MCP.

## Pulse Agent Audit Ledger

Signal Pulse agent decisions must be replayable from PostgreSQL. Every worker
run writes `pulse_agent_runs`; every stage writes one
`pulse_agent_run_steps` row. The runtime stage enum is now
`investigator | decision_maker | research_only_gate` (plan 2026-05-16
hard cut; the prior `analyst / critic / judge` stages are no longer
accepted by the schema CHECK constraint and exist only in historical
rows). `pulse_agent_run_steps.prompt_text` is operational audit data
and must never include secrets, cookies, auth headers, raw `.env`
values, or private provider credentials. Rows with insufficient data
finish as abstain decisions written via `research_only_gate` instead of
inventing confidence or a display status.

## Market tick capture lanes

`market_ticks` are append-only provider tick facts. Runtime persistence is
owned by three capture lanes: `MarketTickStreamWorker` writes Tier 1 WebSocket
ticks, `MarketTickPollWorker` writes Tier 2 REST ticks, and ingest inline
capture writes Tier 3 ticks while committing the matching `enriched_events`
rows with `events`. `token_capture_tier` is a rebuildable projection with
`TokenCaptureTierWorker` as its only runtime writer; it controls stream, poll,
and inline-only capture assignment, but it is not a market fact.

`LivePriceGateway` is cache/publish only. It may maintain process-local latest
state and fan out WebSocket updates, but it must not write market facts or
become a correctness dependency for projections.

WebSocket fan-out must be bounded. Slow clients are stale subscribers to drop;
they must not stall worker publish paths or other clients.

## Wake Hints And Durable Work

PostgreSQL `NOTIFY` channels (`market_tick_written`,
`market_tick_current_updated`, `resolution_updated`, `token_radar_updated`)
are wake hints, not delivery guarantees. Market tick writers wake
`MarketTickCurrentProjectionWorker`; Token Radar wakes from
`market_tick_current_updated` after the current market row changes. Every
listener (`TokenRadarProjectionWorker`, `PulseCandidateWorker`, future
workers) runs on a bounded `interval_seconds` loop from `workers.yaml`
even when `NOTIFY` is healthy. The loop must claim durable dirty queues,
honor due gates, or read bounded read models; it must not scan broad fact
windows just to prove no wake was missed. Token Radar runtime projection has
no recent-resolved-target catch-up scan. Token Radar repair uses the explicit
`ops enqueue-token-radar-dirty-targets` command, and resolution refresh
uses `token_discovery_dirty_lookup_keys`. Service correctness must not
depend on `NOTIFY` delivery.

## One writer per read model

Each derived read model has exactly one runtime writer. A second runtime
writer of `token_radar_current_rows`, `token_radar_publication_state`,
`pulse_candidates`, or any future read model is both a reliability incident
and an architecture-test violation. The
canonical worker registry and worker inventory are architecture-guarded
so runtime ownership stays explicit. Ops paths and CLI rebuilds are
explicit exceptions and must call the same projection service the worker
uses; they do not run their own SQL.

Projection worker idle paths must be proportional to due dirty targets, not
to fact-table size. Equity Event and News projection workers claim durable
dirty targets (`equity_event_projection_dirty_targets`,
`news_projection_dirty_targets`) and then load payloads by explicit target
ids only. Runtime projection workers must not discover stale work by scanning
material facts or read models, including missing-story scans, page-projection
staleness scans, or source-quality all-source/window scans. Broad coverage
discovery is allowed only in manual ops repair commands that enqueue dirty
targets and do not write read-model rows. Normal worker idle paths must be
proportional to queue depth, not to the size of `events`, `token_intents`,
`token_intent_resolutions`, or market tick fact tables.

The same dirty-target rule applies to runtime agent/profile tails:
`pulse_candidate`, `narrative_admission`, `token_discussion_digest`,
`token_profile_current`, `token_image_mirror`, `asset_profile_refresh`, and
`token_capture_tier` must claim their control-plane rows first. `mention_semantics`
and `handle_summary` are leased-job consumers and must not discover missing
jobs inside the runtime loop. `LivePriceGateway` reads the live target control
set from `token_capture_tier`; it must not scan Token Radar current rows.
Historical discovery is domain-owned. Token Radar uses
`ops enqueue-token-radar-dirty-targets` for explicit bounded repair; other
workers must expose similarly explicit domain repair paths instead of a generic
runtime-worker repair command.

## PostgreSQL Observability

The compose PostgreSQL service loads `pg_stat_statements`, PoWA,
`pg_stat_kcache`, `pg_qualstats`, and `pg_wait_sampling`, and writes slow
statement, lock-wait, checkpoint, temp-file, and autovacuum logs under
`~/.gmgn-twitter-intel/postgres-logs`. These signals are production
observability, not business truth, and they must never be used to hide backlog
or mutate queue rows.

Use `./scripts/pgbadger_report.sh` for log-driven evidence such as slow
statements, lock waits, deadlocks, checkpoints, and temp files. Use
`./scripts/powa_configure.sh` to keep the local PoWA GUCs and server row
configured with bounded retention and to verify that coalesced statement history
contains rows. The PoWA script prints server metadata and row counts only; it
does not print passwords or application config.

## Token Radar Clean Reset And Watchlist Summary Maintenance

Token Radar storage is a clean-reset hard cut. Legacy `token_radar_rows` and
`token_radar_retention_runs` are removed by migration/reset. Token Radar online
serving is `token_radar_current_rows` plus `token_radar_publication_state`.
`fresh` is allowed only when publication state is `ready` and served rows match
`current_generation_id`. Failed latest attempts serve previous rows as `stale`
or no rows as `failed`; retired history/audit tables are not part of runtime
serving. `fresh`, `stale`, and `failed` describe publication freshness only;
row `quality_status` describes business credibility.

Successful publication generation ids are content-stable. If a rebuild produces
unchanged current-row content, publication state refreshes without deleting or
reinserting `token_radar_current_rows`. Failed attempts may record
`attempt:{projection_version}:{window}:{scope}:{computed_at_ms}` ids before
rows are built, but successful generations must not be timestamp-derived.

`token_radar_current_rows` stores `rank_score`, `quality_status`,
`degraded_reasons_json`, and `factor_snapshot_json`. Legacy top-level
`asset_json`, `primary_venue_json`, `target_json`, `attention_json`,
`market_json`, `price_json`, and `score_json` blocks are dropped and must not be
treated as reader contracts. High-alert eligibility is gated by market quality
and deterministic gates; degraded rows can remain useful `watch` rows, but they
must not be promoted to `high_alert`.

Token Radar has no runtime hard-reset command. Legacy table retirement belongs
to migrations, and current-row repair is fact-driven:

```bash
uv run gmgn-twitter-intel ops enqueue-token-radar-dirty-targets --source events --since-ms 0 --dry-run
uv run gmgn-twitter-intel ops enqueue-token-radar-dirty-targets --source events --since-ms 0 --execute
uv run gmgn-twitter-intel ops rebuild-token-intents --window 24h --limit 5000 --projection-limit 5000
```

Cross-domain hard-cut cleanup commands, such as CEX Binance cleanup, may report
Token Radar rows that will become stale, but they do not delete Token Radar
tables directly. Run the domain rebuild path after those fact-level cleanups so
Token Radar reprojects from the updated facts.

Before re-enabling Watchlist handle summaries against existing data, backfill
compact watchlist read models in bounded batches:

```bash
uv run gmgn-twitter-intel ops backfill-watchlist-signal-stats --batch-size 5000 --max-batches 20
```

`handle_summary` should stay disabled in operator-owned
`~/.gmgn-twitter-intel/workers.yaml` until
`backfill-watchlist-signal-stats` reports `has_more=false` and the stats row
counts are plausible for the configured handles.

## Provider connection state

Streaming providers (OKX DEX WS, GMGN direct WS, and any future streaming
source) expose a connection state with a `last_state_change_at_ms` and
publish it through `/api/status`. State values are `disconnected`,
`connecting`, `authenticating`, `subscribed`, `streaming`, and `failed`.
Capture workers must expose provider state changes through status payloads so
operators can tell the difference between stale markets and stale projections.

## Snapshot gate observability

`CollectorService` exposes snapshot gate outcome counters
(`immediate_complete`, `debounced_complete`, `debounced_timeout`,
`non_tw_channel`) through `/api/status`. A non-trivial `debounced_timeout`
rate is a reliability signal even when raw ingest looks healthy.
