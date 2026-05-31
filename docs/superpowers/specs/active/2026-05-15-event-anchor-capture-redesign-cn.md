# Spec — 推文事件锚点（event_anchor）的写测重构

**Status**: Draft, awaiting review
**Date**: 2026-05-15 (revised after worker runtime hard cut)
**Owner**: Claude with Qinghuan
**Scope**: 仅"市场数据是如何被捕获并附着到 tweet 事件上"的写测重构；不动 Pulse Lab 决策、不动 Token Radar 算法、不动 frontend
**Depends on**:
  - `docs/superpowers/specs/active/2026-05-15-worker-runtime-platform-cn.md`（**已 hard-cut 实施于 commits `6d48cf85`, `b7efc616`**；本 spec 在 `WorkerBase` / `DBPoolBundle` / `workers.yaml` / `WorkerScheduler` 已存在的前提下书写，并修订该 spec 的 13-row 矩阵中 `anchor_price` 与 `live_price_gateway` 两行）
**Related**:
  - 现状诊断（部分重叠，按本 spec 重新定调）：
    - `docs/superpowers/specs/active/2026-05-12-market-data-pipeline-gap-cn.md`（DEX 市场字段缺失）
    - `docs/superpowers/specs/active/2026-05-11-token-radar-anchor-live-worker-simplification-cn.md`（anchor/live worker 简化）
    - `docs/superpowers/specs/completed/2026-05-04-market-observation-timing-production-spec-cn.md`（market observation timing）
  - 全局架构：`docs/ARCHITECTURE.md`、`src/parallax/domains/asset_market/ARCHITECTURE.md`、`docs/RELIABILITY.md`、`docs/WORKERS.md`
  - 直接落地代码区：`src/parallax/domains/asset_market/{services,runtime,repositories,queries}/`、`src/parallax/app/runtime/{worker_base,db_pool_bundle,worker_scheduler,bootstrap}.py`

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

实现侧两条独立路径（**2026-05-15 worker hard-cut 后**两者都已迁到 `WorkerBase` 基类，但写入语义不变）：

| 路径 | 入口 | 抓取 | 写入 |
|---|---|---|---|
| `AnchorPriceWorker(WorkerBase)` | `src/parallax/domains/asset_market/runtime/anchor_price_worker.py:35-73`（已 short-borrow：先开 session select pending → 关 session → fetch quotes → 重开 session 写 observation） | REST 批量轮询，由 `workers.yaml.anchor_price.interval_seconds + batch_size` 配置 | `price_observations(observation_kind='event_anchor')` |
| `LivePriceGateway(WorkerBase)` | `src/parallax/domains/asset_market/runtime/live_price_gateway.py:74`（`_active_targets` 通过 `repos.registry.active_live_market_targets` 选订阅集） | WS 订阅，由 `workers.yaml.live_price_gateway` 配置 `subscription_limit`、`hot_target_ttl_seconds` | `price_observations(observation_kind='decision_latest')` |

### 关键代码点

