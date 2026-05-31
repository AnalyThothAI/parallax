# Market Observation 与 Social Timing 生产化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Token Radar 的价格采样从同步 ingest 半成品升级为生产级 event-time market observation outbox，并把 market/timing 锚点改为当前社交信号起点。

**Architecture:** Ingest 只写本地事实和 observation outbox，不做外部 HTTP。MarketObservationWorker 异步消费 direct/selected attribution 的 observation，成功写 token_market_snapshots，失败写明确状态。TokenFlowService 基于 social_signal_start_ms 计算 since-social market delta 和 Timing V2。

**Tech Stack:** Python 3.13、SQLite WAL、FastAPI、asyncio worker、GMGN OpenAPI client、pytest、React/Vite/Zustand/TanStack Query。

---

## 设计约束

- 不保留旧 runtime 兼容字段：删除 `price_change_window_pct` 主语义，前后端同步改为 `price_change_since_social_pct`。
- 不恢复旧 `signal`、`evidence_highlight`、手动 D/W/X 控制。
- 不在 ingest 写事务里调用外部 HTTP。
- 不为 unresolved/ambiguous symbol 编造 token snapshot。
- KISS：只新增一张 observation outbox 表，不新增独立 job 表。
- 生产可观测：pending/running/error/dead/rate_limited 必须能从 API/CLI 查到。

## 文件责任图

- `src/parallax/storage/sqlite_schema.py`
  - 新增 `token_market_observations` 表和索引。
  - 升级 schema version。
  - 添加迁移测试需要的表存在断言。
- `src/parallax/storage/market_observation_repository.py`
  - 负责 enqueue、claim、complete、fail、counts、backfill 查询。
  - 只操作 observation 表和 snapshot join 所需字段。
- `src/parallax/market/gmgn_openapi_client.py`
  - 返回 token info 时携带 `cache_status`，让 worker 区分 ready/cached。
- `src/parallax/pipeline/ingest_service.py`
  - 删除同步 `token_market_enricher` 调用。
  - 仍然按 event -> mention -> attribution 顺序写本地事实。
- `src/parallax/pipeline/signal_builder.py`
  - 在 `replace_token_attributions()` 后 enqueue observation。
- `src/parallax/pipeline/market_observation_worker.py`
  - 新增异步 worker，claim observation，调用 provider，写 snapshot，更新状态。
- `src/parallax/storage/token_repository.py`
  - 复用 `upsert_openapi_token_info()` 写 snapshot。
  - 如需要，增加按 snapshot_id 查询方法。
- `src/parallax/api/app.py`
  - 构建 MarketObservationRepository/Worker。
  - 启停 worker。
  - `/api/status` 输出 market observation backlog。
- `src/parallax/api/http.py`
  - 如需要，新增 `/api/market-observations` 只读检查端点。
- `src/parallax/cli.py`
  - 新增 `ops backfill-market-observations`。
  - 新增 `market-observations` 只读命令。
- `src/parallax/retrieval/token_flow_service.py`
  - social-start 锚点 market block。
  - 输出 V2 market fields。
- `src/parallax/retrieval/timing_scoring.py`
  - Timing V2 状态机。
- `src/parallax/retrieval/token_social_timeline_service.py`
  - bucket price overlay。
- `web/src/api/types.ts`
  - 更新 TokenMarketBlock/TimingBlock。
- `web/src/components/TokenRadarRow.tsx`
  - Market/Timing 文案切换到 since-social。
- `web/src/components/TokenTimeline.tsx`
  - 真实 price overlay 和 pending/missing 文案。
- `web/src/App.tsx`
  - selected token 必须来自当前 tokenItems。
- `web/src/lib/format.ts`
  - 新状态中文/英文短标签。

## Task 1: 写 Observation Schema 与 Repository 失败测试

**Files:**
- Modify: `tests/test_sqlite_schema.py`
- Create: `tests/test_market_observation_repository.py`

