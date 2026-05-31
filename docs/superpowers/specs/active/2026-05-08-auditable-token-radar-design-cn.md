# Auditable Token Trading Radar Design Spec

日期：2026-05-08

## 结论

Token Radar 下一阶段要硬切成“可审计的交易雷达”，不是继续修补现在的高分榜。榜单每一行必须能回答五个问题：

1. 这条信号指向哪个确定的交易对象。
2. 哪些推文、哪些作者、在哪些时间点构成了信号。
3. 每条推文解析到该 token 时，对应的 token 价格是什么，观测延迟是多少，数据源是什么。
4. 这个排名分数为什么这么高，哪些特征贡献了分数，哪些风险限制了分数。
5. 从第一次入库 snapshot、social start、当前最新价格看，价格分别涨跌多少。

本阶段不保留旧 scoring 兼容分支，不继续输出空 `reasons/contributions/risk_caps` 的分数 payload，不把 CEX 和 DEX 合并成一个伪 token，也不让前端对缺失字段做“看起来正常”的 fallback。

生产投影切到新版本：

- `PROJECTION_VERSION = "token-radar-v5-auditable"`
- `/api/token-radar` 继续作为读接口，但只读取 v5 投影。
- `target_type` 保持 `CexToken` 和 `Asset` 两条身份线。
- identity resolver 使用 `token_radar_v5_identity_resolver`，resolver policy 与 v5 投影一起作为当前生产 contract 审计字段。
- score 使用现有成熟函数接入生产投影：`social_heat_score`、`discussion_quality_score`、`propagation_score`、`tradeability_score`、`timing_score`、`opportunity_score`。
- `price_health` 在生产 contract 中改名为 `tradeability`，不保留旧字段。

## 第一性原理

### 交易雷达不是热度榜

热度只说明“有人在说”。交易雷达必须同时满足：

- 身份确定：能分清 CEX token、DEX asset、未解析 symbol。
- 价格可复盘：信号出现时的价格、现在的价格、第一次观测价格都能查回。
- 评分可解释：每个组件都有版本、贡献项、风险项、cap 和数据健康状态。
- 决策可控：缺 identity、缺 market、价格已经先涨、传播集中、低质量文本都必须限制 driver。

### 不用一个“总分”掩盖缺口

`opportunity` 是聚合结论，不是事实源。任何 `driver/watch/discard/investigate` 都必须能拆回：

- heat：社交异常程度。
- quality：讨论质量和 token attribution 质量。
- propagation：传播是否扩散到独立作者。
- tradeability：身份和市场数据是否足够交易。
- timing：从 social start 到当前价格是否已经追高。

### CEX 和 DEX 不合并

CEX 和 DEX 可以共用 radar row contract，但不能共享同一个身份模型。

- `CexToken`：symbol 级中心化交易对象，必须有 CEX pricefeed，不能要求 chain/address/pool。
- `Asset`：链上资产，必须有 chain/address，DEX pricefeed 和链上市场字段优先。
- `Project` 可以继续作为未来聚合层存在，但本阶段不把多个 CEX/DEX 目标合并成 project row。

### KISS

本阶段只做一个生产闭环：

`events + token_intents + token_intent_resolutions + price_observations`
→ `TokenRadarProjection`
→ `/api/token-radar` 和 `/api/target-social-timeline`
→ 前端榜单与 token 二级页。

不引入新的缓存系统，不做 shadow 双版本切换，不在 API 请求路径里临时补算旧分数。

## 当前问题

### 生产 scoring 仍是启发式

`src/parallax/pipeline/token_radar_projection.py` 当前 `_score()` 使用：

```python
heat = min(100, 30 + mentions * 6 + authors * 8 + watched * 8)
quality = min(100, 70 + watched * 8) if resolved else min(70, 35 + mentions * 8)
propagation = min(100, 30 + authors * 14)
price_health = 80 if resolved and market_usable else 45 if resolved else 20
timing = 50 if resolved else 35
```

这个公式的问题：

