# Spec — 推文事件锚点（event_anchor）的写测重构

**Status**: Draft, awaiting review
**Date**: 2026-05-15
**Owner**: Claude with Qinghuan
**Scope**: 仅"市场数据是如何被捕获并附着到 tweet 事件上"的写测重构；不动 Pulse Lab 决策、不动 Token Radar 算法、不动 frontend
**Related**:

- 现状诊断（部分重叠，按本 spec 重新定调）：
  - `docs/superpowers/specs/active/2026-05-12-market-data-pipeline-gap-cn.md`（DEX 市场字段缺失）
  - `docs/superpowers/specs/active/2026-05-11-token-radar-anchor-live-worker-simplification-cn.md`（anchor/live worker 简化）
  - `docs/superpowers/specs/completed/2026-05-04-market-observation-timing-production-spec-cn.md`（market observation timing）
- 全局架构：`docs/ARCHITECTURE.md`、`src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`、`docs/RELIABILITY.md`
- 直接落地代码区：`src/gmgn_twitter_intel/domains/asset_market/{services,runtime,repositories,queries}/`

## 一句话结论

`price_observations(observation_kind='event_anchor')` 在文档里被定义为"event-time 物质事实"，实现上却是一张**只对 100 条最热 resolution 反复轮询、且会被覆盖的 join 输出表**。把它从"fact"降格为"projection"，新建 `market_ticks` 作为唯一右手边时序状态，`enriched_events` 作为可重建的 (tweet, tick) join 投影；三层 capture（WS 订阅 / 批量轮询 / ingest 内联）共写一张 `market_ticks`，ingest 路径同步做 join lookup。删 `AnchorPriceWorker` 与 `price_observations` 整套。

## Background

### 业务诉求

产品承诺：**每条推文，若提及代币，应附带该代币在推文 event-time 的市场快照（price / mcap / liquidity / holders）**。下游 `Token Radar` cohort 归一化、`Signal Pulse` 决策、watchlist timeline 都依赖这个快照。

### 当前架构

`docs/ARCHITECTURE.md:36-46` 明确：

- 不变量 #1：`price_observations` 属于 fact 表
- 不变量 #3：`event_anchor` 描述 event-time 观测，**永不被 live data 覆盖**
- `MarketContext.event_anchor` 服务 event-time 和 back-testing；`decision_latest` 服务当前 UI 与 Pulse

实现侧两条独立路径：

| 路径 | 入口 | 抓取 | 写入 |
|---|---|---|---|
| `AnchorPriceWorker` | `src/gmgn_twitter_intel/domains/asset_market/runtime/anchor_price_worker.py:37-44` | REST 批量轮询，5s/cycle, batch=20, `LIMIT=100` | `price_observations(observation_kind='event_anchor')` |
| `LivePriceGateway` | `src/gmgn_twitter_intel/domains/asset_market/runtime/live_price_gateway.py:218-226` | WS 订阅，`subscription_limit=100`, `hot_target_ttl=300s` | `price_observations(observation_kind='decision_latest')` |

### 关键代码点

- 写入端 enum：`src/gmgn_twitter_intel/domains/asset_market/services/anchor_price_observation.py:204,251` 写 `observation_kind="event_anchor"`
- 读取端 enum：`src/gmgn_twitter_intel/domains/asset_market/queries/pending_anchor_price_query.py:84` 过滤 `observation_kind = 'message_anchor'`（**字面量漂移**，从 `20260513_0036` migration 后 worker 一直跟不上）
- UPDATE 路径：`src/gmgn_twitter_intel/domains/asset_market/repositories/price_observation_repository.py:398-450` 对存量 `event_anchor` 行**覆盖** `observed_at_ms` / `price_usd` 等全字段
- 排序：`pending_anchor_price_query.py:86-89` `ORDER BY hot-first DESC, received_at_ms DESC` + `LIMIT 100` —— hot-poll 而非 catch-up
- 跨 cycle / 跨 worker 缓存：**无**。`anchor_price_observation.py:120` 仅在单 batch 内 dedup `request_items.setdefault`
- 历史回填：**无**。`ops` 子命令含 `backfill-account-quality`、`backfill-harness-jobs`，无 `backfill-anchor`