- [ ] 在 `tests/test_sqlite_schema.py` 增加断言：`token_market_observations` 表存在。
- [ ] 增加迁移测试：从 version 8 数据库升级到 version 9 时，已有 `events`、`event_token_attributions`、`token_market_snapshots` 不被清空。
- [ ] 新建 repository 测试，覆盖 enqueue direct attribution。
- [ ] 新建 repository 测试，覆盖同一个 attribution 重复 enqueue 幂等。
- [ ] 新建 repository 测试，覆盖 claim next pending observation。
- [ ] 新建 repository 测试，覆盖 stale `running` observation 超过 timeout 后可重新 claim。
- [ ] 新建 repository 测试，覆盖 complete 后写入 `snapshot_id/status/updated_at_ms`。
- [ ] 新建 repository 测试，覆盖 provider error backoff 和 dead 状态。
- [ ] 运行失败测试：

```bash
uv run pytest tests/test_sqlite_schema.py tests/test_market_observation_repository.py -q
```

Expected: 失败，提示表或 repository 不存在。

## Task 2: 实现 Observation Schema 与 Repository

**Files:**
- Modify: `src/parallax/storage/sqlite_schema.py`
- Create: `src/parallax/storage/market_observation_repository.py`
- Modify: `tests/test_sqlite_schema.py`
- Modify: `tests/test_market_observation_repository.py`

- [ ] 在 `APP_TABLES` 加入 `token_market_observations`。
- [ ] 将 `SCHEMA_VERSION` 升级到 `9`。
- [ ] 修改 `_should_reset_schema()`：version 8 到 9 是 additive migration，不触发 `_reset_app_schema()`。
- [ ] 新增 `_apply_incremental_migrations(conn, current_version)`，version 8 时只执行新表/索引 DDL，再写入 version 9。
- [ ] 保留“缺少必需中文字段的旧 schema reset”逻辑，但不要把 additive table upgrade 当作 incompatible schema。
- [ ] 在 schema SQL 添加表：

```sql
CREATE TABLE IF NOT EXISTS token_market_observations (
  observation_id TEXT PRIMARY KEY,
  attribution_id TEXT NOT NULL REFERENCES event_token_attributions(attribution_id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  token_id TEXT NOT NULL REFERENCES tokens(token_id) ON DELETE CASCADE,
  chain TEXT NOT NULL,
  address TEXT NOT NULL,
  symbol TEXT NOT NULL,
  target_received_at_ms INTEGER NOT NULL,
  status TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100,
  provider TEXT,
  source_channel TEXT NOT NULL DEFAULT 'gmgn_openapi_token_info',
  snapshot_id TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_run_at_ms INTEGER NOT NULL,
  last_error TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE(attribution_id)
);

CREATE INDEX IF NOT EXISTS idx_token_market_observations_status_next
  ON token_market_observations(status, next_run_at_ms, priority);
CREATE INDEX IF NOT EXISTS idx_token_market_observations_token_target
  ON token_market_observations(token_id, target_received_at_ms);
CREATE INDEX IF NOT EXISTS idx_token_market_observations_event
  ON token_market_observations(event_id);
```

- [ ] 在 repository 中实现：
  - `enqueue_for_attributions(attributions, now_ms=None) -> int`
  - `claim_next(now_ms=None) -> dict | None`
  - `complete(observation, snapshot_id, status, provider, now_ms=None)`
  - `fail(observation, error, status='provider_error', now_ms=None)`
  - `counts() -> dict[str, int]`
  - `pending_backfill_rows(limit: int) -> list[dict]`
- [ ] `enqueue_for_attributions()` 只接受：
  - `attribution_status in {'direct', 'selected'}`
  - `token_id`, `chain`, `address` 均非空
  - `chain not in {'unknown', 'evm', 'evm_unknown'}`
- [ ] `claim_next()` 用短事务把 `pending/provider_error/rate_limited` 改为 `running`。
- [ ] `claim_next()` 也允许 claim `running` 且 `updated_at_ms < now_ms - running_timeout_ms` 的 observation。
- [ ] `fail()` 计算 backoff：
  - provider error: `min(300000, (2 ** attempt_count) * 5000)`
  - rate limit: `min(1800000, (2 ** attempt_count) * 30000)`
  - `attempt_count >= max_attempts` 时 `dead`
