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

`DBPoolBundle.create()` owns startup pool construction and partial cleanup.
If pool creation fails after one or more pools were created, cleanup calls each
partial pool's formal synchronous `close()` contract directly and records any
missing or failed close as a note on the original creation exception. Startup
pool cleanup must not skip malformed pools through optional close probing or
mask the original create failure with a cleanup failure.
Runtime shutdown uses the same synchronous pool contract. `DBPoolBundle.aclose()`
may be awaited by async owners, but each psycopg pool must expose
`close() -> None`; awaitable or non-`None` close results are malformed pool
wiring, not alternate lifecycle shapes to await.
When a checked-out worker or advisory-lock connection must be discarded after
reset/unlock failure, `DBPoolBundle` closes the connection directly and returns
the closed connection through `pool.putconn(conn)`. Private test-only pool hooks
such as `close_returns(...)` and optional `conn.close` probing are not runtime
compatibility paths.
PostgreSQL liveness probes use the same formal connection boundary:
`postgres_health_check(...)` must call `conn.commit()` after successful probe
SQL and `conn.rollback()` after probe failures. Missing cleanup methods are
malformed connection wiring and must be reported as failed liveness payloads,
not skipped through optional `hasattr(...)` probes.
Inner write guards use the formal psycopg transaction-status contract:
`require_transaction(conn, operation=...)` reads `conn.info.transaction_status`
directly, rejects `IDLE`, and treats missing transaction-status evidence as
malformed connection/session wiring rather than fake-connection compatibility.

Workers must use `DBPoolBundle.worker_session()`, not
`repository_session()` or raw pool connections. External provider IO,
publish calls, and wake waits must happen outside DB sessions so worker
transactions stay short and cancellable.

Workers that require single-writer advisory locks must acquire them via
`DBPoolBundle.acquire_advisory_lock_connection()`. Advisory locks are
session-scoped and may be held for the worker lifetime, so they must not
consume `worker_pool` connections needed for actual worker sessions.
`WorkerBase` releases that handle through the formal advisory lock
connection `release()` contract; injected lock handles that only expose
`close()` are malformed runtime wiring, not a supported fallback.
Injected wake waiters have separate wait and close contracts:
`async_wait(...)` is awaited by the loop, while `close()` is synchronous and
must return `None`. Awaitable wake-waiter close results are malformed runtime
wiring, not an alternate cleanup shape.
CLI ops one-shot worker commands follow the same lifecycle boundary:
their temporary `DBPoolBundle` closes through `db.aclose()`, and any
manually acquired advisory lock releases through `release()` rather than
pool probing or `close()` fallback. If an ops one-shot command wires
asset-market providers directly, it closes the resulting provider bundle
through `AssetMarketProviders.aclose()` rather than enumerating provider fields
or probing individual `close()` methods.
The continuous collector owns its injected upstream stream client through
`UpstreamClientProtocol.aclose()`. A client that only exposes `close()` is
malformed wiring; collector shutdown must surface that contract failure
rather than silently accepting a different lifecycle shape.
GMGN DirectWS frame delivery follows the same formal-boundary rule: the
upstream adapter awaits the collector's async `handle_frame(...)` contract
directly. Synchronous frame callbacks are malformed runtime wiring, not a
supported test or provider compatibility shape.
Provider cleanup has the same root-contract rule. Runtime shutdown and
bootstrap failure cleanup call `WiredProviders.aclose()`,
`runtime.agent_execution_gateway.aclose()`, and `runtime.llm_gateway.aclose()`
directly. Bootstrap must not recursively scan provider dataclasses, object
slots, mappings, or `close/aclose`-shaped aliases.
Worker-owned provider handles follow their provider protocols directly:
Pulse candidate decision clients close through `aclose()`, and News fetch
source providers close through synchronous `close()`. Workers must not probe
alternate close shapes or await a sync close result as compatibility fallback.
Market stream workers also close each per-cycle provider async iterator through
the iterator's formal `aclose()` contract. A stream iterator missing `aclose()`
is malformed runtime wiring and must surface as degraded stream evidence, not a
successful no-close stream.

## Foreground-only run model

The foreground service reads two config files:
`~/.parallax/config.yaml` for application/provider settings
and `~/.parallax/workers.yaml` for worker runtime knobs.
There is no macOS LaunchAgent, systemd unit, or `service` subcommand —
run via foreground CLI or Docker Compose.

## Docker Compose state