## 数据现状（实测 2026-05-15）

### 端到端漏斗

| 阶段 | 行数 | 留存率 |
|---|---:|---:|
| `events`（推文，lifetime） | 850,244 | — |
| 有 token 抽取 | 92,929 | 10.9% of tweets |
| `token_intents` | 125,898 | — |
| `token_intent_resolutions(is_current=true, target_id NOT NULL)` | 107,815 | 85.6% of intents |
| `price_observations(observation_kind='event_anchor')` | 44,178 | **41.0% of resolved** |
| **anchor 且 `price_usd IS NOT NULL`** | **20,828** | **19.3% of resolved** |

用户体感"几乎大部分推文锚点缺失"是真的：**已解析的 (tweet, token) 对中 80.7% 没有可用价格快照**。

### 历史 0% 大坑（不可恢复）

按 `events.received_at_ms` 切日：

```
2026-05-07 ~ 05-10:  0%   (~55,927 行 anchor 永久缺失，4 天完全断流)
2026-05-11:         28.4%
2026-05-12 ~ 05-14: 73-88%
2026-05-15:         89.6%
```

2026-05-13 `20260513_0036` migration 将 enum 从 `'message_anchor'` 改为 `'event_anchor'`，但 `pending_anchor_price_query.py:84` 没同步。之后 worker 选不到正确的 pending 集，旧 4 天数据永久跳过；DEX 现货 API 不提供 8 天前毫秒级历史报价 → **架构上不可恢复**。

### 锚点时间漂移

`price_observations(observation_kind='event_anchor')` last 7d, n=44,178：

| 分位 | `observation_lag_ms = observed_at_ms - event_received_at_ms` |
|---|---:|
| p50 | 6.7 min |
| p95 | 119 min |
| p99 | **603 min（10 小时）** |
| max | 1158 min（19 小时） |

也就是说，"event-time anchor" 实际是 "worker 第一次能取到价的处理时刻"。1% 的锚点滞后 ≥ 10h，对叙事代币（10 分钟即可拉盘 5×）失真。

### 空字段比例（已写入的锚点）

last 7d, n=44,178：

| 字段 | 缺失率 |
|---|---:|
| `price_usd IS NULL` | 39.1% |
| `market_cap_usd IS NULL` | 78.3% |
| `liquidity_usd IS NULL` | 39.2% |

`anchor_price_observation.py:217` 仅在 `price is None` 时跳过，其他字段 null 照写 → "成功写入"≠ 拿到快照。

### Token universe 规模与分布

| 维度 | 数量 |
|---|---:|
| `registry_assets` 总量 | 20,557 |
| 7 天内被提及 | 13,335 |
| 24h 内被提及 | 3,187 |
| 1h 内被提及 | 0（低活跃时刻） |
| Per-minute distinct tokens (24h avg) | **11.5** / p95 **24** / max **56** |
| 7d 内一次提及 | 6,242（47%） |
| 7d 内 ≥200 次提及 | 53（占 24% 提及量） |
| `LivePriceGateway` 覆盖（last 24h decision_latest） | 1,345 tokens（**仅 42% of 提及过的**） |

幂律分布：top 53 token 占 24% 流量，bottom 6,000 token 各 1 次。任意时刻最多 50-100 并发活跃，**不存在"几万 token 同时活跃"**。

## Problem

1. **事实合同与实现物理矛盾**。`event_anchor` 被定义为 fact，但其值由"worker 何时碰巧取到价格"决定 —— 是 processing-time 派生，不是 event-time 事实。架构承诺无法被实现兑现，下游所有 cohort 归一化与 back-test 因此失真。

2. **写测路径无 catch-up，无 backfill，无重放**。`AnchorPriceWorker` 是 hot-poll，不是 kappa 意义上的 catch-up loop（`docs/RELIABILITY.md:60-68` 的不变量被违反）。一旦掉队 → 永久掉队。

