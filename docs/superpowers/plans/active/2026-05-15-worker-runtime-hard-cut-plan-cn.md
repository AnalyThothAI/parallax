# Worker Runtime 平台 Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for parallel implementation, or `superpowers:executing-plans` if executing serially. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 12 个长期运行 worker 一次性迁移到统一 `WorkerBase + DBPoolBundle + WakeWaiter + LLMGateway + WorkerScheduler` 运行平台；删除旧生命周期、旧 `/readyz` worker section、旧 worker runtime 配置读取路径，不保留兼容层。

**Architecture:** 单 ASGI 进程不变；`runtime.bootstrap()` 成为进程级副作用唯一入口；`workers.yaml` 成为 worker runtime knobs 唯一配置源；所有 worker 通过 `db.worker_session(name)` 短借连接并通过 `WorkerResult` 自动进入 metrics/status；`IngestService` 保持 per-frame 事务服务，只作为合规参照进入测试矩阵。

**Tech Stack:** Python 3.13, FastAPI, psycopg3 pool, PostgreSQL LISTEN/NOTIFY, OpenAI Agents SDK, `aiolimiter`, `prometheus-client`, Pydantic v2, pytest, ruff, OpenAPI generated frontend types.

---

## Status

**Status**: Ready for implementation
**Date**: 2026-05-15
**Owning spec**: `docs/superpowers/specs/active/2026-05-15-worker-runtime-platform-cn.md`
**Suggested branch**: `codex/worker-runtime-hard-cut`
**Suggested worktree**: `.worktrees/worker-runtime-hard-cut/`

## Pre-flight

- [x] Spec corrected to 12 long-running workers + 1 `IngestService` reference row.
- [ ] Create/switch to `codex/worker-runtime-hard-cut` in an isolated worktree.
- [ ] Capture baseline with `uv run ruff check .`.
- [ ] Capture baseline with `uv run pytest tests/unit/test_settings.py tests/unit/test_postgres_client.py tests/unit/test_providers_wiring.py tests/integration/test_api_health.py -q`.
- [ ] Record any unrelated dirty files before editing; do not revert them.

## Invariants

- [ ] No compatibility aliases, adapter shims, dual runtime scheduler, old worker config fallback, or old `/readyz` worker section double-write.
- [ ] All 12 long-running workers inherit `WorkerBase`: `collector`, `anchor_price`, `live_price_gateway`, `resolution_refresh`, `asset_profile_refresh`, `token_radar_projection`, `pulse_candidate`, `enrichment`, `handle_summary`, `harness_ops`, `notification_rule`, `notification_delivery`.
- [ ] `IngestService` does not become a worker and does not get a `workers.yaml` key.
- [ ] Worker code never opens raw pools or calls `repository_session(pool)` directly.
- [ ] `db.worker_session(name)` block contains no external IO, including sync provider/client/market/adapter calls.
- [ ] Process-global setters are limited to `runtime.bootstrap()` and the bootstrap-constructed `LLMGateway`; worker/provider constructors never call them directly.
- [ ] `workers.yaml` is the only source for worker `enabled`, `interval_seconds`, `timeout_seconds`, `concurrency`, `batch_size`, `max_attempts`, leases, wake channels, and per-worker runtime knobs.
- [ ] `/readyz` keeps global health fields, but all worker state is under a single top-level `workers` map.

## Canonical Worker Keys

| Key | Class | Mode | Enabled condition |
|---|---|---|---|
| `collector` | `CollectorService` | continuous | `start_collector` and upstream client configured |
| `anchor_price` | `AnchorPriceWorker` | poll | CEX or DEX quote provider configured |
| `live_price_gateway` | `LivePriceGateway` | continuous cycle | OKX DEX WS or CEX market configured |
| `resolution_refresh` | `ResolutionRefreshWorker` | poll | OKX DEX discovery configured |
| `asset_profile_refresh` | `AssetProfileRefreshWorker` | poll | GMGN exact-token profile provider configured |
| `token_radar_projection` | `TokenRadarProjectionWorker` | wake + catch-up | always enabled unless YAML disables |
| `pulse_candidate` | `PulseCandidateWorker` | wake + catch-up | YAML enabled and LLM pulse model configured |
| `enrichment` | `EnrichmentWorker` | job queue | YAML enabled and LLM base model configured |
| `handle_summary` | `HandleSummaryWorker` | job queue | YAML enabled and watchlist summary model configured |
| `harness_ops` | `HarnessOpsWorker` | poll | YAML enabled |
| `notification_rule` | `NotificationWorker` | poll/event | notifications enabled |
| `notification_delivery` | `NotificationDeliveryWorker` | job queue/event | at least one external delivery channel configured |