Docker Compose bind-mounts the host config directory into the container
and pins PostgreSQL data to the `parallax-postgres` named
volume. Local foreground and Docker share the same config directory,
including both YAML files; query Docker data via `/api/*`, `/ws`, or
`docker compose exec app parallax ...`.

## Worker lifecycle

All long-running workers inherit `WorkerBase`. `runtime.bootstrap()`
constructs the canonical worker map, provider wiring, `DBPoolBundle`,
and disabled placeholders for unavailable workers. `WorkerScheduler`
starts enabled workers in registry priority order, reports status for
the canonical map, awaits worker `stop()` directly, cancels stragglers,
awaits worker `aclose()` directly, and closes the canonical `DBPoolBundle`
through direct `DBPoolBundle.aclose()`. Synchronous or non-awaitable scheduler
lifecycle hook results are malformed runtime wiring. The scheduler does not
close individual
`api_pool`, `worker_pool`, `lock_pool`, `tool_pool`, or `wake_pool`
attributes as a compatibility fallback; missing `db.aclose()` is runtime
wiring failure. Bootstrap failure cleanup follows the same boundary: once a
`DBPoolBundle` exists, startup unwind calls `db.aclose()` and records cleanup
failure as a note on the original startup error rather than duplicating pool
role knowledge. Provider cleanup follows explicit root lifecycle methods and
does not walk object graphs looking for arbitrary close methods. Runtime health
endpoints and CLI status must read worker state
from the scheduler's `workers` map, not bespoke top-level runtime fields.
When a worker owns an injected provider directly, its `on_close()` uses that
provider protocol's lifecycle method directly and fails malformed handles
instead of probing alternate method names.

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
limits, circuit breakers, timeouts, usage capture, and request/result audit
metadata. It does not own domain claims,
attempt counters, product audit tables, or read-model writes.

Workers that burn attempts when claiming DB work must reserve agent capacity,
circuit, and RPM before claiming. Batch workers must pass explicit
`rate_units` for the maximum provider calls they want to execute, then claim no
more rows than the actual `reservation.rate_units` returned by the gateway; one
reservation must not cover multiple unreserved model calls. This applies to
`pulse_candidate` and `news_item_brief`. If a
reservation is denied, the worker returns an `agent_backpressure_*` note and
leaves the job unclaimed. This preserves retry budgets during provider
congestion and lets the next bounded catch-up cycle retry naturally. For Pulse,
`pulse.decision` is reserved before job claim and covers all internal decision
audit stages. A no-start response from capacity, circuit, RPM, or reservation
pressure is backpressure, not a provider attempt.
Reservation release is synchronous resource accounting inside the gateway:
lane semaphores, global capacity, and RPM slots are released by a callback that
must return `None`. Awaitable release results are malformed agent execution
wiring and must not be awaited as compatibility cleanup.
No-start backpressure must not write business run ledgers or increment
business attempts. Provider-started validation, publication, schema, timeout,
or cancellation failures remain started execution failures and follow the
domain retry/audit policy with `execution_started=true`.
Signal Pulse releases provider-started pressure into a bounded provider
cooldown instead of the old 30-second retry loop. The job is returned to
`pending`, its claim attempt is decremented when execution did not start, and
`next_run_at_ms` is delayed by the lane/provider cooldown. This keeps outage
noise out of business retries while preserving audit only for execution that
actually started.
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
classification. These status surfaces read `runtime.agent_execution_gateway`
directly; `None` means disabled, while a malformed non-`None` gateway is a
runtime contract failure. They must not fall back to provider-bundle aliases.
Lane `priority` is an operator-facing label for
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
become a correctness dependency for projections. Its fan-out publisher is the
formal async WebSocket hub `publish(payload)` contract; synchronous callback
results are malformed runtime wiring, not alternate publish compatibility.

WebSocket fan-out must be bounded. Slow clients are stale subscribers to drop;
they must not stall worker publish paths or other clients.
Replay is part of that same public read contract: replay limit, filter
cardinality, and per-filter token replay budget are all bounded before
PostgreSQL reads begin. Token-filter replay then sends the selected
`cas`/`symbols` as one PostgreSQL keyset/window query with per-filter bucket
limits, so one subscribe message cannot fan out into one replay query per
filter. Replay payload hydration then batches projected event payload lookups
for the replay page instead of issuing per-event projection reads.

## News Provider Ingest