- [ ] 运行：

```bash
uv run pytest tests/test_sqlite_schema.py tests/test_market_observation_repository.py -q
```

Expected: 通过。

## Task 3: 移除同步 Market Enricher，并在 Attribution 后 Enqueue

**Files:**
- Modify: `src/parallax/pipeline/ingest_service.py`
- Modify: `src/parallax/pipeline/signal_builder.py`
- Modify: `src/parallax/api/app.py`
- Modify: `tests/test_collector_service.py`
- Create: `tests/test_market_observation_enqueue_flow.py`

- [ ] 写测试：fake GMGN client 变慢或抛错时，`ingest_event()` 仍写入事件、mentions、attributions，并产生 pending observation。
- [ ] 写测试：direct CA mention 生成 pending observation。
- [ ] 写测试：纯 `$SYMBOL` 先 unresolved 不生成 observation；已有 alias 后 selected symbol 生成 observation。
- [ ] 写测试：ambiguous symbol 不生成 observation。
- [ ] 修改 `IngestService.__init__()`：移除 `token_market_enricher` 参数。
- [ ] 修改 `ingest_event()`：删除 `self.token_market_enricher.resolve_and_enrich_mentions(...)` 调用。
- [ ] 修改 `SignalBuilder.__init__()`：接收 `market_observations: MarketObservationRepository | None`。
- [ ] 修改 `SignalBuilder.build_for_event()`：在 `token_attributions = ...` 后调用 `market_observations.enqueue_for_attributions(token_attributions, commit=False)`。
- [ ] 修改 `_build_runtime()`：构建 `MarketObservationRepository(conn)` 并传给 `IngestService` 或 `SignalBuilder`。
- [ ] Task 3 只删除 runtime 同步调用，不在同一步做文件删除；Task 10 必须删除或重命名旧同步 enricher，最终状态不允许任何 ingest runtime 引用。
- [ ] 运行：

```bash
uv run pytest tests/test_market_observation_enqueue_flow.py tests/test_collector_service.py -q
```

Expected: 通过，且测试断言 ingest 不调用外部 HTTP。

## Task 4: 实现 MarketObservationWorker

**Files:**
- Create: `src/parallax/pipeline/market_observation_worker.py`
- Modify: `src/parallax/market/gmgn_openapi_client.py`
- Modify: `tests/test_gmgn_openapi_client.py`
- Create: `tests/test_market_observation_worker.py`

- [ ] 为 GMGN client 添加 lookup result：

```python
@dataclass(frozen=True, slots=True)
class GmgnTokenInfoLookup:
    info: GmgnTokenInfo | None
    cache_status: str  # "miss" | "hit"
```

- [ ] 新增 `lookup_token_info(chain, address) -> GmgnTokenInfoLookup`。
- [ ] 替换所有 runtime 调用点使用 `lookup_token_info()`；旧 `get_token_info()` 不作为生产路径保留。
- [ ] `lookup_token_info()` 命中 TTL 时返回 `cache_status='hit'`。
- [ ] Worker 测试：
  - pending observation 成功后调用 client，写 snapshot，status 为 `ready`。
  - 第二条同 token observation 命中 cache 后仍写 event-time snapshot，status 为 `cached`。
  - client 为 `None` 时标 `provider_not_configured`，不留下 pending。
  - provider not found 标 `provider_not_found`。
  - provider error 标 `provider_error` 并 backoff。
  - rate limit error 标 `rate_limited` 并 backoff。
- [ ] Worker 实现：
  - `run()` loop 与 `EnrichmentWorker` 模式一致。
  - `process_one()` claim 后释放 lock，执行外部 HTTP，再短事务写结果。
  - 成功时调用 `TokenRepository.upsert_openapi_token_info(event_id=observation["event_id"], received_at_ms=observation["target_received_at_ms"])`。
  - observation `snapshot_id` 使用现有 `_snapshot_id(token_id, event_id)` 规则或 repository 返回的 latest snapshot。
