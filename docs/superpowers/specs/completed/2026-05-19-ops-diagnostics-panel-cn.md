# Ops Diagnostics Panel Spec

**Status**: Implemented
**Date**: 2026-05-19
**Owner**: Codex with Qinghuan
**Related**: `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`

## Background

当前项目已经有一组分散的可观测入口，但它们服务的是机器探活、局部页面或 CLI，不是一个面向操作员的诊断面板。

- FastAPI runtime 在启动时 bootstrap `Runtime`，启动 scheduler，并把 runtime 放到 `app.state.service`；同时提供 `/healthz`、`/readyz`、`/metrics`、`/ws` 和前端静态挂载，见 `src/parallax/app/runtime/app.py:30`、`src/parallax/app/runtime/app.py:38`、`src/parallax/app/runtime/app.py:57`、`src/parallax/app/runtime/app.py:59`、`src/parallax/app/runtime/app.py:63`、`src/parallax/app/runtime/app.py:69`、`src/parallax/app/runtime/app.py:77`。
- `/api/status` 已经聚合 DB health、provider connection state、snapshot gate 和 worker payload，见 `src/parallax/app/runtime/app.py:139`、`src/parallax/app/runtime/app.py:151`、`src/parallax/app/runtime/app.py:152`、`src/parallax/app/runtime/app.py:156`、`src/parallax/app/surfaces/api/routes_status.py:53`。
- Worker status 可以补齐 canonical worker，并能从部分 DB-backed queue 表填充 queue depth，见 `src/parallax/app/runtime/worker_status.py:5`、`src/parallax/app/runtime/worker_status.py:26`、`src/parallax/app/runtime/worker_status.py:57`、`src/parallax/app/runtime/worker_status.py:75`。
- Job queue 已经有 allowlisted descriptor，包括 `enrichment_jobs`、`watchlist_handle_summary_jobs`、`pulse_agent_jobs`、`notification_deliveries`，见 `src/parallax/app/runtime/job_queue.py:19`、`src/parallax/app/runtime/job_queue.py:32`、`src/parallax/app/runtime/job_queue.py:45`、`src/parallax/app/runtime/job_queue.py:51`、`src/parallax/app/runtime/job_queue.py:61`。
- Provider wiring 已经把 provider 按领域聚合进 `WiredProviders`，asset market provider 还携带 `ProviderHealth` 列表，见 `src/parallax/app/runtime/provider_wiring/types.py:28`、`src/parallax/app/runtime/provider_wiring/types.py:38`、`src/parallax/app/runtime/provider_wiring/types.py:81`、`src/parallax/domains/asset_market/providers.py:19`、`src/parallax/app/runtime/provider_wiring/asset_market.py:74`、`src/parallax/app/runtime/provider_wiring/asset_market.py:86`。
- API router 目前按 surface include 各领域路由，新增 ops 路由应同样挂在 `/api` 下，见 `src/parallax/app/surfaces/api/http.py:22`、`src/parallax/app/surfaces/api/http.py:24`、`src/parallax/app/surfaces/api/http.py:33`。
- Frontend 已经是 feature-layer 路由结构：`AppRoutes` 拉取 status、recent、radar、watchlist、signal-lab 查询并渲染 shell；现有 `/stocks`、`/watchlist`、`/news`、`/signal-lab`、index route 都在 cockpit shell 下，见 `web/src/routes/AppRoutes.tsx:37`、`web/src/routes/AppRoutes.tsx:40`、`web/src/routes/AppRoutes.tsx:177`、`web/src/routes/AppRoutes.tsx:221`、`web/src/routes/AppRoutes.tsx:225`、`web/src/routes/AppRoutes.tsx:250`、`web/src/routes/AppRoutes.tsx:252`、`web/src/routes/AppRoutes.tsx:263`。
- Frontend 已有 `/api/status` polling hook，12 秒 refetch，见 `web/src/features/cockpit/api/useCockpitStatusQuery.ts:6`、`web/src/features/cockpit/api/useCockpitStatusQuery.ts:9`、`web/src/features/cockpit/api/useCockpitStatusQuery.ts:11`。Side rail 目前只有 Radar、Stocks、News 和 watchlist 区，见 `web/src/features/cockpit/ui/CockpitSideRail.tsx:35`、`web/src/features/cockpit/ui/CockpitSideRail.tsx:44`、`web/src/features/cockpit/ui/CockpitSideRail.tsx:52`、`web/src/features/cockpit/ui/CockpitSideRail.tsx:58`。
- `/news/sources/status`、`/status/narrative-health`、`/enrichment-jobs`、`/notification-deliveries` 等局部诊断已经存在，但散落在领域路由里，见 `src/parallax/app/surfaces/api/routes_news.py:72`、`src/parallax/app/surfaces/api/routes_status.py:32`、`src/parallax/app/surfaces/api/routes_social_enrichment.py:75`、`src/parallax/app/surfaces/api/routes_notifications.py:110`。