- resolved token 默认 quality 70，不看文本质量、重复文本、attribution confidence。
- heat 随 mentions/authors 线性上升，长窗口容易 100 饱和。
- score block 的 `reasons`、`contributions`、`risk_caps` 为空，不可审计。
- stale market 仍被当作 usable，driver 判断过宽。
- timing 没有使用 social start 价格变化字段。

### 成熟 scoring 函数没有进入生产投影

这些函数已经具备审计结构，但目前只在测试或实验路径里使用：

- `retrieval/social_heat_scoring.py`
- `retrieval/discussion_quality_scoring.py`
- `retrieval/propagation_scoring.py`
- `retrieval/tradeability_scoring.py`
- `retrieval/timing_scoring.py`
- `retrieval/opportunity_scoring.py`

生产投影必须直接调用这些函数，而不是重新实现一套简化分数。

### 价格链路只完成了一半

现在 `price_observations` 能存目标级价格，但缺少消息级归因：

- 没有 `event_id`。
- 没有 `intent_id`。
- 没有 `resolution_id`。
- 没有观测延迟字段。
- timeline bucket 的 `price` 仍为 `None`。
- radar market 里的 `price_at_social_start` 和 `price_change_since_social_pct` 仍为 `None`。

GMGN payload 事件只作为 identity evidence；payload 自带 price / market cap 不写入 `price_observations`。解析后的 CEX/DEX token 的“这条消息对应价格”只由 message quote worker 产生。

## 目标 Contract

### Radar Row

每行代表一个确定窗口内的目标信号：

```json
{
  "target": {
    "target_type": "CexToken | Asset",
    "target_id": "stable id",
    "symbol": "BTC",
    "pricefeed_id": "stable feed id"
  },
  "attention": {
    "mentions_window": 7,
    "mentions_5m": 2,
    "mentions_1h": 7,
    "mentions_4h": 19,
    "mentions_24h": 42,
    "unique_authors": 5,
    "watched_mentions": 1,
    "social_signal_start_ms": 1777800000000,
    "latest_seen_ms": 1777800600000
  },
  "market": {
    "market_status": "fresh | stale | missing",
    "market_observation_status": "ready | pending_observation | missing_observation | provider_error",
    "price_usd": 1.23,
    "price_at_social_start": 1.11,
    "price_at_reference": 1.23,
    "price_change_since_social_pct": 0.1081,
    "first_snapshot_observed_at_ms": 1777700000000,
    "price_at_first_snapshot": 0.82,
    "price_change_since_first_snapshot_pct": 0.5,
    "snapshot_observed_at_ms": 1777800600000,
    "snapshot_age_ms": 30000
  },
  "score": {
    "heat": {},
    "quality": {},
    "propagation": {},
    "tradeability": {},
    "timing": {},
    "opportunity": {}
  },
  "decision": "driver | watch | discard | investigate"
}
```

### Score Block

每个 score block 必须遵守同一审计格式：

```json
{
  "score": 68,
  "score_version": "social_heat_v2",
  "reasons": ["positive_mention_delta"],
  "risks": ["public_stream_coverage"],
  "contributions": [
    {"feature": "heat.mentions", "value": 12.1, "reason": "current_mentions"}
  ],
  "risk_caps": [
    {"risk": "thin_public_only", "cap": 55}
  ],
  "data_health": {
    "baseline_ready": true
  }
}
```

如果分数没有 `contributions`，这个分数不能进入生产榜单。

### Message Price

每条 timeline post 必须有独立 price block：

```json
{
  "event_id": "event-1",
  "received_at_ms": 1777800000000,
  "price": {
    "status": "ready | stale | pending_observation | missing_observation",
    "provider": "okx_cex | okx_dex_price",
    "pricefeed_id": "feed-id",
    "price_usd": 1.11,
    "price_quote": null,
    "quote_symbol": "USDT",
    "observed_at_ms": 1777800001000,
    "observation_lag_ms": 1000,
    "observation_id": "obs-id"
  }
}
```

价格不能伪造：