- [ ] 运行：

```bash
uv run pytest tests/test_gmgn_openapi_client.py tests/test_market_observation_worker.py -q
```

Expected: 通过。

## Task 5: 接入 Runtime、Status 和 CLI Ops

**Files:**
- Modify: `src/parallax/api/app.py`
- Modify: `src/parallax/api/http.py`
- Modify: `src/parallax/cli.py`
- Modify: `tests/test_api_http.py`
- Modify: `tests/test_cli.py`

- [ ] 在 `CliRuntime` 增加：
  - `market_observations`
  - `market_observation_worker`
  - `market_observation_task`
- [ ] `_build_runtime()` 总是构建并启动 worker；`gmgn_client is None` 时 worker 不做 HTTP，只把 observation 标为 `provider_not_configured`。
- [ ] `_stop_runtime()` 停止并 await worker task。
- [ ] `/api/status` 增加：

```json
"market_observations": {
  "pending": 0,
  "running": 0,
  "ready": 0,
  "cached": 0,
  "provider_error": 0,
  "rate_limited": 0,
  "dead": 0,
  "worker_running": true
}
```

- [ ] 新增 CLI：
  - `parallax market-observations --status pending --limit 50`
  - `parallax ops backfill-market-observations --limit 1000`
- [ ] `backfill-market-observations` 从已有 `event_token_attributions` direct/selected rows 中 enqueue 缺失 observation。
- [ ] 测试 CLI 输出 JSON 包含 counts 和 rows。
- [ ] 运行：

```bash
uv run pytest tests/test_api_http.py tests/test_cli.py -q
```

Expected: 通过。

## Task 6: 重写 Market Block 为 Since-Social 语义

**Files:**
- Modify: `src/parallax/retrieval/token_flow_service.py`
- Modify: `src/parallax/retrieval/rolling_token_flow.py`
- Modify: `tests/test_token_flow_social_heat_contract.py`
- Modify: `tests/test_token_conviction_flow.py`
- Modify: `tests/test_token_rolling_flow.py`

- [ ] 写失败测试：当前 window 内第一条 direct/selected attribution 是 `social_signal_start_ms`。
- [ ] 写失败测试：market delta 从 social start snapshot 到 reference snapshot。
- [ ] 写失败测试：window start 更早但 social start 较晚时，不使用 window start price。
- [ ] 写失败测试：pending observation 时 `price_change_status == 'pending_observation'`。
- [ ] 写失败测试：provider_not_configured/provider_error/rate_limited/dead 能透传为 market observation status。
- [ ] 修改 `RollingTokenFlow._group_mentions()`：保留当前 window 内 first_seen/latest_seen，避免被全局 bounds 覆盖为 social timing 锚点。
- [ ] 修改 `TokenFlowService._market_block()`：
  - 输入 row 的 `first_seen_ms` 作为 social start。
  - 查询 `market_snapshot_at_or_before(token_id, social_signal_start_ms)`。
  - 查询 `market_snapshot_at_or_before(token_id, reference_ms)`。
  - 查询 social start 前 lookback snapshot，用于 `price_change_before_social_pct`。
  - 查询 observation statuses 覆盖 pending/error。
- [ ] 输出新字段：

```python
{
    "market_status": "fresh",
    "price": reference_price,
    "market_cap": reference_snapshot.get("market_cap"),
    "snapshot_age_ms": age_ms,
    "snapshot_received_at_ms": reference_snapshot.get("received_at_ms"),
    "social_signal_start_ms": social_start_ms,
    "reference_ms": reference_ms,
    "price_at_social_start": start_price,
    "price_at_reference": reference_price,
    "price_change_since_social_pct": change,
    "price_before_social_start": before_price,
    "price_change_before_social_pct": before_change,
    "market_observation_status": observation_status,
    "price_change_status": price_change_status,
}
```

- [ ] 删除 runtime 返回里的旧 `price_change_window_pct`。
- [ ] 运行：

```bash
uv run pytest tests/test_token_flow_social_heat_contract.py tests/test_token_conviction_flow.py tests/test_token_rolling_flow.py -q
```

