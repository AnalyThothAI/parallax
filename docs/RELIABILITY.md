# Reliability

> **Scope.** Owns operational invariants that must hold in any deployment of this service. Setup commands live in `SETUP.md`; security policy in `SECURITY.md`.

## Single ASGI worker

One ASGI worker. Multiple workers duplicate the upstream collector. If collector and API must scale separately, split them into distinct processes.

## PostgreSQL pool isolation

`DBPoolBundle` owns separate PostgreSQL pools for HTTP/WebSocket reads
(`api_pool`), background workers (`worker_pool`), and wake listeners /
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

## Coverage semantics

`coverage=public_stream` flags events as filtered from GMGN's anonymous public stream — not a full Twitter firehose guarantee. Do not advertise broader coverage in payloads or docs.

## MCP boundary

MCP / FastMCP is optional control / query infrastructure only. `/ws` is the production live push channel; do not route real-time events through MCP.

## Pulse Agent Audit Ledger

Signal Pulse agent decisions must be replayable from PostgreSQL. Every worker
run writes `pulse_agent_runs`; every Analyst / Critic / Judge stage, plus
research-only short-circuits, writes `pulse_agent_run_steps`.
`pulse_agent_run_steps.prompt_text` is operational audit data and must never
include secrets, cookies, auth headers, raw `.env` values, or private provider
credentials. Rows with insufficient data finish as abstain decisions instead of
inventing confidence or a display status.

## Material observation write budget

Live market frames are persisted to `price_observations(kind='decision_latest')`
only through
`domains/asset_market/services/live_observation_policy.should_persist_live_observation`.
Persistence triggers are exactly `first_seen`, `heartbeat`,
`significant_price_change`, `gate_field_change`, and
`provider_state_change`. Every other valid frame may update the in-process
cache and fan out over WS, but it is not a fact. The synthetic flat-market
budget is `100 targets × 5 fps × 10 minutes → ≤ 1500 persisted rows`, guarded
by `tests/benchmark/test_live_observation_write_budget.py`. Tightening the
thresholds is a config change; loosening them requires a benchmark update in
the same commit.

## Wake hints and catch-up

PostgreSQL `NOTIFY` channels (`market_observation_written`,
`resolution_updated`, `token_radar_updated`) are wake hints, not delivery
guarantees. Every listener
(`TokenRadarProjectionWorker`, `PulseCandidateWorker`, future workers) runs
on a bounded `interval_seconds` catch-up loop from `workers.yaml` even
when `NOTIFY` is healthy. A dropped `NOTIFY` recovers on the next
interval; service correctness must not depend on `NOTIFY` delivery.

## One writer per read model

Each derived read model has exactly one runtime writer. A second runtime
writer of `token_radar_rows`, `pulse_candidates`, or any future read model
is both a reliability incident and an architecture-test violation. The
canonical worker registry and worker inventory are architecture-guarded
so runtime ownership stays explicit. Ops paths and CLI rebuilds are
explicit exceptions and must call the same projection service the worker
uses; they do not run their own SQL.

## Provider connection state

Streaming providers (OKX DEX WS, GMGN direct WS, and any future streaming
source) expose a connection state with a `last_state_change_at_ms` and
publish it through `/api/status`. State values are `disconnected`,
`connecting`, `authenticating`, `subscribed`, `streaming`, and `failed`.
Workers must treat `provider_state_change=true` as a `first_seen`-equivalent
budget trigger so the first fresh frame after recovery is persisted.

## Snapshot gate observability

`CollectorService` exposes snapshot gate outcome counters
(`immediate_complete`, `debounced_complete`, `debounced_timeout`,
`non_tw_channel`) through `/api/status`. A non-trivial `debounced_timeout`
rate is a reliability signal even when raw ingest looks healthy.