- CEX/DEX 当前报价：`observed_at_ms = provider quote time or fetch time`，并记录 `observation_lag_ms`。
- GMGN payload 自带价格不写入；没有主动报价前，post price 必须是 `pending_observation` 或 `missing_observation`。
- 如果 provider 返回太晚，post price 是 `stale`，不能显示为 ready。
- 如果没有观测，post price 是 `pending_observation` 或 `missing_observation`。

## 数据模型

### `price_observations` 增量字段

新增字段：

- `source_event_id TEXT REFERENCES events(event_id) ON DELETE SET NULL`
- `source_intent_id TEXT REFERENCES token_intents(intent_id) ON DELETE SET NULL`
- `source_resolution_id TEXT REFERENCES token_intent_resolutions(resolution_id) ON DELETE SET NULL`
- `observation_kind TEXT NOT NULL DEFAULT 'refresh'`
- `event_received_at_ms BIGINT`
- `observation_lag_ms BIGINT`

索引：

- `idx_price_observations_source_event`
- `idx_price_observations_source_intent`
- `idx_price_observations_subject_time_kind`

`observation_kind` 取值：

- `message_quote`：消息解析后主动拉取的价格。
- `refresh`：周期刷新价格。
- `discovery`：token discovery/search 带回价格。

### 不新增单独消息价格表

KISS：消息价格就是 `price_observations` 的一种来源。增加 event/intention/resolution 归因字段即可支持：

- per-message price ledger。
- target latest price。
- social start baseline。
- first snapshot delta。
- timeline bucket overlay。

## Feature Builder

新增 `src/parallax/pipeline/token_radar_feature_builder.py`，只负责把 source rows 转成 scoring features。投影负责读数据和写 row，scoring 函数负责计算分数。

### Heat Features

输入给 `social_heat_score`：

- `mentions`
- `mentions_5m`
- `mentions_1h`
- `mentions_4h`
- `mentions_24h`
- `weighted_mentions`
- `previous_mentions`
- `mention_delta`
- `stream_share`
- `watched_share`
- `is_new_local_evidence`
- `is_first_seen_by_watched`
- `new_burst_score`

第一版 baseline 使用同 target 前一等长窗口，不做复杂 EWMA。没有 baseline 时显式触发 `insufficient_baseline` cap。

### Quality Features

输入给 `discussion_quality_score`：

- `mentions`
- `direct_mentions`
- `avg_attribution_confidence`
- `duplicate_text_share`
- `informative_post_count`
- `watched_source_count`
- `market_context_count`
- `avg_post_quality`

post-level quality 使用现有 `post_quality_score`，不再使用 `45 + confidence * 35` 的临时公式。

### Propagation Features

输入给 `propagation_score`：

- `mentions`
- `independent_authors`
- `effective_authors`
- `new_authors`
- `top_author_share`
- `duplicate_text_share`
- `watched_author_count`
- `seed_lag_ms`
- `reproduction_rate`
- `phase_hint`

第一版 `effective_authors` 直接用作者 entropy 计算；没有足够 bucket 时 `reproduction_rate = 0`。

### Tradeability Features

`tradeability_score` 要升级为支持两种 target，不是把 CEX 假装成 CA：

Asset:

- `target_type = "Asset"`
- `identity_status = "resolved_ca"`
- `token_id = target_id`
- `chain`
- `address`
- `market_status`
- `market_cap`
- `liquidity`
- `pool_status`

CexToken:

- `target_type = "CexToken"`
- `identity_status = "resolved_cex"`
- `token_id = target_id`
- `pricefeed_id`
- `native_market_id`
- `quote_symbol`
- `market_status`
- `volume_24h`
- `open_interest`

CEX 不要求 chain/address/pool/market cap。DEX Asset 不要求 CEX venue。

### Timing Features

输入给 `timing_score`：

- `social_signal_start_ms`
- `price_change_since_social_pct`
- `price_change_before_social_pct`
- `market_observation_status`

如果缺 social start 或缺 social start price，timing 必须暴露风险，不能返回静默 neutral。

### Opportunity Features

`opportunity_score` 聚合：

- `heat`
- `quality`
- `propagation`
- `tradeability`
- `timing`