Expected: 通过。

## Task 7: Timing V2

**Files:**
- Modify: `src/parallax/retrieval/timing_scoring.py`
- Modify: `tests/test_timing_scoring.py`
- Modify: `tests/test_token_flow_social_heat_contract.py`

- [ ] 写失败测试：`price_change_since_social_pct=0.02` 且 market ready 时返回 `social_leads_price`，不含 `missing_price_history`。
- [ ] 写失败测试：`price_change_since_social_pct=0.18` 返回 `social_confirms_price`。
- [ ] 写失败测试：`price_change_before_social_pct=0.35` 返回 `price_leads_social` 和 `chase_risk`。
- [ ] 写失败测试：`market_observation_status='pending'` 返回 `market_pending`。
- [ ] 写失败测试：provider error/dead 返回 `market_unavailable`。
- [ ] 修改 `timing_score()` 输入字段：
  - `social_signal_start_ms`
  - `price_change_since_social_pct`
  - `price_change_before_social_pct`
  - `market_observation_status`
  - `social_heat_score`
- [ ] 删除对 `first_price_move_ms is None` 的缺历史误判。
- [ ] 运行：

```bash
uv run pytest tests/test_timing_scoring.py tests/test_token_flow_social_heat_contract.py -q
```

Expected: 通过。

## Task 8: Token Social Timeline Price Overlay

**Files:**
- Modify: `src/parallax/retrieval/token_social_timeline_service.py`
- Modify: `tests/test_token_social_timeline_service.py`
- Modify: `tests/test_api_http.py`

- [ ] 写失败测试：有 token snapshots 时，timeline buckets 返回非 null `price`。
- [ ] 写失败测试：`price_change_from_start_pct` 相对 timeline baseline 计算。
- [ ] 写失败测试：没有 baseline 时，price fields 为 null，但 social buckets 仍正常返回。
- [ ] 修改 `TokenSocialTimelineService` 初始化，接收 `tokens` 或直接用同一 sqlite conn 查询 `token_market_snapshots`。
- [ ] `_buckets()` 增加 token_id 参数，按 bucket end 查询 snapshot。
- [ ] baseline 用 window start 前最近 snapshot；没有时用第一条 bucket snapshot 作为 baseline。
- [ ] API router 创建 service 时传入 `runtime.read_tokens`。
- [ ] 运行：

```bash
uv run pytest tests/test_token_social_timeline_service.py tests/test_api_http.py -q
```

Expected: 通过。