- 写入端 enum：`src/parallax/domains/asset_market/services/anchor_price_observation.py:273,320` 写 `observation_kind="event_anchor"`
- 读取端 enum：`src/parallax/domains/asset_market/queries/pending_anchor_price_query.py:84` 过滤 `observation_kind = 'message_anchor'`（**字面量漂移**，从 `20260513_0036` migration 后 worker 一直跟不上；**worker runtime hard-cut 后仍未修复** —— 该 bug 不在 worker 平台 spec 范围内）
- 允许 enum：`src/parallax/domains/asset_market/repositories/price_observation_repository.py:15` `MARKET_OBSERVATION_KINDS = frozenset({"event_anchor", "decision_latest"})`
- UPDATE 路径：`price_observation_repository.py:398-450` 对存量 `event_anchor` 行**覆盖** `observed_at_ms` / `price_usd` 等全字段（破坏 ARCH #3 "Anchor describes the event-time observation; it is never overwritten by live data"）
- 排序：`pending_anchor_price_query.py:86-89` `ORDER BY hot-first DESC, received_at_ms DESC` + `LIMIT` —— hot-poll 而非 catch-up
- 跨 cycle / 跨 worker 缓存：**无**。`anchor_price_observation.py` 中的 `_fetch_dex_quotes` 仅在单 batch 内 dedup `request_items.setdefault`；`AnchorPriceWorker` 不读 `LivePriceGateway` 的 in-process WS 缓存（两个 worker 独立持有 in-memory state）
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
| `price_observations(event_anchor)` | **删**。语义被 `enriched_events.tick_id` + `market_ticks` 替代 |
| `price_observations(decision_latest)` | **改成 `market_ticks`**。decision_latest 这个 partition 概念消失；所有 tick 都在 `market_ticks`，时序连续即可代表"最新" |
| `AnchorPriceWorker(WorkerBase)` | **删** 整个 class 及其 service / query 模块。Tier 3 ingest-inline 接管 + Tier 1/2 持续覆盖 |
| `LivePriceGateway(WorkerBase)` 的写测职责 | **拆分**：持久化迁到新 `MarketTickStreamWorker(WorkerBase)`，目标表 `market_ticks`；in-process cache 与 `/ws` fan-out 留在 `LivePriceGateway`，但它不再 INSERT |
| `should_persist_live_observation` 写入预算 | **取消**。改为 `market_ticks.(target, observed_at_ms)` UNIQUE 自然去重；不再需要"应该不应该持久化"的策略函数 |
| `repos.registry.active_live_market_targets` | **替换** 为 `repos.tier.subscribe_targets(tier=1)`；订阅集来源从 `token_radar_rows.computed_at_ms` 换成 `token_capture_tier.tier=1` |
| `pending_anchor_price_query.py` | **删**。无对应替代（不再需要"哪些 resolution 没 anchor"概念） |
| `MARKET_OBSERVATION_KINDS` enum | **删整张 `price_observations` 表后 enum 自然消失** |

### 与 Worker Runtime Platform Spec 的协同

本 spec 在 `2026-05-15-worker-runtime-platform-cn.md` 已 hard-cut 实施的前提下书写。要点：

1. **基类**：所有新增 worker（`MarketTickStreamWorker`、`MarketTickPollWorker`、`TokenCaptureTierWorker`）继承 `app/runtime/worker_base.py:WorkerBase`，实现 `async run_once() -> WorkerResult`；运行循环 / metrics / `application_name` 自动由基类负责。
2. **连接持有契约**：所有新 worker 与 ingest 路径的 Tier 3 inline-pull **必须遵守 `db.worker_session(name)` short-borrow 契约**（worker spec G2/AC1）—— 任何 HTTP/WS provider IO 不在 session 块内。Tier 3 在 IngestService 中体现为：
   - 短借 session A：写 `events`
   - 释放 session A
   - 短借 session B：lookup `market_ticks`（命中则记录 tick_id）
   - 释放 session B
   - 若未命中：调 provider quote（**池外**，1s timeout）
   - 短借 session C：写 `market_ticks` + `enriched_events`（同事务）
3. **`workers.yaml` 变更**（hard-cut，同 plan 内）：
   - 删除：`anchor_price`
   - 改语义：`live_price_gateway`（保留 key，配置项简化为 cache + ws fan-out；删除 `subscription_limit` 等订阅参数）
   - 新增：`market_tick_stream`（Tier 1 WS 写入）、`market_tick_poll`（Tier 2 批量轮询）、`token_capture_tier`（projection）
   - 所有新 key 加入 `WorkersSettings`（`platform/config/settings.py`），保持 `extra="forbid"`
4. **修订 worker spec 的 13-row 矩阵**（同 plan 内提交，参见 Risks 关于跨 spec 协调）：
   - 删除行：`AnchorPriceWorker`
   - 修改行：`LivePriceGateway`（"主要 gap" 改为 "持久化职责迁出"，不再列 `provider_state_change` 触发器项）
   - 新增 3 行：`MarketTickStreamWorker`、`MarketTickPollWorker`、`TokenCaptureTierWorker`，按矩阵 8 项契约填写
5. **单写者保护**：
   - `TokenCaptureTierWorker` 声明 `SINGLE_WRITER_KEY`（projection writer）
   - `MarketTickStreamWorker` / `MarketTickPollWorker` **不**声明（market_ticks 是 fact，append-only + UNIQUE 自然安全；多 worker 写同一表与现有 `events` 多 ingest 源一致）