3. **同一 token 的实时价格分裂在两个进程内存里**。`LivePriceGateway` 的 WS 流和 `AnchorPriceWorker` 的 REST 报价彼此看不见。anchor 路径不读旁边正在跳动的 WS 数据，重复消耗 provider 配额。

4. **缺失被静默掉**。`skipped_missing_market`、`skipped_missing_pricefeed`、batch cooldown 都只增 in-process 计数器，重启清零；下游读模型看到的是"该 (event, token) 没有 anchor 行"——分不清"丢失"和"未到达"。

## First principles

1. **Fact ≠ Join Output**。Fact 是不可重建的原始事实（market_ticks：某一时刻某 token 的价格快照，append-only）；Join Output 是可从 facts 完全重建的派生（`enriched_events`：tweet × tick）。把 join output 当 fact 是架构错位的根源。
2. **Event-time 数据必须在 event-time 捕获**。任何"以后再补"的方案对长尾代币物理失败 —— DEX 现货 API 不提供历史毫秒级查询。inline-at-ingest 是事件时锚的唯一物理可行路径。
3. **缺失是显式状态，不是 NULL**。`capture_method ∈ {tier1_cached, tier2_cached, inline_pull, unavailable}` + `capture_reason` 是产品契约的一部分；下游消费者可据此决定是否信任。
4. **后台 worker 单职责**。WS 订阅、批量轮询、on-demand 抓取互不耦合；写入端虽多入口，状态汇聚到唯一 `market_ticks` 表；读取端永远只有一个 lookup 视图。
5. **物理可实现的不变量**。"每条 resolution 必有 event_anchor" 物理不可保证；"每条 (event, token) 必有 enriched_events 行（含可能 `capture_method=unavailable`）" 物理可保证。降级承诺到可实现的层面。

## Goals

每条是可证伪的：

- **G1**. WHEN 一条 tweet 在 ingest 路径被解析为 `(event, token)` THEN 同步生成一条 `enriched_events` 行，`capture_method ∈ {tier1_cached, tier2_cached, inline_pull, unavailable}`，**100% 无遗漏**（DB 约束保证）。
- **G2**. 对 last 7d ingest 的 tweet，`enriched_events.tick_lag_ms` 的 **p95 ≤ 60s**，**p99 ≤ 300s**（当前 p95=119min, p99=603min）。
- **G3**. 对最近 1h 提及量 top-100 的 token (Tier 1)，`market_ticks` 的连续性满足"任意 60s 窗口内 ≥ 1 tick"，目标 **覆盖率 ≥ 95%**。
- **G4**. 在 last 24h `enriched_events` 上做 `(event_id, target_id)` 去重计数，**恰好等于** `token_intent_resolutions(is_current=true, target_id NOT NULL)` 的同期计数 —— **100% join completeness**。
- **G5**. `DROP TABLE enriched_events; rebuild_from_facts()` 在 last 7d `events × market_ticks` 输入上产出的行集**逐字段相等**于重建前（仅 `created_at_ms` 允许 ±epoch_skew；projection 可重建性）。
- **G6**. 没有任何 SQL 字面量在 reader 与 writer 之间不一致；新增 architecture test 在 CI 红灯（破坏即不可合并）。

## Non-goals

- **N1**. 不重做 token resolver / `token_intent_resolutions` 逻辑（resolver dominance gap 已有独立 spec）。
- **N2**. 不动 frontend；frontend 仍按 `factor_snapshot.market.*` 字段读，下游适配器在本 spec 外。
- **N3**. 不动 Signal Pulse 决策算法 / agent prompt；只换它读的市场数据来源。
- **N4**. 不引入新 provider（DEX Screener / Jupiter / Birdeye / Pyth），仍用 OKX DEX + OKX CEX。
- **N5**. 不做历史 5/7-5/10 的 0% 数据回填（OHLCV 5m approximated backfill 是独立工具，本 spec 不强制）。
- **N6**. 不引入新的运行时（Kafka / Redis Streams / Materialize）；继续在 Postgres + `LISTEN/NOTIFY` 上实现。
- **N7**. 不实现"任意历史 timestamp 的精确报价"功能 —— provider 物理不可。

## Target architecture