Advisory lock keys are stable local constants:

| Worker | Key |
|---|---:|
| `token_radar_projection` | `2026051501` |
| `pulse_candidate` | `2026051502` |

## File-level Edits

### Runtime platform files

Create:

- `src/parallax/app/runtime/bootstrap.py`
- `src/parallax/app/runtime/db_pool_bundle.py`
- `src/parallax/app/runtime/job_queue.py`
- `src/parallax/app/runtime/llm_gateway.py`
- `src/parallax/app/runtime/telemetry.py`
- `src/parallax/app/runtime/wake_waiter.py`
- `src/parallax/app/runtime/worker_base.py`
- `src/parallax/app/runtime/worker_registry.py`
- `src/parallax/app/runtime/worker_result.py`
- `src/parallax/app/runtime/worker_scheduler.py`

Modify:

- `src/parallax/app/runtime/app.py`
- `src/parallax/app/runtime/providers_wiring.py`
- `src/parallax/app/runtime/repository_session.py`
- `src/parallax/app/runtime/wake_bus.py`
- `src/parallax/app/surfaces/api/schemas.py`
- `src/parallax/app/surfaces/cli/main.py`
- `src/parallax/platform/config/settings.py`
- `src/parallax/platform/db/postgres_client.py`
- `src/parallax/platform/paths/runtime_paths.py`
- `pyproject.toml` and `uv.lock`

### Worker files

Modify all current long-running worker classes:

- `src/parallax/domains/ingestion/runtime/collector_service.py`
- `src/parallax/domains/asset_market/runtime/anchor_price_worker.py`
- `src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py`
- `src/parallax/domains/asset_market/runtime/live_price_gateway.py`
- `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`
- `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`
- `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- `src/parallax/domains/social_enrichment/runtime/enrichment_worker.py`
- `src/parallax/domains/watchlist_intel/runtime/handle_summary_worker.py`
- `src/parallax/domains/closed_loop_harness/runtime/harness_ops_worker.py`
- `src/parallax/domains/notifications/runtime/notification_worker.py`
- `src/parallax/domains/notifications/runtime/notification_delivery.py`

Modify domain service helpers where current code performs provider IO inside a repository session:

- `src/parallax/domains/asset_market/services/anchor_price_observation.py`
- `src/parallax/domains/asset_market/services/asset_profile_refresh.py`
- `src/parallax/domains/token_intel/runtime/token_resolution_refresh.py`
- `src/parallax/domains/watchlist_intel/services/handle_summary_service.py`

Modify OpenAI provider clients:

- `src/parallax/integrations/openai_agents/pulse_decision_agent_client.py`
- `src/parallax/integrations/openai_agents/social_event_agent_client.py`
- `src/parallax/integrations/openai_agents/watchlist_summary_agent_client.py`

### Tests

Create:

- `tests/unit/test_worker_settings.py`
- `tests/unit/test_worker_result.py`
- `tests/unit/test_db_pool_bundle.py`
- `tests/unit/test_worker_base_runtime.py`
- `tests/unit/test_worker_scheduler.py`
- `tests/unit/test_wake_waiter.py`
- `tests/unit/test_llm_gateway.py`
- `tests/architecture/test_worker_runtime_contracts.py`

Modify existing focused tests for every migrated worker:

- `tests/unit/test_collector_service.py`
- `tests/unit/test_anchor_price_worker.py`
- `tests/unit/test_asset_profile_refresh_worker.py`
- `tests/unit/test_resolution_refresh_worker.py`
- `tests/unit/test_live_price_gateway.py`
- `tests/unit/test_token_radar_projection_worker.py`
- `tests/unit/test_pulse_candidate_worker.py`
- `tests/unit/test_enrichment_worker_runtime.py`
- `tests/unit/domains/watchlist_intel/test_handle_summary_worker.py`
- `tests/integration/test_harness_ops.py`
- `tests/unit/test_notification_worker_runtime.py`
- `tests/integration/test_notification_delivery.py`
- `tests/integration/test_api_health.py`
- `tests/integration/test_cli.py`
- `tests/contract/test_openapi_drift.py`

### Docs/generated

Modify:

- `docs/WORKERS.md`
- `docs/CONTRACTS.md`
- `docs/RELIABILITY.md`
- `docs/SETUP.md`
- `docs/TESTING.md`
- `docs/generated/openapi.json`
- `docs/generated/cli-help.md`
- `web/src/lib/types/openapi.ts`
- frontend tests/fixtures that assert `/readyz` shape.

## Workers YAML Contract

### Paths

- `config.yaml`: application, provider, API, storage, notification rules/channels, LLM credentials/model/trace config.
- `workers.yaml`: worker runtime config only.
- `runtime_paths.py` exports `WORKERS_CONFIG_FILE_NAME = "workers.yaml"` and `workers_config_path(app_home_override=None)`.

### Default file

`write_default_config(force=...)` writes both files. If either file exists and `force=False`, it preserves the existing file and reports both paths. `load_settings()` requires both files; missing `workers.yaml` is a startup error with the same explicit style as missing `config.yaml`.

Default `workers.yaml`:

```yaml
defaults:
  enabled: true
  interval_seconds: 5.0
  timeout_seconds: 120.0
  concurrency: 1
  batch_size: 100
  max_attempts: 3
  lease_ms: 120000
  restart_locally: false
  statement_timeout_seconds: 30.0
  backoff:
    kind: "exponential"
    base_ms: 1000
    max_ms: 60000