`news_fetch` is an interval catch-up worker over configured sources and
durable source cursors. OpenNews provider ingestion is REST-only through
bounded `/open/news_search` pages; it must not open short-lived WebSocket
subscribe cycles during a poll. If a future OpenNews streaming input is added,
it must be a separate provider input path that writes provider observations
into the same material-fact contract instead of sharing `news_fetch` control
flow or reintroducing hybrid fetch mode. The OpenNews REST HTTP poster is a
formal async contract and is awaited directly; synchronous poster results are
malformed runtime wiring, not a compatibility mode to detect with
`inspect.isawaitable(...)`. The sync worker bridge accepts the formal coroutine
created by the REST fetch and closes it directly if `fetch()` is misused from an
active event loop; arbitrary awaitables without `close()` are malformed private
bridge inputs, not compatibility shapes. REST scan budgets are formal runtime
policy: source policy or worker/cursor inputs must provide page size, max pages,
and overlap, and the integration client must not supply hidden defaults when
that policy is missing.

## Wake Hints And Durable Work

PostgreSQL `NOTIFY` channels (`market_tick_written`,
`market_tick_current_updated`, `resolution_updated`, `token_radar_updated`,
`macro_observations_imported`)
are wake hints, not delivery guarantees. Market tick writers wake
`MarketTickCurrentProjectionWorker`; Token Radar wakes from
`market_tick_current_updated` after the current market row changes.
`macro_sync` wakes `MacroViewProjectionWorker` after committed fact imports,
but wake failure never changes the committed sync result. Every listener
(`TokenRadarProjectionWorker`, `MacroViewProjectionWorker`,
`PulseCandidateWorker`, future workers) runs on a bounded
`interval_seconds` loop from `workers.yaml` even when `NOTIFY` is healthy. The
loop must claim durable dirty queues, honor due gates, or read bounded read
models; it must not scan broad fact windows just to prove no wake was missed.
Token Radar runtime projection has no recent-resolved-target catch-up scan.
Token Radar repair uses the explicit
`ops enqueue-token-radar-dirty-targets` command, and resolution refresh
uses `token_discovery_dirty_lookup_keys`. Service correctness must not
depend on `NOTIFY` delivery.

Wake emitters are still runtime contracts even though wakes are hints.
`WakeBus` is constructed from the dedicated wake-pool connection context
factory, enters that context, emits `pg_notify`, and commits the checked-out
connection. A factory that returns a raw connection without the context
protocol is malformed runtime wiring and fails before `pg_notify`; it is not a
supported compatibility path.

## One writer per read model

Each derived read model has exactly one runtime writer. A second runtime
writer of `token_radar_current_rows`, `token_radar_publication_state`,
`pulse_candidates`, or any future read model is both a reliability incident
and an architecture-test violation. The
canonical worker registry and worker inventory are architecture-guarded
so runtime ownership stays explicit. Ops paths and CLI rebuilds are
explicit exceptions and must call the same projection service the worker
uses; they do not run their own SQL.

Single-writer ownership does not by itself make a read model bounded. Current
serving projections must keep physical storage proportional to the product
surface they serve: target/window rows, active queue rows, or compact latest
series rows. Current serving primary keys must not include `generation_id`,
`run_id`, `attempt_id`, timestamp-derived ids, or UUIDs. Do not use permanent
generation tables or active-generation pointers as the serving lifecycle for
current read models unless the owning architecture document defines retention,
pruning, reader behavior, and tests. An active pointer can make readers correct
while storage still grows without a runtime bound. Workers that rebuild current
rows must have an unchanged path that is visible in publication state and writes
zero serving rows, usually through `payload_hash` or `IS DISTINCT FROM` gates.

Projection worker idle paths must be proportional to due dirty targets, not
to fact-table size. News projection workers claim durable dirty targets
(`news_projection_dirty_targets`) and then load payloads by explicit target ids
only. Runtime projection workers must not discover stale work by scanning
fact tables. News page projection row identity is stable by
`NEWS_PAGE_PROJECTION_VERSION` plus `story_key` when one exists, otherwise the
item id. Dirty target wakeup remains item-scoped for durable queue simplicity,
but the worker expands claimed items into a bounded story group before writing
one current `news_page_rows` row. Unchanged story rows keep the existing
`payload_hash IS DISTINCT FROM` zero-serving-write path. Runtime projection
workers must not discover stale work by scanning material facts or read models,
including missing-story scans, page-projection staleness scans, or
source-quality all-source/window scans. Broad coverage discovery is allowed
only in manual ops repair commands that enqueue dirty targets and do not write
read-model rows. Normal worker idle paths must be
proportional to queue depth, not to the size of `events`, `token_intents`,
`token_intent_resolutions`, or market tick fact tables.
News source-quality runtime follows the same rule: the worker processes durable
source refresh/window targets and expands configured windows inside that worker;
broad source/window coverage is an ops repair enqueue concern only.