6. **wake channels**：
   - 删除：`market_observation_written`（被 `market_tick_written` 替代）；`AnchorPriceWorker`、`LivePriceGateway` 的 emitter 角色消失
   - 新增：`market_tick_written`（Tier 1/2/3 写入后 emit；下游 `TokenRadarProjectionWorker` 等监听）
   - 保留：`resolution_updated`（不在本 spec 范围）

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

- **AC1**. WHEN 一条 tweet 被 ingest 路径解析为 `(event, target_type, target_id)` THEN 同事务（或保证最终一致的紧随事务）写一条 `enriched_events` 行，且 `capture_method` 必填、与 `tick_id` 的 NULL 状态一致（约束级别：`tick_id NOT NULL ⟺ capture_method ≠ 'unavailable'`）。
- **AC2**. WHEN 一个 `(target_type, target_id, observed_at_ms)` 已存在于 `market_ticks` THEN 重复 INSERT 不报错且**不修改任何字段**（idempotent via `ON CONFLICT DO NOTHING`）。
- **AC3**. WHEN 上游 provider 返回 `price_usd IS NULL` THEN inline 路径**不写 `market_ticks`** 且对应 `enriched_events.capture_method='unavailable'`, `capture_reason='no_market_data'`。
- **AC4**. WHEN 我们在 ingest 时获取的 tick 与 event 的时间差 ≤ `tier_tolerance_ms[tier]`（默认 Tier 1=60s, Tier 2=180s, Tier 3=600s）THEN 标 `capture_method=tier{N}_cached` 并复用；否则 falls through 到 inline pull。
- **AC5**. 对 last 7d 的所有 `enriched_events`，**`tick_lag_ms` 的 p95 ≤ 60s 且 p99 ≤ 300s**（架构 SLO）。
- **AC6**. 对 last 24h 的 `enriched_events`，**`COUNT(*) = COUNT(DISTINCT (event_id, target_type, target_id)) = (resolved-with-target 总数)`**（join completeness）。
- **AC7**. `DROP TABLE enriched_events; CALL rebuild_enriched_events()` 在 last 7d 数据上产出的行集合与现网行**逐行 deep-equal**（除 `created_at_ms` 容许 ±epoch_skew）。
- **AC8**. CI 含一条 architecture test：扫描所有 SQL 字符串字面量中出现的 `observation_kind` / `source_tier` / `capture_method` 取值，必须 ⊆ 当前 enum；不一致即红灯（防止 `'message_anchor'` 类漂移重演）。
- **AC9**. ingest 路径在 inline pull 超时（≥1s）时**仍能完成 `events` 写入**；不存在"price provider 挂了 → tweet 落不下来"的传染。
- **AC10**. `market_ticks` 表无 UPDATE 入口（DB 层 REVOKE UPDATE 或 application 层不实现 update 函数；架构 test 验证）。
- **AC11** *(WorkerBase 合规)*. 3 个新 worker 全部继承 `app/runtime/worker_base.py:WorkerBase`，其 `run_once` 内不在 `db.worker_session(...)` 块内 `await` 外部 IO（worker spec AC1 一致）；架构 test `test_no_external_io_inside_db_session` 扩展覆盖新 worker 模块。
- **AC12** *(ingest 路径合规)*. IngestService Tier 3 inline-pull 路径满足：（a）`events` 与 `enriched_events` 在同事务提交；（b）provider quote 调用**不在** session 块内；（c）provider timeout 严格 ≤ 1s，超时不影响 `events` 提交。架构 test + 单元 test 双管。
- **AC13** *(workers.yaml schema)*. `WorkersSettings` 已删除 `anchor_price` key、新增 3 个 `market_tick_*` / `token_capture_tier` key；`extra="forbid"` 下旧 key 出现即 ValidationError 拒启。

## Observability、Cost、Capacity SLO

本节是对 G2-G6 的具体度量与阈值绑定，避免"目标可观察但无数字"的盲区。

### Observability — 每 worker 自动暴露 + 业务级补充

继承 `WorkerBase` 自动获得 worker spec 已定义的 `worker_processing_seconds` / `worker_jobs_in_flight` / `worker_jobs_total{status}` / `worker_lag_seconds` 等指标。本 spec 额外要求暴露：

