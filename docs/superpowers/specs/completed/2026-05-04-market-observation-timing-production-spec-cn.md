# Token Radar Market Observation 与 Social Timing 生产化设计规格

## 背景

Token Radar 的产品目标不是展示一组分数，而是让交易员快速判断：

1. 哪个 token 正在形成真实社交扩散。
2. 这轮讨论是否早于价格、同步确认价格，还是已经落后于价格。
3. 这个 token 是否有足够市场观测支持交易判断。

当前实现已经有正确的骨架：事件先入库、确定性抽实体、token attribution、GMGN token info、market snapshots、rolling token flow、timeline 和右侧 drawer。但 market observation 仍然是半成品：

- `IngestService.ingest_event()` 在写事务里同步调用 `TokenMarketEnricher.resolve_and_enrich_mentions()`。
- `TokenMarketEnricher` 只处理原始 mention 阶段已经有 `chain/address` 的记录。
- `$SYMBOL` 先作为 symbol-only mention 进入库，后续 attribution 可能选中具体 token，但此时 market enricher 已经错过该帖子时间点。
- `TokenFlowService._market_block()` 用固定 window start 到 window end 计算涨跌，不是用当前社交信号起点。
- `timing_score()` 把 `first_price_move_ms is None` 和 `price_change is None` 混在一起，导致“有价格但没明显动”被误报为 `missing_price_history`。
- `TokenSocialTimelineService._buckets()` 目前永远返回 `price: None`，所以 timeline price overlay 只是空字段。

这些不是单点 bug，而是边界设计问题：token attribution、market observation、timing explanation 三个概念现在耦合在同步 ingest 路径里。

## 第一性原理

### 1. 帖子流与价格流是两种事实

帖子提及 token 或 symbol 是社交事实；价格是外部市场观测事实。帖子本身不天然携带价格，但每条被系统判定为有效 token attribution 的帖子，都应该触发一次 event-time market observation。

正确合同是：

- 每条 `direct` CA attribution 都必须创建 market observation。
- 每条 `selected` symbol attribution 都必须创建 market observation。
- `ambiguous`、`weak_candidate`、`unresolved` symbol 不允许生成 token price snapshot，但必须留下明确状态。
- 外部 provider 成功时写入 event-time `token_market_snapshots`。
- 外部 provider 失败时记录 observation 状态，不允许 silent missing。

### 2. Ingest 不能被外部 HTTP 拖住

实时 collector 的生产边界是 store-first。外部 GMGN OpenAPI 是非本地依赖，不能在 ingest 写事务里同步等待。否则扩大到“每个有效 attribution 都采样价格”后，会产生：

- collector 吞吐下降；
- SQLite 写锁持有时间变长；
- API timeout 或 rate limit 直接影响事件入库；
- 重试语义不清晰；
- UI 无法区分 pending、失败、无 provider 和真正无历史。

因此 market observation 必须使用 outbox/worker 模式。

### 3. Timing 的锚点是当前社交信号起点

交易员想知道的是“从这轮讨论开始到现在，价格如何变化”，不是“固定窗口起点到现在，价格如何变化”。

Timing 应基于：

- `social_signal_start_ms`：当前 token flow window 内第一条有效 `direct` 或 `selected` attribution。
- `price_at_social_start`：社交起点附近或之前最近的 market snapshot。
- `price_at_reference`：当前 reference time 前最近的 market snapshot。
- `price_change_since_social_pct`：从社交起点到 reference 的涨跌。
- `price_change_before_social_pct`：社交起点前的涨跌，用于 chase risk。

## 目标

### In Scope

- 将 market observation 从同步 ingest 中拆出，改为异步 outbox/worker。
- 以最终 attribution 为准创建 market observation，覆盖 direct CA 和 selected symbol。
- 为 observation 增加明确状态，消除 silent missing。
- 将 market delta 和 timing 锚点改成当前社交信号起点。
- 让 token social timeline 使用真实 market snapshots 渲染 price overlay。
- 修正前端 selected token 与当前 radar result set 的一致性。
- 移除旧的 window-price 语义和任何 runtime 兼容分支。
- 添加生产级测试和运维可观测性。

### Out of Scope

- 不实现链上实时成交或订单簿。
- 不把 unresolved/ambiguous symbol 强行映射到 token。
- 不依赖 LLM 判断 token identity 或 market timing。
- 不恢复旧 `signal`、`evidence_highlight` 或手动 D/W/X 覆盖逻辑。
- 不把 GMGN `previous_price` 当作窗口涨跌来源。

## 核心设计

### 新边界

```text
collector websocket
  -> ingest event
  -> extract entities
  -> resolve raw mentions
  -> write event_token_mentions
  -> build event_token_attributions
  -> enqueue token_market_observations for direct/selected attributions
  -> commit

market observation worker
  -> claim pending observation
  -> query GMGN token info
  -> write token_market_snapshots on success
  -> update observation status

token-flow query
  -> read social attributions
  -> read market observations/snapshots
  -> compute market since social start
  -> compute timing
  -> rank opportunity
```