### 整体结构

```
                                                  ┌─────────────────┐
       (auto-tiered by mention frequency)         │  market_ticks   │ append-only
                                                  │  (token, t)     │ UNIQUE on (target, ts)
                ┌──→ Tier 1 (top ~100, WS) ──────→│  fact 表        │ TS-partitioned, 30d retain
                │                                 │                 │
                ├──→ Tier 2 (next ~500, batch ──→ │                 │
   token_       │     poll 30s)                   │                 │
   capture_     │                                 │                 │
   tier  ───────┤                                 │                 │
   projection   │                                 └────────▲────────┘
                │                                          │ lookup
                └──→ Tier 3 (long-tail, on-demand)         │ WHERE (target, t±tol)
                            ▲                              │
                            │                              │
                            │                              │
tweet → resolve(sync) ──────┴──────────────────────────────┴──┐
                                                              │
                                                              ▼
                                                     ┌───────────────────┐
                                                     │ enriched_events   │ projection
                                                     │ (event, token)    │ rebuildable from
                                                     │ UNIQUE            │ (events × ticks)
                                                     │ capture_method    │
                                                     │ tick_lag_ms       │
                                                     │ tick_id (FK to    │
                                                     │   market_ticks)   │
                                                     └───────────────────┘
```

### 三层 capture 的职责

- **Tier 1 (WS 订阅, top ~100)**：由 `MarketTickStreamWorker` 维护，订阅 token 集合 = `token_capture_tier WHERE tier=1`，每个 WS tick 写一条 `market_ticks`。本 worker 接管现 `LivePriceGateway` 的持久化职责；`LivePriceGateway` 自身退化为纯 `/ws` fan-out 与 in-process latest 缓存（见下方"与现状的对应"）。
- **Tier 2 (批量轮询, next ~500)**：由 `MarketTickPollWorker` 维护，每 30s 拉一次 `tier=2` 全集，batch quote，写 `market_ticks`。
- **Tier 3 (on-demand, ingest 同步)**：ingest 路径在 resolve 后 lookup `market_ticks`；命中（在 `tolerance_ms` 内）直接用；未命中同步调 quote provider，写一条 `market_ticks` 再用。失败则写 `enriched_events.capture_method='unavailable'` + `capture_reason`。

`token_capture_tier` 由后台 projection 按"最近 1h 提及次数 + 最近 5min 提及" 自动晋升 / 降级，是普通 read model，不是 fact。

### 唯一右手边状态

`market_ticks` 是**所有 capture 路径的唯一去处**，是**所有 join lookup 的唯一来源**。
- 写多入口：Tier 1/2/3 都写
- 读单视图：ingest path 和未来任何 read model 只通过 `market_ticks` 读
- append-only：`(target_type, target_id, observed_at_ms)` UNIQUE；不允许 UPDATE；想覆盖就插入新行（更新 tick）
- TS 分区：按 `observed_at_ms` 日分区，30 天 retention

### 单一 join 输出

`enriched_events` 是 `events × market_ticks` 的 projection，可从二者完全重建。
- 写测时机：ingest 路径同步写入（与 `events` 同事务或紧随其后）
- 写测保证：每条 `(event_id, target_type, target_id)` 恰好一行
- 不允许 UPDATE：tick 后续刷新不改 enrichment 行（事件时锚点定格）
- 可重建：删表后扫 `events × market_ticks` 重 join，值相等

### 与现状的对应

| 现状 | 新设计 |
|---|---|
| `price_observations(event_anchor)` | **删**。语义被 `enriched_events.tick_observation_id` + `market_ticks` 替代 |
| `price_observations(decision_latest)` | **改成 `market_ticks`**。decision_latest 这个 partition 概念消失；所有 tick 都在 `market_ticks`，时序连续即可代表"最新" |
| `AnchorPriceWorker` | **删**。Tier 3 ingest-inline 接管 + Tier 1/2 持续覆盖 |
| `LivePriceGateway` 的写测 | **改为 `MarketTickStreamWorker`**，目标表换 `market_ticks` |
| `LivePriceGateway` 的 in-process cache + WS fan-out | **保留**，但只服务 `/ws` 推送，不再是持久化职责 |
| `should_persist_live_observation` 写入预算 | **简化**。tick 直接 append-only；同 token 同毫秒 UNIQUE 即去重 |