## Task 9: Frontend Breaking API Update

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/lib/format.ts`
- Modify: `web/src/components/TokenRadarRow.tsx`
- Modify: `web/src/components/TokenDetailDrawer.tsx`
- Modify: `web/src/components/TokenTimeline.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/lib/format.test.ts`

- [ ] 更新 `TokenMarketBlock`：
  - 删除 `price_change_window_pct`
  - 增加 `price_change_since_social_pct`
  - 增加 `social_signal_start_ms`
  - 增加 `market_observation_status`
- [ ] 更新 `TimingBlock` 状态 union：
  - `social_leads_price`
  - `social_confirms_price`
  - `price_leads_social`
  - `social_fades`
  - `market_pending`
  - `market_unavailable`
  - `insufficient_history`
- [ ] `TokenRadarRow` Market 列显示 `price_change_since_social_pct`。
- [ ] `timingMeta()`：
  - `market_pending` -> `market observation pending`
  - `market_unavailable` -> provider/status label
  - `social_leads_price` -> `price quiet after social`
  - 不再显示 `price history thin` 作为默认主文案。
- [ ] `latestTokenForSelection()` 改为找不到当前 token 时返回 null。
- [ ] 增加 effect：当 selected token 不在当前 tokenItems 且 tokenItems 非空，选当前第一行；tokenItems 空则清空 selected token。
- [ ] `TokenTimeline` 只有所有 bucket price 均 null 时显示 `price snapshot missing`。
- [ ] 测试：
  - window 切换后 drawer 和 selected row 一致。
  - ready market + quiet price 显示 social leads。
  - pending observation 显示 pending，不显示 price history thin。
- [ ] 运行：

```bash
cd web && npm test -- --run
cd web && npm run typecheck
cd web && npm run build
```

Expected: 全部通过。

## Task 10: 删除旧同步 Market Enricher 路径和兼容引用

**Files:**
- Delete or deprecate by removal from runtime imports: `src/parallax/pipeline/token_market_enricher.py`
- Modify: `src/parallax/api/app.py`
- Modify: `tests/test_token_market_enricher.py`
- Modify: docs if needed

- [ ] 确认 `TokenMarketEnricher` 不再被 runtime 使用。
- [ ] 如果没有独立价值，删除 `token_market_enricher.py` 和对应测试。
- [ ] 如果保留 provider helper，会改名为 worker 内部服务，不允许被 ingest 调用。
- [ ] 搜索确认无同步路径：

```bash
rg "token_market_enricher|TokenMarketEnricher|resolve_and_enrich_mentions" src tests
```

Expected: 没有 runtime 引用。

- [ ] 搜索确认无旧字段：

```bash
rg "price_change_window_pct|missing_price_history|evidence_highlight|signal\\.decision|signal\\.score|post_score_v1" src tests web/src
```

Expected: 除迁移说明或测试 fixture 旧数据外无 runtime 引用；如有测试 fixture，必须改成 V2 字段。

## Task 11: 端到端运行和数据验证

**Files:**
- No source edits unless previous tasks reveal failures.

- [ ] 后端全量：

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Expected: all passed。

- [ ] 前端全量：

```bash
cd web && npm test -- --run
cd web && npm run typecheck
cd web && npm run build
```

Expected: all passed。

- [ ] 本地服务验证：

```bash
docker compose up --build
```

或本地：

```bash
uv run parallax serve
```

- [ ] API 验证：

```bash
TOKEN=$(curl -sS http://127.0.0.1:8765/api/bootstrap | jq -r '.data.ws_token')
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/api/status | jq '.data.market_observations'
curl -sS -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:8765/api/token-flow?window=1h&limit=20&scope=all' | jq '.data.items[0].market, .data.items[0].timing'
```

Expected:

- status 有 market observation counts。
- token-flow item 使用 `price_change_since_social_pct`。
- timing 不再因为 price quiet 输出 `missing_price_history`。

- [ ] 浏览器验证：
  - 打开 `http://127.0.0.1:5174/`。
  - 切换 `1h -> 5m -> 24h`。
  - 检查 `.radar-row.selected` 与 drawer title 一致。
  - 检查 ready market token 的 Market 列显示 since-social delta。
  - 检查 timeline 有 snapshots 时不显示 `price snapshot missing`。

## 风险清单与防回归

- Schema 当前测试允许版本变化时 reset app schema。生产化时不应把新增 observation 表作为重置理由。实现者必须评估并更新 `test_migrate_resets_incompatible_app_schema_instead_of_keeping_old_columns`：本次新增表是 additive migration，不应清空 events/attributions/snapshots。
- Worker 与 enrichment worker 共用 write lock，外部 HTTP 必须在 lock 外执行。
- Observation enqueue 必须幂等，否则 attribution rebuild 会重复创建任务。
- Cache 命中仍需写 event-time snapshot，否则 timing 仍会缺社交起点 sample。
- UI 不得用 `market_pending` 代替失败状态；pending、provider error、rate limited、dead 必须区分显示。
- Ambiguous symbol 不能生成 price snapshot，否则会污染 token flow。

## Self-Review

- Spec 覆盖：outbox、selected symbol、异步 worker、since-social market delta、Timing V2、timeline price overlay、frontend selection、observability 均有对应任务。
- Placeholder scan：本文没有占位式实现描述。
- Type consistency：计划统一使用 `token_market_observations`、`price_change_since_social_pct`、`social_signal_start_ms`、`market_observation_status`。
- Scope check：本计划只处理 market observation 与 timing，不引入链上成交、订单簿或 LLM token identity。