## Problem

当实时数据、Token Radar、Pulse、Narrative、News、Watchlist 或通知缺失时，操作员需要在 CLI、`/api/status`、领域接口、日志和数据库之间来回切换，才能判断是 provider 未配置、worker 停止、queue 堵塞、projection lag、read model 空、还是下游通知失败。这个排障路径太散，容易把“没有业务结果”误判成算法问题，而不是运行时或数据面问题。

## First Principles

- 诊断面板属于控制面和可观测面，不产生业务事实。项目事实源仍然是 PostgreSQL material facts 和 derived read models；`/readyz` 也已经从 runtime 和 DB 读状态，而不是创建新事实，见 `src/parallax/app/runtime/app.py:139`、`src/parallax/app/runtime/app.py:178`。
- Queue 和 worker 诊断必须基于 allowlisted runtime/DB 信号，不接受任意表名或任意 SQL。现有 `JOB_QUEUE_DESCRIPTORS` 已经提供队列表 allowlist，见 `src/parallax/app/runtime/job_queue.py:61`。
- 面板永远不暴露 secret。当前 AGENTS 运行规则要求真实数据诊断只报告 redacted booleans、paths 和 diagnostic command results；本 spec 把这个要求固化到 HTTP contract 和 frontend model。

## Goals

- G1. 一个操作员打开 `/ops` 后，15 秒内能看到 DB、collector、providers、workers、queues、projections、Pulse、Narrative、News、notifications 的当前健康状态，无需打开 CLI。
- G2. `GET /api/ops/diagnostics` 在单个 section 查询失败时仍返回 200 和其余 section；失败 section 用 `status="unknown"`、`error_type`、`reason` 表达，页面不白屏。
- G3. 所有 ops HTTP 输出不包含字段名匹配 `api_key`、`secret`、`passphrase`、`token`、`password`、`dsn` 的原始值；只允许 redacted boolean、配置路径、provider 名称、capability、状态、时间戳、计数和截断错误类型。
- G4. 首版只读，不新增 worker、不新增事实表、不触发 backfill、不重跑 projection。
- G5. 前端首屏在 1440px 桌面和 390px 移动宽度都能扫描核心异常：顶部健康条、pipeline lane、worker matrix、provider matrix、queue drilldown 不重叠。

## Non-Goals

- 不把 DSA 的 in-memory task queue 或 SSE task stream 搬进首版。
- 不在首版做后台任务按钮、手动重跑、清理 dead job、重建 projection 等 mutation。
- 不新增 Prometheus metric；面板读现有 runtime/DB 状态。
- 不把 `/api/status` 变成巨型 payload；`/api/status` 继续服务轻量 readiness。
- 不把 ops 页面设计成通用管理后台；它只服务本项目实时情报链路排障。
- 不展示 provider request raw frame、LLM prompt、LLM response raw JSON、用户 secret 或完整 DSN。

## Target Architecture

新增一个只读 ops diagnostics surface：

- Backend route: `src/parallax/app/surfaces/api/routes_ops.py`
- Backend aggregator: `src/parallax/app/runtime/ops_diagnostics.py`
- Backend schemas: extend `src/parallax/app/surfaces/api/schemas.py` with loose but named ops payloads.
- API router: include `routes_ops.router` in `src/parallax/app/surfaces/api/http.py`.
- Static mount: add `/ops` and `/ops/{path:path}` to frontend fallback in `src/parallax/app/runtime/app.py`.
- Frontend feature: `web/src/features/ops/{api,model,ui}` with `OpsDiagnosticsPage`, query hook, normalizers, and CSS.
- Frontend route: `web/src/routes/ops.route.tsx`; add a cockpit shell route at `/ops`.
- Navigation: add `opsPath()` and a SideRail `Ops` item using lucide icon/text consistent with existing rail density.

The aggregator is an application-runtime read model, not a new domain. It composes current runtime status, provider health, canonical worker status, queue summaries, projection status, and existing domain health queries. It must never hold state between requests.

## Conceptual Data Flow