## Conceptual data flow

```
            GMGN public stream                       OKX DEX/CEX
                  │                                       │
                  ▼                                       │
        domains/ingestion                                 │
        (snapshot gate, frame normalise)                  │
                  │                                       │
                  ▼                                       │
        domains/evidence                                  │
        - events (FACT)                                   │
        - token_intents                                   │
        - token_intent_resolutions                        │
                  │                                       │
                  ▼                                       │
        ┌─── domains/asset_market (ingest 同步路径) ───┐  │
        │  resolve(tweet, mention) → target            │  │
        │  lookup market_ticks(target, t_event ± tol)  │  │
        │  ┌───────────┴───────────┐                   │  │
        │  ▼ HIT                   ▼ MISS              │  │
        │  use cached              quote_now ──────────┼──┤
        │                          ▼                   │  │
        │                          INSERT              │  │
        │                          market_ticks ◄──────┼──┘
        │                          ▲                   │
        │                          │                   │
        │  INSERT enriched_events  │                   │
        └──────────────────────────┘                   │
                  │                                    │
                  │              ┌──── Tier 1 ─────────┤
                  │              │   WS stream worker  │
                  │              │                     │
                  │              └────► market_ticks ◄─┤
                  │                                    │
                  │              ┌──── Tier 2 ─────────┤
                  │              │   batch poll 30s    │
                  │              │                     │
                  │              └────► market_ticks ◄─┘
                  ▼
        domains/token_intel
          - token_radar_rows 读 enriched_events.market 字段
        domains/pulse_lab
          - pulse_candidates 读 enriched_events
        app/surfaces/api + /ws
```

新增的箭头：

- `ingest 同步路径 → market_ticks`（Tier 3 inline pull）：现在没有这条；原因：唯一能保证 event-time 锚不漂移的物理路径。
- `MarketTickPollWorker → market_ticks`（Tier 2）：现在没有这条；原因：填补 WS 订阅上限之外的"次活跃"token 覆盖。
- `ingest → enriched_events`：替代现在的 `AnchorPriceWorker → price_observations`。

消失的箭头：

- `AnchorPriceWorker → price_observations(event_anchor)`：worker 删除。
- `LivePriceGateway → price_observations(decision_latest)`：写测下沉到 `market_ticks`；gateway 仅保留 WS fan-out。

## Core models

### `market_ticks` — fact

单个市场 tick，append-only。

- `tick_id`（合成主键，UUID 或确定性 hash）
- `target_type` ∈ {`Asset`, `CexToken`}
- `target_id`
- `observed_at_ms`（来自 provider 的报价时间戳；缺失则拒绝写入）
- `received_at_ms`（本地接收时间，便于诊断网络延迟）
- `source_tier` ∈ {`tier1_ws`, `tier2_poll`, `tier3_inline`}
- `source_provider` ∈ {`okx_dex_ws`, `okx_dex_rest`, `okx_cex_rest`}
- `pricefeed_id`（保留与 `price_feeds` 表的关联）
- `price_usd`, `price_quote`, `quote_symbol`, `price_basis`
- `market_cap_usd`, `liquidity_usd`, `holders`, `volume_24h_usd`, `open_interest_usd`
- `raw_payload_hash`
- 不变量：`(target_type, target_id, observed_at_ms)` UNIQUE；任意字段一旦写入不可修改

### `token_capture_tier` — projection

token 的 capture 层级；由 mention frequency 派生。

- `target_type`, `target_id`
- `tier` ∈ {1, 2, 3}
- `mention_count_1h`, `mention_count_24h`, `last_mention_at_ms`
- `tier_assigned_at_ms`
- 不变量：每个 (target_type, target_id) 唯一一行；tier 由 projection worker 单点写

### `enriched_events` — projection

`events × market_ticks` 的 join 输出。