collector:
  enabled: true
  mode: "continuous"
  interval_seconds: 3.0
  timeout_seconds: 0.0
  snapshot_timeout_seconds: 0.5
  watchdog_interval_seconds: 30.0
  stale_timeout_seconds: 180.0

anchor_price:
  enabled: true
  interval_seconds: 5.0
  batch_size: 100

live_price_gateway:
  enabled: true
  mode: "continuous"
  interval_seconds: 30.0
  batch_size: 100
  subscription_limit: 100
  hot_target_ttl_seconds: 300.0
  reconnect_delay_seconds: 3.0
  cex_poll_interval_seconds: 30.0
  live_observation_heartbeat_seconds: 60.0
  live_observation_min_price_change_pct: 0.005
  live_observation_min_write_interval_seconds: 5.0

resolution_refresh:
  enabled: true
  interval_seconds: 30.0
  batch_size: 50
  reprocess_limit: 500
  chain_ids: ["solana", "eip155:1", "eip155:56", "eip155:8453", "ton"]

asset_profile_refresh:
  enabled: true
  interval_seconds: 60.0
  batch_size: 50

token_radar_projection:
  enabled: true
  interval_seconds: 10.0
  batch_size: 100
  statement_timeout_seconds: 120.0
  advisory_lock_key: 2026051501
  wakes_on: ["market_observation_written", "resolution_updated"]
  windows: ["5m", "1h", "4h", "24h"]
  scopes: ["all", "matched"]
  hot_windows: ["5m"]

pulse_candidate:
  enabled: true
  interval_seconds: 60.0
  batch_size: 10
  max_attempts: 3
  advisory_lock_key: 2026051502
  wakes_on: ["token_radar_updated"]
  windows: ["5m", "1h", "4h", "24h"]
  scopes: ["all", "matched"]
  trigger_thresholds:
    min_rank_score: 45
  gate_thresholds:
    trade_candidate_min: 72
    token_watch_min: 45
    high_info_rejection_min: 30
    high_conviction_min: 78

enrichment:
  enabled: true
  interval_seconds: 2.0
  concurrency: 4
  batch_size: 1
  max_attempts: 3

handle_summary:
  enabled: true
  interval_seconds: 2.0
  concurrency: 1
  batch_size: 1
  lease_ms: 120000
  max_attempts: 3
  reconcile_limit: 100
  signal_threshold: 10
  time_threshold_ms: 1800000
  min_interval_ms: 300000
  input_limit: 80
  window_days: 7