The same dirty-target rule applies to runtime agent/profile tails:
`pulse_candidate`, `narrative_admission`, `token_profile_current`,
`token_image_mirror`, `asset_profile_refresh`, and `token_capture_tier` must
claim their control-plane rows first. `LivePriceGateway` reads the live target
control set from `token_capture_tier`; it must not scan Token Radar current
rows.
Historical discovery is domain-owned. Token Radar uses
`ops enqueue-token-radar-dirty-targets` for explicit bounded repair; other
workers must expose similarly explicit domain repair paths instead of a generic
runtime-worker repair command.

`macro_sync` follows the same claim-first rule: it claims a bounded
`macro_sync_windows` row before running macrodata, records retry or terminal
source-health outcomes in `macro_sync_runs`, and keeps FRED secrets out of
argv, logs, DB diagnostics, and API/CLI payloads. The macrodata child process
must have its own subprocess timeout (`macrodata_timeout_seconds`) because
canceling the worker thread does not kill a running child process.
The FRED env var name is a settings-owned policy: `null` or blank disables env
lookup, and runner/service code must not silently restore `FINANCE_FRED_API_KEY`.

## PostgreSQL Observability

The compose PostgreSQL service loads `pg_stat_statements`, PoWA,
`pg_stat_kcache`, `pg_qualstats`, and `pg_wait_sampling`, and writes slow
statement, lock-wait, checkpoint, temp-file, and autovacuum logs under
`~/.parallax/postgres-logs`. These signals are production
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
`fresh` is allowed only when publication state is `ready` and product/window
current rows are available; an explicitly empty ready publication is fresh with
zero rows. Failed latest attempts serve previous rows as `stale` or no rows as
`failed`; retired history/audit tables are not part of runtime serving.
`current_generation_id` remains attempt audit metadata, not an online serving
join key. `fresh`, `stale`, and `failed` describe publication freshness only;
row `quality_status` describes business credibility.
Projection-private `token_radar_target_features` and rank-source edge retention
is bounded maintenance owned by `TokenRadarProjectionWorker`; rank publication
does not perform retention prune work, and maintenance deletes are capped by the
worker batch limit.

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
uv run parallax ops enqueue-token-radar-dirty-targets --source events --since-ms 0 --dry-run
uv run parallax ops enqueue-token-radar-dirty-targets --source events --since-ms 0 --execute
uv run parallax ops rebuild-token-intents --window 24h --limit 5000 --projection-limit 5000
```

Cross-domain hard-cut cleanup commands, such as CEX Binance cleanup, may report
Token Radar rows that will become stale, but they do not delete Token Radar
tables directly. Run the domain rebuild path after those fact-level cleanups so
Token Radar reprojects from the updated facts.

Watchlist handle-summary agent tables and their signal-stats backfill were
retired in the 2026-05-30 hard cut that dropped
`watchlist_handle_signal_stats` and related social/watchlist agent storage.
Do not run or reintroduce `ops backfill-watchlist-signal-stats`; rebuilding
watchlist intelligence now requires a new product contract and schema instead
of replaying the retired command.

## Provider connection state

Streaming providers (OKX DEX WS, GMGN direct WS, and any future streaming
source) expose a connection state with a `last_state_change_at_ms` and
publish it through `/api/status`. State values are `disconnected`,
`connecting`, `authenticating`, `subscribed`, `streaming`, and `failed`.
Capture workers must expose provider state changes through status payloads so
operators can tell the difference between stale markets and stale projections.
GMGN DirectWS also treats frame delivery as a formal async collector contract:
`on_frame(frame)` is awaited directly and must not be accepted through
conditional await compatibility.

Provider lifecycle cleanup is owned by explicit roots and wrapper contracts,
not reflection. Runtime roots call `WiredProviders.aclose()` and gateway
`aclose()` methods directly. Provider wiring wrappers that own synchronous
providers call the wrapped provider `close()` contract directly, and startup
partial-cleanup records missing `close()` as failure evidence on the original
exception instead of silently skipping malformed providers.

## Snapshot gate observability

`CollectorService` exposes snapshot gate outcome counters
(`immediate_complete`, `debounced_complete`, `debounced_timeout`,
`non_tw_channel`) through `/api/status`. A non-trivial `debounced_timeout`
rate is a reliability signal even when raw ingest looks healthy.