- `event_id` (FK to `events`)
- `target_type`, `target_id`
- `t_event_ms`（冗余，便于查询）
- `tick_id` (FK to `market_ticks.tick_id`，可空)
- `tick_lag_ms`（`|tick.observed_at_ms - t_event_ms|`，可空）
- `capture_method` ∈ {`tier1_cached`, `tier2_cached`, `inline_pull`, `unavailable`}
- `capture_reason`（仅 `unavailable` 时填，例如 `provider_timeout`, `no_market_data`, `rate_limited`, `tolerance_exceeded`）
- `created_at_ms`
- 不变量：`(event_id, target_type, target_id)` UNIQUE；不允许 UPDATE；`tick_id NOT NULL ⟺ capture_method ≠ 'unavailable'`

## Interface contracts

### HTTP/WS（对外消费）

- `/api/token-radar`、`/api/recent`、`/api/search/inspect`、`/api/pulse/*`、`/ws` 的 payload 中 `factor_snapshot.market.*` 字段语义不变；底层数据源换为 `enriched_events JOIN market_ticks`。**前端无须变更**。
- 新增可选字段 `factor_snapshot.market.capture_method` 与 `tick_lag_ms`，让前端能选择性展示"该快照是 inline 实时取的"还是"缓存的"。
- 不再暴露 `event_anchor` / `decision_latest` 概念；如果某 read model 文档暴露过这两个词，按 `docs/CONTRACTS.md` 更新。

### CLI

- 删除：`ops` 隐式依赖的 anchor worker 状态命令（若存在）
- 新增：
  - `ops promote-token-tier <target_type> <target_id> <tier>`：手动调级
  - `ops backfill-market-ticks --from=DAY --to=DAY --provider=okx`：可选历史 tick 回填（不强制；不影响 enriched_events 准确性）

### 内部 Provider 契约

- `dex_quote_market.token_quotes` 与 `cex_market.ticker` 接口不变；但 **inline 路径必须配置 strict timeout（≤ 1s）** 并在超时后走 `capture_method='unavailable' + capture_reason='provider_timeout'`，**不阻断 events 表写入**。
- WS provider (`stream_price_info`) 接口不变；订阅集合来源从 `active_live_market_targets`（基于 `token_radar_rows`）改为 `token_capture_tier WHERE tier=1`。

## Acceptance criteria