### 新表：`token_market_observations`

只新增一张 outbox 表，避免过度设计。它既是待处理任务，也是观测结果状态。

字段：

- `observation_id TEXT PRIMARY KEY`
- `attribution_id TEXT NOT NULL REFERENCES event_token_attributions(attribution_id) ON DELETE CASCADE`
- `event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE`
- `token_id TEXT NOT NULL REFERENCES tokens(token_id) ON DELETE CASCADE`
- `chain TEXT NOT NULL`
- `address TEXT NOT NULL`
- `symbol TEXT NOT NULL`
- `target_received_at_ms INTEGER NOT NULL`
- `status TEXT NOT NULL`
- `priority INTEGER NOT NULL DEFAULT 100`
- `provider TEXT`
- `source_channel TEXT NOT NULL DEFAULT 'gmgn_openapi_token_info'`
- `snapshot_id TEXT`
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `max_attempts INTEGER NOT NULL DEFAULT 5`
- `next_run_at_ms INTEGER NOT NULL`
- `last_error TEXT`
- `created_at_ms INTEGER NOT NULL`
- `updated_at_ms INTEGER NOT NULL`

唯一约束：

- `UNIQUE(attribution_id)`

索引：

- `(status, next_run_at_ms, priority)`
- `(token_id, target_received_at_ms)`
- `(event_id)`

状态：

- `pending`：已入队，worker 尚未处理。
- `running`：worker claim 后处理中。
- `ready`：provider 返回 fresh info，并写入 snapshot。
- `cached`：worker 使用 TTL 缓存结果，也写入 event-time snapshot。
- `provider_not_configured`：GMGN OpenAPI 未配置。
- `provider_not_found`：provider 没有返回 token info。
- `provider_error`：临时错误，会按 backoff 重试。
- `rate_limited`：provider rate limit，会按更长 backoff 重试。
- `dead`：超过最大尝试次数。

未解析或歧义 symbol 不创建 observation 行。它们的状态由
`event_token_attributions.attribution_status` 表达，避免在 observation 表里写入没有
`token_id/chain/address` 的伪任务。

Crash recovery：

- `running` 超过 `running_timeout_ms` 后允许重新 claim，默认 2 分钟。
- 重新 claim 前递增 `attempt_count`，避免 worker crash 后 observation 永久卡死。

### `token_market_snapshots` 的责任

`token_market_snapshots` 只表达成功的 market sample，不表达失败原因。

保留现有唯一约束 `UNIQUE(token_id, event_id)`。一条事件里多个 attribution 指向同一 token 时，多个 observation 可以共享同一 snapshot。observation 通过 `snapshot_id` 指向成功 sample。

### Attribution 后置 enqueue

market observation 必须基于最终 attribution，而不是原始 mention：

- `attribution_status = 'direct'` 且 `token_id/chain/address` 有效：enqueue。
- `attribution_status = 'selected'` 且 `token_id/chain/address` 有效：enqueue。
- 其他 attribution 不创建 observation。

这解决 `$PEPE` 的根因：symbol-only mention 后续被选中为具体 token 时，也会在 attribution 写入后创建 observation。

### 异步 worker

新增 `MarketObservationWorker`：

- 单 worker 默认即可，KISS。
- 每次 claim 一条 `pending/provider_error/rate_limited` 且 `next_run_at_ms <= now` 的 observation。
- `running` 超过 timeout 的 observation 可重新 claim。
- claim 和状态更新受现有 `write_lock` 保护。
- 外部 HTTP 不在 SQLite transaction 内执行。
- 成功后在短事务中写 `token_market_snapshots` 并更新 observation。
- 失败后更新 `attempt_count`、`last_error`、`next_run_at_ms`。
- GMGN 未配置时 worker 仍运行，但不做 HTTP；它会把 observation 标为 `provider_not_configured`，避免 pending 永久积压。

Backoff：

- 普通 provider error：`min(5m, 2^attempt * 5s)`。
- rate limit：`min(30m, 2^attempt * 30s)`。
- 超过 `max_attempts` 后 `dead`。

缓存：

- 保留 `GmgnOpenApiClient` 的 TTL 缓存，但 worker 需要知道结果是否来自 cache。
- 如果命中 cache，仍写一条 event-time snapshot，observation 标 `cached`。
- 这样每个 event attribution 都有自己的时间锚点，Timing 不会因为 provider TTL 而缺 sample。

### Market block 新语义

`TokenFlowService` 不再把主 delta 命名为 `price_change_window_pct`。新字段：

- `social_signal_start_ms`
- `reference_ms`
- `price_at_social_start`
- `price_at_reference`
- `price_change_since_social_pct`
- `price_before_social_start`
- `price_change_before_social_pct`
- `market_observation_status`
- `market_status`
- `snapshot_age_ms`

`price_change_status` 改为：

- `ready`：有 social-start 和 reference 两侧 price。
- `pending_observation`：observation 已入队但未完成。
- `insufficient_history`：已确认缺少足够 snapshot。
- `provider_not_configured`
- `provider_not_found`
- `provider_error`
- `rate_limited`
- `dead`