| 指标 | 单位 | 计算位置 | 目标 SLO |
|---|---|---|---|
| `enriched_events_capture_method_total{method}` | counter | IngestService | inline_pull 占比 ≤ 40%，unavailable 占比 ≤ 5%（hot 数据） |
| `enriched_events_tick_lag_ms` | histogram | IngestService 写入时计算 | p95 ≤ 60s, p99 ≤ 300s（G2） |
| `market_ticks_tier_coverage_ratio{tier}` | gauge | TokenCaptureTierWorker | tier=1 中 last-60s-tick 覆盖率 ≥ 95% |
| `market_ticks_inline_pull_latency_ms` | histogram | IngestService Tier 3 | p95 ≤ 500ms, p99 ≤ 1000ms (与 timeout 一致) |
| `market_ticks_inline_pull_timeout_total` | counter | IngestService Tier 3 | 24h rate < 5% of inline pulls |
| `token_capture_tier_promotions_total{from,to}` | counter | TokenCaptureTierWorker | 每 token 24h 内 tier 切换 ≤ 4 次（防抖动） |

所有以上指标在 `/readyz` 的对应 worker 节加 `notes` 字段，便于运维快速读。

### Cost — 量化 provider 调用预算

| 路径 | 调用频率 | 24h 上限估算 | 触发限流的红线 |
|---|---|---|---|
| Tier 1 WS | 持续订阅 100 channels | 单 WS 连接，零额外 REST 配额 | OKX DEX WS 单连接上限 ~200 channels — 100 留余量 |
| Tier 2 batch poll | 30s × 500 token / batch 50 = 6 req × 2880 cycles = 17,280 req/day | ~0.2 req/sec 稳态 | OKX DEX REST 软限 ~10 req/sec/IP — 远低于 |
| Tier 3 inline | 每条 mentioned tweet 最差一次 = 11.5/min × 1440 = 16,560 req/day | ~0.2 req/sec 稳态 | 同上 |
| **合计 REST** | — | ~34k req/day | < 5% of OKX 限额 |

Cost 异常告警：
- WHEN 任一 tier 24h 调用量超出预算 3× THEN `/readyz` `degraded` + Slack/Telegram 通知（已有通道）
- WHEN OKX 返回 429/403 持续 ≥ 5min THEN 整 tier 进入退避模式，写入流量降级到 Tier 1 only

### Capacity — Tier 容量与晋升规则

| Tier | 默认容量 | 晋升阈值 | 降级阈值（hysteresis） |
|---|---|---|---|
| Tier 1 (WS) | 100 token | mention_count_1h ≥ 5 **或** 在 `pulse_candidates(last 1h)` 中出现 | mention_count_1h < 1 **且** 持续 30 分钟（防抖） |
| Tier 2 (poll) | 500 token | mention_count_1h ≥ 1 **或** mention_count_24h ≥ 5 | mention_count_24h < 1 持续 6h |
| Tier 3 (on-demand) | 无 | 默认 tier | — |

容量上限可经 `workers.yaml` 调；超出上限按 `mention_count_1h DESC` 截断。当 Tier 1 满载且 Tier 2 满载时，新 mention 走 Tier 3 inline pull —— 不阻塞产品。

### Eval — 上线前 + 持续验证

- **上线前 backtest**：用 last 7d `events` 重放，对每条 resolved (event, token) 重新走 Tier 3 inline 路径，记录 `tick_lag_ms` 与 `capture_method` 分布；要求 ≥ 80% 的 mentions 在重放下能拿到 `inline_pull` 且 lag p95 ≤ 60s。否则 spec 上线被卡。
- **上线后回归 eval**：每周自动跑 `parallax ops eval-anchor-capture --since=7d`，输出 G2/G3 的实际值与目标差异；落 7d 趋势到 `docs/generated/anchor-capture-slo.md`

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
| 与 worker spec 的 13-row 矩阵冲突（matrix 假设 `anchor_price` / `live_price_gateway` 继续存在并 fix per-row gap） | Medium | 同 plan 内提交 worker spec 的矩阵修订（删 `anchor_price` 行；改写 `live_price_gateway` 行；新增 3 行）；plan 顺序确保 worker spec 矩阵不会在中间状态被引用为合规标准 |
| `WorkersSettings(extra="forbid")` schema 变更顺序：删 `anchor_price` key 与新增 `market_tick_*` key 必须在同 commit | Medium | 在 plan 任务里把 schema 变更与新 worker 类提交、yaml.bak 备份、旧 worker 删除合并到一个 commit；提供单 alembic-style "settings migration" 测试 |
| 新增 wake channel `market_tick_written` 与现有 `market_observation_written` 并存导致 downstream 双订阅 | Low | hard-cut 同 plan 内：先迁 downstream（`TokenRadarProjectionWorker` 等）订阅源到新 channel，再删旧 channel emitter；架构 test 扫 `pg_notify\\(['"]market_observation_written` 字面量为 0 |
| Tier 3 inline pull 撞 OKX REST 限流，导致 ingest 路径整体降级到 `unavailable` | Medium | 限流时短路到只走 in-process LivePriceGateway cache（命中即 `capture_method='tier1_cached'`）；Tier 2 兜底保持运转；运维通过 `market_ticks_inline_pull_timeout_total` 告警 |