- **AC1**. WHEN 一条 tweet 被 ingest 路径解析为 `(event, target_type, target_id)` THEN 同事务（或保证最终一致的紧随事务）写一条 `enriched_events` 行，且 `capture_method` 必填、与 `tick_observation_id` 的 NULL 状态一致（约束级别）。
- **AC2**. WHEN 一个 `(target_type, target_id, observed_at_ms)` 已存在于 `market_ticks` THEN 重复 INSERT 不报错且**不修改任何字段**（idempotent via `ON CONFLICT DO NOTHING`）。
- **AC3**. WHEN 上游 provider 返回 `price_usd IS NULL` THEN inline 路径**不写 `market_ticks`** 且对应 `enriched_events.capture_method='unavailable'`, `capture_reason='no_market_data'`。
- **AC4**. WHEN 我们在 ingest 时获取的 tick 与 event 的时间差 ≤ `tier_tolerance_ms[tier]`（默认 Tier 1=60s, Tier 2=180s, Tier 3=600s）THEN 标 `capture_method=tier{N}_cached` 并复用；否则 falls through 到 inline pull。
- **AC5**. 对 last 7d 的所有 `enriched_events`，**`tick_lag_ms` 的 p95 ≤ 60s 且 p99 ≤ 300s**（架构 SLO）。
- **AC6**. 对 last 24h 的 `enriched_events`，**`COUNT(*) = COUNT(DISTINCT (event_id, target_type, target_id)) = (resolved-with-target 总数)`**（join completeness）。
- **AC7**. `DROP TABLE enriched_events; CALL rebuild_enriched_events()` 在 last 7d 数据上产出的行集合与现网行**逐行 deep-equal**（除 `created_at_ms` 容许 ±epoch_skew）。
- **AC8**. CI 含一条 architecture test：扫描所有 SQL 字符串字面量中出现的 `observation_kind` / `source_tier` / `capture_method` 取值，必须 ⊆ 当前 enum；不一致即红灯（防止 `'message_anchor'` 类漂移重演）。
- **AC9**. ingest 路径在 inline pull 超时（≥1s）时**仍能完成 `events` 写入**；不存在"price provider 挂了 → tweet 落不下来"的传染。
- **AC10**. `market_ticks` 表无 UPDATE 入口（DB 层 REVOKE UPDATE 或 application 层不实现 update 函数；架构 test 验证）。

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Ingest 同步耦合 provider 延迟，导致 tweet 入库慢 | High | inline pull 严格 timeout（≤1s）；超时即同事务写 `capture_method='unavailable', capture_reason='provider_timeout'`，**events 与 enriched_events 仍在同一事务提交**，不引入 outbox / async retry（保持简单，由 Tier 1/2 持续覆盖弥补） |
| Tier 2 批量轮询过量调用 OKX REST 触发限流 | Medium | 默认 30s 周期 + batch 50 + p95 token 数预计 24/min → 远低于限流；加 backoff + jitter + 自适应 batch_size |
| 长尾 token (Tier 3) inline pull 命中 provider null payload | Medium | 显式 `capture_method='unavailable'` + `capture_reason`，下游 gate 必须 fail-closed |
| 历史 5/7-5/10 的 0% 永久缺口 | Accepted | 公开 `coverage_since='2026-05-11'`；本 spec 不做回填（见 N5），如未来另开 spec 做 OHLCV approximated 回填，需在 enum 中扩 `source_tier='backfill_approximation'` 一档 |
| `token_capture_tier` 抖动导致同 token 频繁跨层 | Low | EMA / hysteresis：升级触发阈值与降级触发阈值不对称（升级激进、降级保守） |
| `enriched_events` 与下游 read model schema 不兼容 | Medium | hard-cut 同 PR 改下游读路径；下线 `price_observations` 留 1 个 PR 间隔以便 hotfix 回滚 |
| Tolerance 选错（过松 → 漂移；过紧 → miss） | Medium | 每个 tier 单独配置；上线后用 ACS 监控 `tick_lag_ms` 分布 + `capture_method` 占比；按数据调整 |

## Evolution path

- **下一步可扩展**：
  - 自动学习 tolerance（按 token 波动率给 per-token 容忍）
  - 多 provider redundancy（在 `market_ticks.source_provider` 维度做交叉对账，发现 OKX 异常时切 backup）
  - 真正的 back-testing replay：`market_ticks` 按时分区 + retention 调长，可重放任意时间窗口
  - 把 `enriched_events` 进一步派生出"asset-level cohort percentile snapshot"消除 `token_radar_projection.py` 里的 cohort 计算重复
- **要小心不要前置约束的事**：
  - 不把 `tick_observation_id` 暴露到 frontend：未来若 tick 表分区化或更换底层（Timescale / Pinot），FK 形态会变；保留 internal-only
  - 不把 `capture_method` 枚举当作产品口径（PR 文案外不暴露具体取值）：未来 capture 路径可能扩展

## Alternatives considered

- **Alt A — 单 worker 修 dedup bug 即可，不重做架构**。Rejected：bug 修了只解决"反复刷 100 行"的浪费，不解决事件时漂移、不解决长尾覆盖、不解决"anchor 被当 fact"的合同错配。3 个月内还会撞同样的根。
- **Alt B — 全 WS 订阅所有 token**。Rejected：OKX DEX WS 单连接订阅上限 ~100；20k token 物理不可行；多连接 sharding 把账号风控风险拉高。
- **Alt C — 全 on-demand pull-on-arrival，不分层**。Rejected at higher load：现 scale 11/min 可行，但产品热度上来后 100+/min 会撞 REST 限流；分层是必要 future-proofing。
- **Alt D — 保留 `price_observations` 两个 partition，新增 `enriched_events` 但不删旧表**。Rejected：dual-write 维护成本高，"fact 是 join output" 的合同错配仍在；不变量 #1 名实不副；与用户 hard-cut 偏好不符（见 `feedback_hard_cut_style`）。
- **Alt E — 新建 `anchor_dlq` 表跟踪失败重试**。Rejected：失败状态已由 `enriched_events.capture_method='unavailable'` + `capture_reason` 表达；多张表是把同一状态拆三个地方维护。如要重试，加 `next_retry_at_ms` 列到 `enriched_events` 即可。
- **Alt F — 引入 Kafka + Materialize / RisingWave 做真正 streaming join**。Rejected：runtime 复杂度跳升一档；现 scale 850k events / 90 天，Postgres + LISTEN/NOTIFY 物理够用；引入新运行时违反 KISS。
- **Alt G — 引入 TimescaleDB hypertable 给 `market_ticks`**。Deferred：上线后再评。30 天 retention + 日分区在原生 PG 上对 ~10k ticks/day 完全够用；写入量超过 100k ticks/day 时再考虑 Timescale。