harness_ops:
  enabled: true
  interval_seconds: 60.0
  batch_size: 200

notification_rule:
  enabled: true
  interval_seconds: 5.0
  batch_size: 50

notification_delivery:
  enabled: true
  interval_seconds: 5.0
  batch_size: 1
  max_attempts: 5
```

### Settings changes

- Add `WorkersSettings`, `WorkerDefaults`, `PerWorkerSettings`, `BackoffPolicy`, and concrete typed per-worker settings in `platform/config/settings.py`.
- Add `Settings.workers: WorkersSettings`.
- Remove worker runtime fields from `LlmConfig`, `CollectorConfig`, root live-observation fields, and `NotificationsConfig.poll_interval_seconds`.
- Keep LLM credential/model/trace fields in `LlmConfig`: provider, api key, base model, base URL, timeout, trace config, `pulse_agent_model`, `watchlist_handle_summary_model`.
- Keep notification rule/channel business config in `NotificationsConfig`; only polling/delivery runtime moves to `workers.yaml`.
- Update `parallax config` output to include `workers_config_path` and a `workers` map generated from `settings.workers`.

## Implementation Steps

### 1. Config hard cut

- [ ] Add `workers_config_path()` and `WORKERS_CONFIG_FILE_NAME` to `runtime_paths.py`.
- [ ] Add `default_workers_yaml()` and `write_default_workers_config()` to `settings.py`.
- [ ] Change `write_default_config()` to write `config.yaml` and `workers.yaml`.
- [ ] Change `load_settings()` to load `config.yaml`, load `workers.yaml`, validate both with Pydantic `extra="forbid"`, and attach the parsed worker settings to `Settings`.
- [ ] Remove old worker runtime properties such as `settings.enrichment_poll_interval`, `settings.pulse_agent_batch_size`, `settings.watchlist_handle_summary_poll_interval_seconds`, and `settings.notifications.poll_interval_seconds`.
- [ ] Update default `config.yaml` text so it no longer contains worker runtime knobs.
- [ ] Add unit tests covering unknown `workers.yaml` key rejection, missing `workers.yaml` startup error, default file creation, and old `config.yaml` worker fields rejection.

Verification:

```bash
uv run pytest tests/unit/test_settings.py tests/unit/test_worker_settings.py tests/integration/test_cli.py -q
```

### 2. Runtime primitives

- [ ] Add `WorkerResult` as frozen slots dataclass with `processed`, `failed`, `dead`, `skipped`, and `notes`.
- [ ] Add `TelemetryRegistry` with in-process metric objects for processing seconds, jobs total, jobs in flight, last run, lag, pool wait, and queue depth.
- [ ] Add `/metrics` support using `prometheus-client`; add direct dependencies `aiolimiter` and `prometheus-client` to `pyproject.toml`.
- [ ] Extend `postgres_client.create_pool()` with `application_name`, `statement_timeout_seconds`, `idle_in_transaction_session_timeout_seconds`, and TCP keepalive options.
- [ ] Add `DBPoolBundle.create(settings)` to build API, worker, and wake pools with distinct options.
- [ ] Add `DBPoolBundle.api_session()` and `DBPoolBundle.worker_session(name, statement_timeout_seconds=None)` context managers.
- [ ] In `worker_session(name)`, execute `SET application_name = %s` on checkout before yielding repositories, and restore `application_name='gmgn_worker'` on exit.
- [ ] Measure pool wait time around pool checkout and record it under `pool_wait_ms`.
- [ ] Add `DBPoolBundle.acquire_advisory_lock_connection(worker_name, key)` that returns a dedicated connection only after `pg_try_advisory_lock(key)` succeeds.
- [ ] Add `WakeWaiter` with `wait(timeout)` and `wake()`; it LISTENs on configured channels through the wake pool, reconnects on failure, and always returns on timeout for catch-up.
- [ ] Keep `WakeBus` emit-only, but construct it through `DBPoolBundle.wake_emitter()` instead of raw pool factories.
- [ ] Add `JobQueue` with allowlisted table descriptors instead of arbitrary table strings; initial descriptors cover enrichment jobs, watchlist summary jobs, pulse jobs, and notification deliveries only where repositories already expose matching methods.

Verification:

```bash
uv run pytest tests/unit/test_worker_result.py tests/unit/test_db_pool_bundle.py tests/unit/test_wake_waiter.py tests/unit/test_postgres_client.py -q
```

### 3. WorkerBase and WorkerScheduler

- [ ] Implement `WorkerBase` constructor with `name`, `settings`, `db`, `telemetry`, optional `llm`, `wake_waiter`, `job_queue`, and `logger`.
- [ ] `WorkerBase.run()` handles `on_start()`, optional advisory lock acquisition, iteration loop, timeout, exception backoff, metrics, `last_*` status fields, wake wait, and `on_stop()`.
- [ ] `WorkerBase.run_once()` is abstract and async; sync-heavy workers implement `async run_once()` by calling `asyncio.to_thread(self._run_once_sync, ...)`.
- [ ] `WorkerBase.stop()` sets an event and wakes `WakeWaiter`.
- [ ] `WorkerBase.aclose()` calls subclass close hooks and releases advisory lock connection.
- [ ] Add `WorkerStatus` payload method with `enabled`, `running`, `last_started_at_ms`, `last_finished_at_ms`, `last_result`, `last_error`, `iteration_duration_p99_ms`, `queue_depth`, and `pool_wait_ms_p99`.
- [ ] Implement `WorkerScheduler` with dependency-aware start order: wake listeners/projections, emitter workers, LLM job workers, notifications, live gateway, collector last.
- [ ] `WorkerScheduler.stop()` stops workers, waits for in-flight iterations, cancels after timeout, closes workers, then closes pools.
- [ ] `WorkerScheduler.unhealthy_reasons()` replaces the worker sections in `_watchdog_unhealthy_reasons`.
- [ ] Add task naming via `asyncio.create_task(worker.run(), name=f"worker:{name}")`.

Verification:

```bash
uv run pytest tests/unit/test_worker_base_runtime.py tests/unit/test_worker_scheduler.py -q
```

### 4. Bootstrap hard cut

- [ ] Move DB pool creation from `app.py` into `bootstrap.py`.
- [ ] Move provider wiring into `bootstrap(settings, start_collector=...)` after `DBPoolBundle` and `LLMGateway` construction.
- [ ] Replace `CliRuntime` with `Runtime` that stores `settings`, `db`, `providers`, `hub`, `collector_status`, `workers`, `scheduler`, and read-only API repository access.
- [ ] Replace `_build_runtime`, `_start_runtime_tasks`, and `_stop_runtime` with calls to `bootstrap()`, `runtime.scheduler.start()`, and `runtime.aclose()`.
- [ ] Keep `create_app()` public signature unchanged.
- [ ] Add `/metrics` route returning Prometheus text.
- [ ] Replace `/readyz` worker-specific top-level sections with `workers: runtime.scheduler.status_payload()`.
- [ ] Keep top-level `ok`, `reasons`, `collector`, `snapshot_gate`, `handles`, `store`, `db`, and `provider_states`.
- [ ] Update `StatusData` schema to include `workers: dict[str, WorkerStatusData]` and remove explicit old worker section fields.

Verification:

```bash
uv run pytest tests/integration/test_api_health.py tests/unit/test_api_async_boundaries.py -q
```

### 5. LLMGateway

- [ ] Add `LLMGateway` with global `asyncio.Semaphore`, `AsyncLimiter`, tracing export key setup, and `run_with_limits(worker_name, stage, timeout_s, coro_factory)`.
- [ ] `LLMGateway.openai_client(model, base_url, timeout_s)` returns `AsyncOpenAI` with shared headers and `trust_env=False`.
- [ ] `set_tracing_export_api_key` is called only in `LLMGateway.__init__` when trace export is configured.
- [ ] Modify `wire_providers(settings, llm_gateway=...)`.
- [ ] Modify the three OpenAI clients so constructors receive `llm_gateway` and never call `set_tracing_export_api_key`.
- [ ] Wrap every `Runner.run(...)` call in `llm_gateway.run_with_limits(...)`, with `worker_name` and stage labels:
  - `enrichment` stage `social_event`
  - `pulse_candidate` stages `analyst`, `critic`, `judge`
  - `handle_summary` stage `summary`
- [ ] Preserve existing prompt/schema/audit logic inside the provider clients; gateway owns only rate limit, trace key, OpenAI client construction, timeout, and metrics.
- [ ] Update tests to inject a fake gateway instead of monkeypatching tracing setters.

Verification:

```bash
uv run pytest tests/unit/test_llm_gateway.py tests/unit/test_social_event_agent_client.py tests/unit/test_pulse_decision_agent_client.py tests/unit/test_watchlist_summary_agent_client.py tests/unit/test_providers_wiring.py -q
```

### 6. Worker migration group A: collector and asset-market workers

- [ ] `CollectorService` inherits `WorkerBase`; `run_once()` calls `upstream_client.run()` and returns when the upstream client exits or disconnects.
- [ ] Move collector `snapshot_timeout`, watchdog interval, and stale timeout to `settings.workers.collector`.
- [ ] Replace `_PooledIngestStore(worker_db_pool)` with a store that uses `db.worker_session("collector")`.
- [ ] Ensure collector publishes only after ingest transaction exits.
- [ ] `AnchorPriceWorker` inherits `WorkerBase`; split anchor work into select inputs, call CEX/DEX providers outside session, persist observations in a short session, then emit wake hints.
- [ ] `AssetProfileRefreshWorker` inherits `WorkerBase`; split due profile selection, GMGN profile calls, and profile writes.
- [ ] `ResolutionRefreshWorker` inherits `WorkerBase`; split lookup claim/start, OKX discovery/quote calls, persistence, reprocess, and wake emission into short sessions.
- [ ] `LivePriceGateway` inherits `WorkerBase`; read active targets in a short session, poll/stream providers outside session, persist each material observation in a short session.
- [ ] Fix `LivePriceGateway.provider_state_change`: store the stream provider state/epoch, pass `provider_state_change=True` to `should_persist_live_observation` on the first valid frame after provider state changes, and include reason breakdown in `WorkerResult.notes`.
- [ ] Move live observation thresholds and OKX WS runtime knobs from `config.yaml` call sites to `settings.workers.live_price_gateway`.

Verification:

```bash
uv run pytest tests/unit/test_collector_service.py tests/unit/test_anchor_price_worker.py tests/unit/test_asset_profile_refresh_worker.py tests/unit/test_resolution_refresh_worker.py tests/unit/test_live_price_gateway.py tests/benchmark/test_live_observation_write_budget.py -q
```

### 7. Worker migration group B: projection and Pulse

- [ ] `TokenRadarProjectionWorker` inherits `WorkerBase`, declares advisory lock key `2026051501`, uses `WakeWaiter` for `market_observation_written` and `resolution_updated`, and returns `WorkerResult`.
- [ ] Remove or de-publicize `token_resolution_refresh.rebuild_token_radar_windows`; CLI rebuild paths must call the same `TokenRadarProjection` service under the projection worker ownership boundary, not bypass the worker writer contract.
- [ ] Keep ops CLI projection/rebuild commands as explicit operator paths; they must not introduce a second runtime writer.
- [ ] `PulseCandidateWorker` inherits `WorkerBase`, declares advisory lock key `2026051502`, uses `WakeWaiter` for `token_radar_updated`, and returns `WorkerResult`.
- [ ] Move Pulse interval, batch, attempts, trigger thresholds, gate thresholds, windows, and scopes to `settings.workers.pulse_candidate`.
- [ ] Fix `pulse_agent_run_steps.started_at_ms` so every step records its real start time rather than copying `finished_at_ms`.
- [ ] Fill `usage_json` from OpenAI/Agents SDK usage metadata when available; store `{}` only when the SDK truly returns no usage.
- [ ] Ensure Pulse LLM calls enter only through provider client methods already wrapped by `LLMGateway`.

Verification:

```bash
uv run pytest tests/unit/test_token_radar_projection_worker.py tests/unit/test_token_resolution_refresh.py tests/unit/test_pulse_candidate_worker.py tests/e2e/test_pulse_agent_runtime_flow.py -q
```

### 8. Worker migration group C: LLM job workers

- [ ] `EnrichmentWorker` inherits `WorkerBase`; replace its private concurrency loop with scheduler-managed `settings.concurrency` tasks for the same worker key.
- [ ] Add `last_started_at_ms`, `last_finished_at_ms`, and `WorkerResult` status to enrichment.
- [ ] Keep claim/read/model/write stages as separate short sessions; no provider call occurs inside a session.
- [ ] Keep watchlist summary enqueue hook inside the final materialization transaction, because it is a local repository write and not external IO.
- [ ] `HandleSummaryWorker` inherits `WorkerBase`; replace `service.summarize_handle()` while holding a repository session.
- [ ] Split handle summary into:
  - claim due jobs in a short session,
  - load events/context in a short session,
  - call summary provider through `LLMGateway` outside session,
  - persist summary run and mark job success/failure in a short session.
- [ ] Move handle summary runtime and trigger knobs to `settings.workers.handle_summary`.
- [ ] Ensure failed summary runs still write `usage_json={}` and job error in one short transaction.

Verification:

```bash
uv run pytest tests/unit/test_enrichment_worker_runtime.py tests/integration/test_enrichment_worker.py tests/unit/domains/watchlist_intel/test_handle_summary_worker.py tests/integration/watchlist/test_watchlist_intel_repository.py -q
```

### 9. Worker migration group D: harness and notifications

- [ ] `HarnessOpsWorker` inherits `WorkerBase`; add `last_started_at_ms`, `last_finished_at_ms`, and structured `WorkerResult`.
- [ ] Split harness operations into short sessions per stage: materialize, settle 6h, settle 24h, credit 6h, credit 24h, weights.
- [ ] Move `poll_interval`, `batch_limit`, and horizons to `settings.workers.harness_ops`.
- [ ] `NotificationWorker` inherits `WorkerBase`; keep rule evaluation in a sync thread and repository session, then publish notification payloads after session exit.
- [ ] Move notification worker poll/batch config to `settings.workers.notification_rule`.
- [ ] `NotificationDeliveryWorker` inherits `WorkerBase`; move initial DB claim/read/failure branches into `asyncio.to_thread` so synchronous SQL does not run on the event loop.
- [ ] Keep external Apprise/PushDeer calls outside DB sessions.
- [ ] Add an in-process wake event from `NotificationWorker` to `NotificationDeliveryWorker` after external deliveries are enqueued; `notification_delivery` still keeps bounded interval catch-up.
- [ ] Move notification delivery poll/batch/attempt config to `settings.workers.notification_delivery`.

Verification:

```bash
uv run pytest tests/integration/test_harness_ops.py tests/unit/test_notification_worker_runtime.py tests/integration/test_notification_worker.py tests/integration/test_notification_delivery.py -q
```

### 10. Architecture tests

- [ ] `test_all_long_running_workers_inherit_worker_base` scans the 12 canonical classes and fails on any missing subclass.
- [ ] `test_worker_registry_matches_workers_yaml_schema` asserts registry keys, YAML keys, scheduler keys, and `docs/WORKERS.md` keys are the same set.
- [ ] `test_no_external_io_inside_db_session` AST-scans worker modules for `db.worker_session(...)` blocks containing awaited or sync calls to client/provider/market/adapter objects.
- [ ] `test_workers_do_not_call_repository_session_or_raw_pool` rejects `repository_session(` and `.connection()` inside worker modules outside `DBPoolBundle` and tests.
- [ ] `test_process_global_setters_only_in_bootstrap` allowlists `app/runtime/bootstrap.py` and `app/runtime/llm_gateway.py` for tracing/logging/OTel setters.
- [ ] `test_no_old_readyz_worker_sections` rejects old top-level `/readyz` keys in API schema/fixtures.
- [ ] `test_no_old_worker_runtime_settings` rejects old runtime fields in `LlmConfig`, `CollectorConfig`, root `Settings`, and `NotificationsConfig`.
- [ ] `test_read_model_single_writers` rejects runtime writes to `token_radar_rows` outside `TokenRadarProjectionWorker`/projection service ownership.

Verification:

```bash
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture -q
```

### 11. API, CLI, frontend contract updates

- [ ] Update `/readyz` integration tests to assert the new `workers` map and absence of old worker sections.
- [ ] Update `/api/status` if it mirrors readiness data, keeping public fields documented in `CONTRACTS.md`.
- [ ] Add `parallax ops worker-status` to print the same worker map as `/readyz` plus queue depths.
- [ ] Update `parallax config` output to show both config files and effective worker settings.
- [ ] Run `make regen-contract` to update `docs/generated/openapi.json` and `web/src/lib/types/openapi.ts`.
- [ ] Update frontend fixtures/tests that use `StatusData` or `/readyz` payloads.
- [ ] Update `docs/generated/cli-help.md` after CLI surface changes.

Verification:

```bash
uv run pytest tests/integration/test_api_health.py tests/integration/test_cli.py tests/contract/test_openapi_drift.py -q
cd web && npm test -- --run
```

### 12. Documentation update

- [ ] Update `docs/WORKERS.md`: all workers now inherit `WorkerBase`; adding a worker means adding registry entry + `workers.yaml` schema + docs row + architecture test fixture.
- [ ] Update `docs/CONTRACTS.md`: `config.yaml` is application/provider config; `workers.yaml` is worker runtime config; `/readyz` worker data is under `workers`.
- [ ] Update `docs/RELIABILITY.md`: foreground-only run model now has two config files, and worker pool/session observability is enforced by `DBPoolBundle`.
- [ ] Update `docs/SETUP.md`: `init` creates both `config.yaml` and `workers.yaml`.
- [ ] Update `docs/TESTING.md`: worker inventory guard now references `WorkerBase`, `worker_registry`, and `workers.yaml`.
- [ ] Update owning domain `ARCHITECTURE.md` files where stage maps mention old worker lifecycle or config fields.

Verification:

```bash
uv run pytest tests/integration/test_docs_generated.py tests/architecture/test_completion_gates.py -q
```

### 13. Final verification

- [ ] Run lint.
- [ ] Run unit tests.
- [ ] Run architecture tests.
- [ ] Run contract tests.
- [ ] Run integration/e2e gate.
- [ ] Manually inspect `/readyz` and `/metrics` from a local running service.

Commands:

```bash
uv run ruff check .
uv run pytest tests/unit -q
uv run pytest tests/architecture -q
uv run pytest tests/contract -q
uv run pytest tests/integration/test_api_health.py tests/integration/test_cli.py tests/integration/test_notification_delivery.py -q
make check-all
```

Manual smoke:

```bash
uv run parallax init --force
uv run parallax config
uv run parallax serve
curl -s http://127.0.0.1:8765/readyz | jq '.workers'
curl -s http://127.0.0.1:8765/metrics | rg 'worker_processing_seconds|worker_jobs_total|worker_pool_wait'
```

## Parallel Execution Map

Use this split only after steps 1-3 define shared contracts.

| Stream | Owns | Files |
|---|---|---|
| Runtime core | `DBPoolBundle`, `WorkerBase`, scheduler, metrics, wake waiter | `app/runtime/*`, runtime unit tests |
| Config/API | `workers.yaml`, settings, CLI, `/readyz`, `/metrics`, generated contracts | `platform/config`, `app/runtime/app.py`, API schemas, CLI, docs/generated, web types |
| Provider gateway | `LLMGateway`, OpenAI clients, providers wiring | `app/runtime/llm_gateway.py`, `integrations/openai_agents/*`, `providers_wiring.py` |
| Asset workers | collector + asset-market short-session migration | `domains/ingestion`, `domains/asset_market` |
| Intel workers | token radar + Pulse + LLM job workers | `domains/token_intel`, `domains/pulse_lab`, `domains/social_enrichment`, `domains/watchlist_intel` |
| Ops workers | harness + notifications | `domains/closed_loop_harness`, `domains/notifications` |
| Architecture/docs | AST guards and docs | `tests/architecture`, `docs/*` |

Merge order: runtime core → config/API → provider gateway → worker groups → architecture/docs final tighten. Architecture tests may start red while shared contracts land, but no worker group is complete until its focused tests and architecture tests are green.

## Cutover Notes

- Existing local deployments must run `parallax init --force` or create `workers.yaml` explicitly after this hard cut; the process refuses to infer worker settings from old `config.yaml`.
- Old `/readyz` consumers must switch to `payload.workers.<worker_key>` in the same deployment.
- The implementation should prefer small commits per step, but the final branch has no runtime compatibility layer and no dual config reader.