这里不保留旧字段作为 runtime compatibility。前端和测试一起破坏式更新。

### Timing V2

`timing_score()` 输入改为：

- `social_signal_start_ms`
- `price_change_since_social_pct`
- `price_change_before_social_pct`
- `market_observation_status`
- `social_heat_score`

状态：

- `social_leads_price`：社交开始后价格还未明显动，且 market observation ready。
- `social_confirms_price`：社交开始后价格明显上涨。
- `price_leads_social`：社交开始前价格已明显上涨，标 `chase_risk`。
- `social_fades`：社交开始后价格下跌或热度明显衰退。
- `market_pending`：observation 还在处理。
- `market_unavailable`：provider 未配置、失败、dead 或 not found。
- `insufficient_history`：已有观测但无法形成 social-start/reference 两端。

`missing_price_history` 不再作为“未明显涨价”的风险。它只用于真正缺少历史 sample 的内部原因，UI 不把它放成主状态。

### Token timeline price overlay

`TokenSocialTimelineService` 的 bucket price 应来自 `token_market_snapshots`：

- baseline：social timeline window 起点或第一条 bucket 前最近 snapshot。
- 每个 bucket：bucket end 前最近 snapshot。
- `price_change_from_start_pct`：bucket price 相对 baseline 的变化。
- 没有 baseline 或 bucket snapshot 时才为 null。

### Frontend 状态合同

前端不保留旧 API 字段：

- `TokenMarketBlock` 移除 `price_change_window_pct`，使用 `price_change_since_social_pct`。
- Market 列文案显示 `since social` 语义。
- Timing 列不再把“未明显涨价”显示为 `waiting / price history thin`。
- Drawer 的 selected token 必须来自当前 `tokenItems`。当前 result set 找不到旧选中时，自动选当前第一行；没有 row 时显示 empty。
- Timeline 有 price overlay 时不显示 `price snapshot missing`。

## 上下游影响评估

### Collector / Ingest

正向影响：

- 外部 GMGN API 不再阻塞 ingest。
- SQLite 写事务更短。
- public stream 高峰时更稳定。
- schema 新增 observation 表必须走 additive migration，不能因为 schema version mismatch 清空 events、attributions、snapshots。

风险：

- observation worker 落后时，UI 会短暂显示 `market_pending`。

控制：

- `/api/status` 暴露 pending/running/dead/rate_limited 计数。
- Token Radar 把 pending 作为 market/timing 状态，而不是当作缺数据。

### Token Attribution

正向影响：

- selected symbol 也会产生 event-time market observation。
- rebuild attribution 后可以补 observation。

风险：

- ambiguous symbol 被错误 selected 会带来错误 price sample。

控制：

- observation 只消费 `direct` 和 `selected`，继续依赖现有 attribution confidence/margin。
- ambiguous/rejected 不生成 token snapshot。

### Market Provider

正向影响：

- 调用量可控，可重试，可观测。

风险：

- 高提及 token 可能产生大量 observation。

控制：

- worker 单并发默认。
- provider TTL cache。
- 每条 attribution 一条 observation，但 token info 请求可由 cache 吸收。
- rate limit 状态可见。

### Token Flow / Ranking

正向影响：

- Market delta 与交易员语义对齐：从社交信号起点到现在。
- Timing 不再把“没涨够”误报成缺历史。

风险：

- 排名会变化，旧测试需要破坏式更新。

控制：

- 新 contract 测试锁定 V2 字段。
- 不保留旧字段，避免两套语义并存。

### Timeline / Drawer / Tape

正向影响：

- 右侧详情和当前表格行一致。
- Timeline 可以显示价格叠加。
- 实时信号内容不再被 market missing 文案压住。

风险：

- observation pending 时，短时间 price overlay 为空。

控制：

- 显示 `market pending`，不是 `price history thin`。

## 验收标准

- Ingest 过程中禁用 GMGN API 时，事件仍正常入库，observation 状态为 `provider_not_configured`。
- direct CA 事件写入后，有对应 `token_market_observations`。
- selected symbol attribution 写入后，有对应 `token_market_observations`。
- ambiguous symbol 不生成 observation，也不生成 token snapshot；歧义只保留在 attribution 状态里。
- worker 成功后，observation 指向 `token_market_snapshots.snapshot_id`。
- Token Flow 使用 `price_change_since_social_pct`，不返回旧 `price_change_window_pct`。
- 有 ready observation 且价格小幅变化时，timing 为 `social_leads_price`，不是 `insufficient_data`。
- 切换 window/scope 后，drawer 标题与 `.radar-row.selected` 对齐。
- Timeline 在有 snapshots 时返回非 null price bucket。
- 全量测试通过：`uv run pytest`、`uv run ruff check .`、`uv run python -m compileall src tests`、`cd web && npm test -- --run`、`cd web && npm run typecheck`、`cd web && npm run build`。