```text
runtime + db facts/read models
  -> ops_diagnostics aggregator
  -> /api/ops/diagnostics
  -> web/features/ops query model
  -> /ops diagnostic cockpit

runtime + allowlisted job queue tables
  -> queue drilldown query
  -> /api/ops/queues/{queue_name}
  -> queue detail drawer/table
```

Changed arrows:

- Existing `/api/status` remains as-is for readiness. `/api/ops/diagnostics` reuses the same categories but expands them for operator explanation.
- Existing domain routes remain as direct product surfaces. Ops diagnostics may call the same repositories/queries internally, but it owns the cross-domain composition and status classification.
- Frontend reuses cockpit shell and token/session plumbing, but ops gets its own route feature so Radar state and ops filters do not pollute each other.

## Core Models

### OpsDiagnosticsData

Semantic fields:

- `schema_version`: literal `ops.diagnostics.v1`.
- `generated_at_ms`: server clock used for age/staleness calculations.
- `overall`: `{status, severity, reasons, section_status_counts}`.
- `config`: redacted runtime config metadata: `app_home`, `config_path`, `workers_config_path`, `handles_count`, `upstream_channels`, and boolean readiness flags such as `gmgn_configured`, `okx_dex_configured`, `llm_configured`, `news_enabled`, `notifications_enabled`.
- `database`: DB health from existing readiness logic, including migration version status where available.
- `collector`: collector counters and snapshot gate outcome summary.
- `providers`: list of provider diagnostics. Each item has `provider`, `domain`, `configured`, `capabilities`, `state`, `last_state_change_at_ms`, `last_error_type`, `status`, `reason`.
- `workers`: list of worker diagnostics. Each item has `name`, `group`, `enabled`, `running`, `last_started_at_ms`, `last_finished_at_ms`, `last_result`, `last_error_type`, `iteration_duration_p99_ms`, `pool_wait_ms_p99`, `queue_depth`, `status`, `reason`.
- `queues`: list of queue summaries. Each item has `queue_name`, `table`, `worker_name`, `counts_by_status`, `due_count`, `running_count`, `dead_count`, `oldest_due_age_ms`, `oldest_running_age_ms`, `status`, `reason`.
- `domains`: grouped domain health for `token_radar`, `asset_market`, `pulse`, `narrative`, `news`, `watchlist`, `notifications`.
- `suggested_checks`: read-only guidance rows. Each item has `id`, `label`, `reason`, `cli_equivalent`, `safe_to_run`, `requires_confirmation`. In首版这些不是按钮。

### OpsQueueData

Semantic fields:

- `schema_version`: literal `ops.queue.v1`.
- `queue_name`: one of allowlisted queue descriptor names.
- `status_filter`: nullable queue status.
- `counts_by_status`: count summary from the same request.
- `items`: sanitized job rows with stable id, status, attempts, timestamps, last error type/detail preview, and source identifiers.

### OpsSectionStatus

Status vocabulary:

- `ok`: section is configured and current enough for its role.
- `idle`: section is healthy but has no work in the selected window.
- `disabled`: intentionally disabled or not configured.
- `degraded`: section has stale data, retryable failures, or high backlog.
- `blocked`: missing config, failed DB, dead jobs, or provider disconnected in a lane that should be live.
- `unknown`: section query failed or table is absent in an older migration.

## Interface Contracts

### `GET /api/ops/diagnostics`

Authentication: same bearer token/query token behavior as other authenticated API routes.

Query params:

- `since_hours`: integer `1..168`, default `4`. Used for recent failure windows.
- `window`: existing observation window, default `1h`.
- `scope`: existing scope, default `all`.

Response:

- `200 {"ok": true, "data": OpsDiagnosticsData}` when aggregate request succeeds, even if one or more sections are `unknown` or `degraded`.
- `401 {"ok": false, "error": "unauthorized"}` without valid token.
- `400 {"ok": false, "error": "invalid_window" | "invalid_scope" | "invalid_since_hours"}` for invalid inputs.
- `503` is not used for section degradation; `/readyz` remains the readiness endpoint.

Idempotency: safe, read-only, no database writes.

### `GET /api/ops/queues/{queue_name}`

Authentication: same as above.

Path params:

- `queue_name`: allowlisted queue descriptor name: `enrichment_jobs`, `watchlist_handle_summary_jobs`, `pulse_agent_jobs`, `notification_deliveries`.

Query params:

- `status`: optional allowlisted status. For notification delivery, `delivered` is also accepted.
- `limit`: integer, default `50`, max `200`.

Response:

- `200 {"ok": true, "data": OpsQueueData}`.
- `400 {"ok": false, "error": "invalid_queue"}` when queue is not in `JOB_QUEUE_DESCRIPTORS`.
- `400 {"ok": false, "error": "invalid_status"}` when status is not valid for that queue.
- `401` without valid token.

Idempotency: safe, read-only, no database writes.

### Frontend Route `/ops`

Route semantics:

- Mounted inside existing cockpit shell.
- Uses global auth token from `AppSession`.
- Polls `GET /api/ops/diagnostics` every 12 seconds by default, matching current status polling cadence.
- Queue drilldown fetches `GET /api/ops/queues/{queue_name}` only when a queue row is selected or a queue tab is open.
- Direct browser refresh on `/ops` must serve the SPA index, same as `/news`, `/stocks`, `/watchlist`.

## Frontend Experience

The page is an operator cockpit, not a marketing page. It should be dense, scannable, and action-oriented.

Primary regions:

- **Health Strip**: compact top row with DB, collector, providers, workers, queues, projections. Each tile shows status, age, and one terse reason.
- **Pipeline Lanes**: full-width table with lanes: Ingestion, Evidence, Asset Market, Token Radar, Narrative, Pulse, Watchlist, News, Notifications. Columns: lane, status, latest clock, backlog, failed/dead, reason, next check.
- **Provider Matrix**: provider rows grouped by domain. Shows configured, capabilities, connection state, last change, error type. No secrets or full URLs.
- **Worker Matrix**: canonical workers grouped by domain. Shows enabled/running, last finish age, p99 duration, pool wait, queue depth, last error type.
- **Queue Drilldown**: selected queue details with status segmented control, count chips, recent rows, attempt count, next run, last error preview.
- **Config Source Bar**: app home, config path, workers config path, and redacted booleans. This makes real-data debugging start with the correct operator-owned config path.

UI constraints:

- Use feature-scoped files under `web/src/features/ops`.
- Use existing `getApi`, `queryKeys`, `RemoteState`, formatting helpers, and shared CSS tokens.
- Use lucide icons only for compact status affordances where they improve scanning.
- Do not put cards inside cards. Use full-width bands/tables and small repeated row panels.
- Do not display prose explaining how to use the app inside the page. Labels and status reasons are enough.
- Keep all tables responsive: desktop uses multi-column tables; mobile collapses rows into compact lane blocks with fixed-height status chips and no overlapping text.

## Backend Classification Rules

Overall status:

- `blocked` if DB is unhealthy, scheduler reports unhealthy reasons, or collector is expected but not running.
- `degraded` if any required provider is disconnected, any queue has dead jobs, any enabled worker has recent error, or selected domain health is stale.
- `ok` if no blocked/degraded reasons exist.

Provider status:

- `disabled` when `configured=false`.
- `blocked` when configured provider has connection state `failed` or required live stream state is `disconnected`.
- `degraded` when configured provider has `last_error_type` but still has a usable fallback path.
- `ok` when configured and no current error is visible.

Worker status:

- `disabled` when worker status says `enabled=false`.
- `blocked` when enabled worker is not running and its lane is required for the selected page.
- `degraded` when enabled worker has `last_error_type`, nonzero dead queue count, or stale `last_finished_at_ms`.
- `ok` when enabled/running or recently finished without visible backlog.

Queue status:

- `blocked` when `dead_count > 0`.
- `degraded` when `failed_count > 0`, `running_count` has stale rows, or `oldest_due_age_ms` exceeds two worker intervals where interval is known.
- `idle` when all counts are zero or only terminal success statuses exist.
- `ok` when pending/running work exists but is fresh.

## Security And Redaction

- Redaction is applied in the aggregator before JSON serialization.
- Any key containing `api_key`, `secret`, `passphrase`, `token`, `password`, `dsn`, `authorization`, `cookie` is replaced with `"<redacted>"` if it ever appears in diagnostic dictionaries.
- Error strings are truncated to 500 characters and passed through redaction. Where possible, expose `last_error_type` separately from `last_error_preview`.
- Config diagnostics expose path and boolean readiness only. They do not expose API keys, WS token, DSN, provider credentials, OpenAI base URL with credentials, or notification URLs.
- Queue item payloads expose stable identifiers and status metadata. JSON payload/context fields are either omitted or reduced to whitelisted keys per queue.

## Acceptance Criteria