## Boundaries

| Class | Behaviour |
|---|---|
| Always | 每条 resolved `(event, token)` 都有一行 `enriched_events`；ingest 路径不被 provider 失败阻塞；`market_ticks` 仅 append-only；`enriched_events` 仅 INSERT；`capture_method` 必填且与 `tick_observation_id` NULL 状态一致 |
| Ask first | 调整 tier tolerance 默认值；手动晋升 / 降级 token tier；调整 Tier 2 周期 / batch；扩 retention 窗口 |
| Never | UPDATE `market_ticks`；UPDATE `enriched_events`；在 HTTP / WS 处理器内同步调 provider 报价；用 `LISTEN/NOTIFY` 作为唯一数据投递保证（必须 bounded interval catch-up）；在 ingest 同步路径内做 LLM / agent 调用 |

## 决策待定

- **D1**. Tier 1 / Tier 2 容量上限：100 / 500 是初值；上线后按 OKX 实际限流和命中率调（可观察）。
- **D2**. ingest inline pull 的 strict timeout 默认值：1s 是初值（保住 ingest p95 落库 < 2s）；如 OKX REST p95 ~ 200ms 则可放到 500ms 更紧。
- **D3**. `enriched_events` 与 `events` 是否同事务：当前倾向**同事务**（简单、强一致、inline timeout 已 bound 总耗时）；如压测后 ingest p95 超阈，再退化为先写 events 再后置写 enriched（紧随同进程，无 outbox 队列）。
- **D4**. 是否实施 5/7-5/10 的 OHLCV approximated 回填：默认不做；如产品强需历史完整性再做。
- **D5**. Tier 3 inline pull 在 provider 限流时是否短退避后重试：倾向直接写 `unavailable` 不重试（避免雪崩），用 Tier 2 兜底；但 Tier 2 覆盖周期较长，可能存在 30s gap。

## 参考量化点（生成于 2026-05-15）

| 指标 | 真实值 |
|---|---|
| lifetime events | 850,244 |
| lifetime resolved with target | 107,815 |
| lifetime event_anchor | 44,178 |
| lifetime anchor with `price_usd NOT NULL` | 20,828 (**19.3% of resolved**) |
| 5/7-5/10 anchor retention | 0% (4 天断流) |
| 5/14 anchor retention | 88.0% |
| 5/15 anchor retention | 89.6% |
| anchor `observation_lag_ms` p50 / p99 (7d) | 6.7 min / 603 min |
| anchor `price_usd IS NULL` (7d) | 39.1% |
| anchor `market_cap_usd IS NULL` (7d) | 78.3% |
| registry_assets total | 20,557 |
| distinct tokens mentioned 7d | 13,335 |
| distinct tokens mentioned 24h | 3,187 |
| distinct tokens / min (24h avg / p95 / max) | 11.5 / 24 / 56 |
| 7d 一次提及 token | 6,242 (47%) |
| 7d ≥200 提及 token | 53 (24% mentions) |
| LivePriceGateway WS 订阅上限 | 100 |
| AnchorPriceWorker interval / LIMIT | 5s / 100 |
| 24h decision_latest 覆盖 distinct tokens | 1,345 (42% of mentioned) |