## Evolution path

- **下一步可扩展**：
  - 自动学习 tolerance（按 token 波动率给 per-token 容忍）
  - 多 provider redundancy（在 `market_ticks.source_provider` 维度做交叉对账，发现 OKX 异常时切 backup）
  - 真正的 back-testing replay：`market_ticks` 按时分区 + retention 调长，可重放任意时间窗口
  - 把 `enriched_events` 进一步派生出"asset-level cohort percentile snapshot"消除 `token_radar_projection.py` 里的 cohort 计算重复
- **要小心不要前置约束的事**：
  - 不把 `tick_id` 暴露到 frontend：未来若 tick 表分区化或更换底层（Timescale / Pinot），FK 形态会变；保留 internal-only
  - 不把 `capture_method` 枚举当作产品口径（PR 文案外不暴露具体取值）：未来 capture 路径可能扩展

## Alternatives considered

- **Alt A — 单 worker 修 dedup bug 即可，不重做架构**。Rejected：bug 修了只解决"反复刷 100 行"的浪费，不解决事件时漂移、不解决长尾覆盖、不解决"anchor 被当 fact"的合同错配。3 个月内还会撞同样的根。
- **Alt A2 — 按 worker spec 13-row 矩阵修 anchor_price / live_price_gateway 那两行的 per-row gap，保留写测语义**。Rejected：worker spec 矩阵处理的是运行时合规（连接持有、自报家门、metrics、yaml 配置），不是写测语义。修完矩阵后 anchor 仍是被覆盖的 join output、`message_anchor` SQL bug 仍在、provider 数据缺失仍静默 —— 用户感知的 80.7% 锚点缺失不动。**矩阵合规与写测重构是正交的两层问题**，不可互相替代。
- **Alt B — 全 WS 订阅所有 token**。Rejected：OKX DEX WS 单连接订阅上限 ~100；20k token 物理不可行；多连接 sharding 把账号风控风险拉高。
- **Alt C — 全 on-demand pull-on-arrival，不分层**。Rejected at higher load：现 scale 11/min 可行，但产品热度上来后 100+/min 会撞 REST 限流；分层是必要 future-proofing。
- **Alt D — 保留 `price_observations` 两个 partition，新增 `enriched_events` 但不删旧表**。Rejected：dual-write 维护成本高，"fact 是 join output" 的合同错配仍在；不变量 #1 名实不副；与用户 hard-cut 偏好不符（见 `feedback_hard_cut_style`）。
- **Alt E — 新建 `anchor_dlq` 表跟踪失败重试**。Rejected：失败状态已由 `enriched_events.capture_method='unavailable'` + `capture_reason` 表达；多张表是把同一状态拆三个地方维护。如要重试，加 `next_retry_at_ms` 列到 `enriched_events` 即可。
- **Alt F — 引入 Kafka + Materialize / RisingWave 做真正 streaming join**。Rejected：runtime 复杂度跳升一档；现 scale 850k events / 90 天，Postgres + LISTEN/NOTIFY 物理够用；引入新运行时违反 KISS。
- **Alt G — 引入 TimescaleDB hypertable 给 `market_ticks`**。Deferred：上线后再评。30 天 retention + 日分区在原生 PG 上对 ~10k ticks/day 完全够用；写入量超过 100k ticks/day 时再考虑 Timescale。

## Boundaries

| Class | Behaviour |
|---|---|
| Always | 每条 resolved `(event, token)` 都有一行 `enriched_events`；ingest 路径不被 provider 失败阻塞；`market_ticks` 仅 append-only；`enriched_events` 仅 INSERT；`capture_method` 必填且与 `tick_id` NULL 状态一致 |
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