生产 row 的 `decision` 直接采用 `opportunity_score()["decision"]`。没有第二套 `_decision()`。

## Market Baselines

投影必须计算三个价格锚点：

1. `price_at_social_start`：target 在 `social_signal_start_ms` 时点之前最近的 observation。
2. `price_at_reference`：投影时点之前最近的 observation。
3. `price_at_first_snapshot`：target 第一次入库 observation。

派生字段：

- `price_change_since_social_pct = price_at_reference / price_at_social_start - 1`
- `price_change_since_first_snapshot_pct = price_at_reference / price_at_first_snapshot - 1`
- `price_change_before_social_pct = price_at_social_start / price_before_social_start - 1`

如果锚点缺失，字段为 `None`，同时 `price_change_status` 说明原因。

## Token 二级页

新增 token 二级页，不只依赖 drawer：

- 路由：`/tokens/:targetType/:targetId`
- API：复用并扩展 `/api/target-social-timeline`
- 页面目标：按时间复盘“哪条推文 → 当时 token 价格 → 后续价格变化 → 当前评分 ledger”

页面区域：

- Header：target identity、venue、当前价格、first snapshot delta、social start delta。
- Timeline：bucket posts、new authors、watched posts、bucket price、bucket price change。
- Posts：每条推文带 post quality、attribution confidence、message price、observation lag。
- Score Ledger：展示六个 score blocks 的 contributions、risk caps、data health。
- Market Ledger：first snapshot、social start、latest observation、provider/status。

## Market 页面补齐

market/radar row 必须展示：

- `price_change_since_first_snapshot_pct`
- `first_snapshot_observed_at_ms`
- `price_at_first_snapshot`

该字段不替代 social timing，而是回答“第一次进入系统到现在涨跌多少”。social timing 回答“信号开始到现在是否已经追高”。

## 落地顺序

1. 硬切 scoring contract：生产投影接入成熟 scoring 函数，输出 `token-radar-v5-auditable`，删除旧 `_score()` 公式。
2. 扩展 `price_observations` 事件归因字段，并删除 GMGN payload 价格写入路径。
3. 增加 message quote worker：对已解析 CEX/DEX 目标补齐消息价格，并记录观测延迟。
4. 投影计算 market baselines：social start、first snapshot、latest reference。
5. timeline API 输出 post price 和 bucket price overlay。
6. 前端榜单移除旧 `price_health` fallback，接入 `tradeability`、first snapshot delta、二级页。
7. 增加 ops/validation：score 审计、价格覆盖率、高分饱和率、projection freshness。

## 验收标准

- `token_radar_rows.projection_version` 只写 `token-radar-v5-auditable`。
- 生产 `score_json` 包含 `heat/quality/propagation/tradeability/timing/opportunity`，不包含 `price_health`。
- 每个 score block 有非空 `score_version` 和 `contributions`。
- resolved row 的 quality 不再默认 70；低信息重复文本会被 cap。
- sparse public-only row 不能拿到 100 heat。
- stale/missing market row 不能成为 driver。
- unresolved target 只能进入 attention/investigate，不进入 driver/watch 的 resolved lane。
- GMGN payload event 不产生 price observation；只保留 identity evidence / deterministic resolution。
- 解析后的 CEX/DEX message 若 provider 可用，会产生 `message_quote` observation；否则 timeline 显示显式 pending/missing。
- `/api/target-social-timeline` 的 posts 每条都有 `price.status`。
- market/radar row 有 `price_change_since_first_snapshot_pct`，有观察时不为 null。
- `uv run pytest`、`uv run ruff check .`、`uv run python -m compileall src tests` 通过。

## 明确不做

- 不把 `Asset` 和 `CexToken` 合成一个混合 target。
- 不保留 v4 `_score()` 作为 fallback。
- 不在前端把缺失 price 伪装成 fresh。
- 不用 LLM 给 score 直接加分；LLM 只能作为已审计 feature，且 deterministic score 不足时要 cap。
- 不承诺历史 as-of 价格，除非 provider 返回真实历史价格。本阶段只记录消息附近的真实观测和观测延迟。