- AC1. WHEN an authenticated user calls `GET /api/ops/diagnostics?since_hours=4&window=1h&scope=all` THEN the system SHALL return `schema_version="ops.diagnostics.v1"` with non-empty `overall`, `database`, `collector`, `providers`, `workers`, `queues`, and `domains` keys.
- AC2. WHEN DB health succeeds but `NewsPageQuery.source_status()` raises an exception THEN the system SHALL return 200, mark `domains.news.status="unknown"`, include `error_type`, and still return worker/provider/queue sections.
- AC3. WHEN a request lacks a valid token THEN `/api/ops/diagnostics` and `/api/ops/queues/{queue_name}` SHALL return the same unauthorized envelope behavior as existing authenticated routes.
- AC4. WHEN `queue_name` is not in `JOB_QUEUE_DESCRIPTORS` THEN `/api/ops/queues/{queue_name}` SHALL return 400 with `error="invalid_queue"` and SHALL NOT interpolate the provided name into SQL.
- AC5. WHEN a queue has `dead_count > 0` THEN its queue summary SHALL have `status="blocked"` and the frontend queue row SHALL render a high-severity status chip.
- AC6. WHEN a provider health item has `configured=false` THEN the provider matrix SHALL render it as `disabled`, not `blocked`.
- AC7. WHEN any diagnostic output contains an input dictionary with keys such as `api_key`, `secret_key`, `ws_token`, or `dsn` THEN the serialized response SHALL not contain the raw value.
- AC8. WHEN the frontend loads `/ops` directly from the browser address bar THEN the backend SHALL serve the SPA index and React SHALL render the ops page inside the cockpit shell.
- AC9. WHEN diagnostics are loading, failed, empty, or stale THEN `OpsDiagnosticsPage` SHALL use existing remote-state patterns and SHALL NOT render an empty center column.
- AC10. WHEN the viewport is 390px wide THEN the Health Strip and Pipeline Lanes SHALL remain readable without text overlap or horizontal body scrolling.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Ops endpoint becomes a second `/api/status` with too much readiness responsibility. | Medium | Keep `/api/status` unchanged; `/api/ops/diagnostics` is operator-facing and may show degraded sections without changing HTTP readiness. |
| Generic queue drilldown accidentally allows SQL injection. | High | Use `JOB_QUEUE_DESCRIPTORS` as the only queue-name source and never interpolate user-provided table names. |
| Secret leakage through config, provider errors, queue payloads, or raw context JSON. | High | Central redaction helper, whitelisted queue fields, contract tests with seeded fake secrets. |
| Endpoint becomes slow because it runs many cross-domain queries. | Medium | Query small aggregate counts only; cap queue details; tolerate section timeout/failure as `unknown`; frontend polls at 12s. |
| Frontend becomes another dense dashboard that hides the actual cause. | Medium | Top health strip and lane table must show one primary reason per degraded/blocked section before detailed matrices. |
| The ops page creates pressure to add mutation buttons too early. | Medium | First version only shows `suggested_checks` as text/CLI equivalents; mutation endpoints require a separate spec. |

## Evolution Path

After the read-only panel is stable, the next expansion can borrow DSA’s task-progress idea as an ops event stream:

```text
DB-backed control jobs / worker status
  -> /api/ops/tasks
  -> /api/ops/tasks/stream or existing websocket ops channel
```

That expansion should still keep business truth in PostgreSQL, avoid in-memory singleton task state, and require a separate mutation/permission design before adding buttons such as rebuild, retry, or backfill.

## Alternatives Considered

- Extend `/api/status` with all diagnostics. Rejected because `/api/status` currently serves readiness-style status and is polled globally; adding queue rows, domain health, and config diagnostics would make it heavy and semantically noisy.
- Build a DSA-style in-memory task queue and SSE stream first. Rejected for首版 because the immediate problem is observability, not task execution, and in-memory task truth conflicts with this project’s DB-backed Kappa/CQRS discipline.
- Rely on Prometheus/Grafana only. Rejected because operators need product-domain explanations such as “Pulse has dead jobs” or “GMGN profile provider disabled” beside app concepts, not just metric names.
- Add a new ops database table. Rejected because all首版 data already exists in runtime status, provider wiring, job tables, projection metadata, and domain read models.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Read from runtime and PostgreSQL through allowlisted repositories/queries; return partial diagnostics when one section fails; redact secrets before response; keep `/api/status` lightweight. |
| Ask first | Add mutation actions, expose raw provider payloads, add SSE/task stream, introduce new tables, change worker health thresholds that can page or block readiness. |
| Never | Print or return secrets; use repo fixture config as real-data truth; accept arbitrary SQL/table names; make frontend-only health decisions that contradict backend classifications; mark missing business results as algorithm failure without showing provider/worker/queue context. |
