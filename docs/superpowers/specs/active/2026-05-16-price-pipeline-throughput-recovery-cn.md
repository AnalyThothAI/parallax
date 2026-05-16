# Spec — 价格 pipeline 吞吐恢复（worker 限速与全链路 backlog 修复）

**Status**: Draft, awaiting review
**Date**: 2026-05-16
**Owner**: Claude with Qinghuan
**Scope**: 在 `2026-05-15-event-anchor-capture-redesign-cn.md` 已落地的"三层 capture lane + `market_ticks` 单一右手边状态 + `enriched_events` 单一 join 投影"架构之内，修复每条 lane 实际未兑现契约的执行层 bug。**不引入新表、不改架构方向、不违反写读分离、不违反 Kappa/CQRS**。
**Depends on**:
  - `docs/superpowers/specs/active/2026-05-15-event-anchor-capture-redesign-cn.md`（三层 capture lane 与 enriched_events 投影定义；本 spec 假定该 spec 已实施）
  - `docs/superpowers/specs/active/2026-05-15-worker-runtime-platform-cn.md`（`WorkerBase` / `DBPoolBundle` / `workers.yaml` 已就位）
**Related**:
  - `docs/ARCHITECTURE.md`（10 条 Kappa/CQRS 不变量）
  - `docs/RELIABILITY.md`（wake-hint 非 truth、capture lane 划分、one writer per read model）
  - `docs/WORKERS.md`（cross-domain worker 清单）
  - `src/gmgn_twitter_intel/domains/asset_market/ARCHITECTURE.md`
  - 直接落地代码区：`src/gmgn_twitter_intel/domains/asset_market/{runtime,services,repositories}/`、`src/gmgn_twitter_intel/integrations/okx/dex_ws_client.py`、`src/gmgn_twitter_intel/app/runtime/bootstrap.py`、`src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`、`src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`

## 一句话结论

**架构是对的，每条 lane 的实现都没兑现契约。** 先校准 provider 角色（验证自 `providers_wiring.py:464-655`）：**Tier 1 WS 的唯一价格流实现是 OKX DEX WS**（`OkxDexWebSocketMarketProvider`，无 fallback）；**Tier 2/3 的 DEX quote 走 `FallbackDexQuoteProvider(primary=GMGN OpenAPI REST, fallback=OKX DEX REST)`**；**CEX quote 走 OKX CEX REST，不是 CEX WS**。GMGN DirectWS 已接入，但它在 ingestion 域处理推特帧，不是价格 provider；当前代码里没有 GMGN price WS provider、没有 `stream_price_info` 形式的 GMGN 价格流协议，也没有把 GMGN WS 接到 `market_ticks`。在这个真实拓扑下：Tier 1 因为 StreamWorker 每 5 秒重建 OKX DEX WS 连接并重复 login/subscribe，持续触发 OKX WS 限速/断连风险；Tier 2 PollWorker 同步串行 + 没轮询游标，950 个 token 里只有 10% 真的被轮询到（实测 24h: GMGN primary 命中 8%、OKX DEX/CEX REST 承担绝大多数写入——GMGN 在长尾 DEX token 上不返价）；Tier 3 内联 capture 在 collector frame 处理路径上同步等 GMGN OpenAPI（实测占 80%）或 OKX REST，timeout 15s，是单点故障；TokenCaptureTier 写 tier 时不把不在 batch 里的旧 tier1/2 行 demote，留下永远不会被订阅的"僵尸 tier1"，且 CEX target 被分到 tier1 时也会被 DEX-only StreamWorker 跳过。本 spec 在不动数据模型、不动写读分离、不动 single writer per read model 不变量的前提下，给每条 lane 做最小化执行修复 + 一次 schema 放宽（`enriched_events` 允许从 `unavailable → tier3_inline` 的 capture_method 升级），让架构契约真正闭合。

## Background

### 业务诉求

每条 token-bearing tweet → ① 在事件时刻获得锚价（tick_lag ≤ 60s）；② Token Radar / Pulse Lab 在帖子发出后 5 分钟内能拿到该 token 的近实时价格（live 或 fresh）做决策；③ 任何一条 capture lane 异常都不能让 ingest pipeline 整体阻塞。

### 当前架构（2026-05-15 spec 落地后的状态）

```
ingestion (collector + snapshot gate)
  ← GMGN public WS (DirectGmgnWebSocketClient) ── 推特帧来源；与价格无关
   → evidence (events, token_intents, token_intent_resolutions)        【FACT，append-only】
   → asset_market 三层 capture lane:
       Tier 1: MarketTickStreamWorker(WS)  → market_ticks(tier1_ws)    【FACT】
         └ provider: OKX DEX WS (OkxDexWebSocketMarketProvider) ── 唯一实现，无 fallback
       Tier 2: MarketTickPollWorker(REST)  → market_ticks(tier2_poll)  【FACT】
         └ provider: FallbackDexQuoteProvider(primary=GMGN OpenAPI, fallback=OKX DEX REST)
                    + OKX CEX REST (for cex_symbol targets)
       Tier 3: IngestService.capture_for_event (inline)
                                           → market_ticks(tier3_inline)【FACT】
                                           → enriched_events           【PROJECTION】
        └ provider: 同 Tier 2 (DEX: GMGN OpenAPI primary + OKX DEX REST fallback; CEX: OKX CEX REST)
       TokenCaptureTierWorker → token_capture_tier                     【PROJECTION】
   → token_intel.TokenRadarProjectionWorker → token_radar_rows         【PROJECTION】
       (joins enriched_events + market_ticks 拿事件锚价 + 最新价)
   → pulse_lab.PulseCandidateWorker → pulse_candidates                 【PROJECTION】

LivePriceGateway(WorkerBase) ──── /ws fan-out:
                                  DEX 用 OKX DEX WS in-process latest cache
                                  CEX 用 OKX CEX REST polling 后由本服务 /ws 推送
                                  不写 fact (符合不变量 #8)
```

不变量复述（`docs/ARCHITECTURE.md`）：

- **#1 Facts-first**：`events`、`market_ticks`、`enriched_events` 等是 fact 表
- **#2 Append-only market ticks**：`market_ticks` 不可 UPDATE，trigger `forbid_market_fact_update` 强制（`platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py:146-152`）
- **#3 Event projections committed with events**：内联 Tier 3 写 ticks + enriched_events 与 `events` 同事务
- **#5 One writer per read model**：`token_capture_tier` 只由 `TokenCaptureTierWorker` 写
- **#6 Wake 是 hint 不是 truth**：`market_tick_written` 只唤醒，不保证投递
- **#8 Capture lanes own market persistence**：`LivePriceGateway` 只缓存 + WS fan-out 不写 fact

### 关键代码点

| 关注点 | file:line |
|---|---|
| Provider 拼装总入口（`AssetMarketProviders`） | `src/gmgn_twitter_intel/app/runtime/providers_wiring.py:466-492` |
| `FallbackDexQuoteProvider`（GMGN primary + OKX fallback） | `src/gmgn_twitter_intel/app/runtime/providers_wiring.py:252-272` |
| `GmgnDexMarketProvider`（GMGN OpenAPI REST quote） | `src/gmgn_twitter_intel/app/runtime/providers_wiring.py:176-209` |
| OKX DEX WS 客户端（tier1 唯一实现） | `src/gmgn_twitter_intel/integrations/okx/dex_ws_client.py:48-106` |
| OKX DEX REST 客户端（tier2 fallback、tier3 fallback） | `src/gmgn_twitter_intel/integrations/okx/dex_client.py` |
| OKX CEX REST 客户端（CEX quote；无 CEX WS 接入） | `src/gmgn_twitter_intel/integrations/okx/cex_client.py:14-72` |
| GMGN public WS（推特帧 ingestion，**与价格无关**） | `src/gmgn_twitter_intel/integrations/gmgn/direct_ws.py` |
| StreamWorker run loop（注入 OKX WS） | `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_stream_worker.py:71-149` |
| PollWorker run loop（注入 fallback chain） | `src/gmgn_twitter_intel/domains/asset_market/runtime/market_tick_poll_worker.py:64-211` |
| TokenCaptureTierWorker | `src/gmgn_twitter_intel/domains/asset_market/runtime/token_capture_tier_worker.py:77-163` |
| capture tier upsert SQL | `src/gmgn_twitter_intel/domains/asset_market/repositories/token_capture_tier_repository.py:21-53` |
| 内联 capture 入口 | `src/gmgn_twitter_intel/app/runtime/bootstrap.py:448-492`（事务外 capture，事务内写 enriched_events） |
| 内联 capture 服务 | `src/gmgn_twitter_intel/domains/asset_market/services/event_market_capture.py:51-242` |
| collector → ingest 串行 await | `src/gmgn_twitter_intel/domains/ingestion/runtime/collector_service.py:195` |
| enriched_events PK + trigger | `platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py:94-168` |
| enriched_events INSERT ON CONFLICT DO NOTHING | `src/gmgn_twitter_intel/domains/asset_market/repositories/enriched_event_repository.py:41` |
| RadarProjection 串行循环 | `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py:106-140` |
| RadarProjection source 全量扫 | `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py:199-231` |
| RadarProjection truncate+insert | `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py:52-90` |
| factor_snapshot.market.readiness.latest_status 计算 | `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:745-763` |
| `market_json` 硬写空 | `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:453` |

### Provider 边界说明：为什么不用 GMGN WS 查价格

当前不是"有 GMGN price WS 但暂时不用"，而是**本仓库没有可用/已接入的 GMGN 价格 WS capability**：

- `DirectGmgnWebSocketClient` 只由 `_gmgn_upstream_factory(...)` 构造成 ingestion upstream，用来接 GMGN anonymous public stream 里的推特帧。
- `AssetMarketProviders.dex_quote_market` 中的 GMGN 价格能力来自 `GmgnDexMarketProvider(GmgnOpenApiClient)`，即 GMGN OpenAPI REST quote/profile/candle。
- `AssetMarketProviders.stream_dex_market` 只来自 `_okx_dex_ws_market(...)`，即 OKX DEX WS；没有 GMGN adapter 实现 `DexMarketStreamProvider.stream_price_info(...)`。
- 官方 `GMGNAI/gmgn-skills` 仓库（commit `123bdba`, 2026-05-14, `gmgn-cli` 1.3.0）也把公开能力定义为 **GMGN OpenAPI CLI**：`package.json` description 是 "GMGN OpenAPI CLI"，依赖只有 `undici`/`socks` 等 HTTP/代理栈；`src/config.ts` 固定 host 为 `https://openapi.gmgn.ai`；`OpenApiClient.ts` 里的 token/market/trade 能力均经 `normalRequest` / `criticalRequest` 到 `/v1/...` endpoint，并最终 `fetch(...)`。仓库检索 `websocket|wss://|ws://|EventSource|SSE` 未发现价格 WS 客户端或价格 WS endpoint。
- 因此本 spec 里的事实表述应为：**GMGN DirectWS 已接入但与价格无关；GMGN 价格当前只走 OpenAPI REST；若 GMGN 有未公开或后续新增的价格 WS，需要先拿到 vendor contract 并新增 adapter，不能把现有 DirectWS 当价格源复用。**

### Provider 决策说明：为什么 CEX 暂不接 OKX CEX WS

OKX CEX 确实有公开 market-data WebSocket（如 `tickers` public channel），但本 spec 不把它纳入修复范围，原因是：

- **当前代码没有 CEX stream contract**：`CexMarketProvider` 只有 `tickers(...)` / `ticker(...)` / `candles(...)`；`MarketCapability` 只有 `QUOTE_CEX`，没有 `STREAM_CEX`；`DexMarketStreamProvider.stream_price_info(...)` 明确是 DEX target。
- **当前 CEX 实际需求是小集合、低频补价**：实测 `token_capture_tier` 中 `cex_symbol` 为 tier1=31、tier2=80；24h `okx_cex_rest` 覆盖 102 个 distinct CEX targets。这个规模下，修 `cex_symbol` 不要进 tier1 + tier2 poll rotation，比新增一套 WS 生命周期、订阅差分、重连、限速、source_provider schema 更 KISS。
- **OKX CEX WS 不是免费替换 REST**：官方 OKX WS 需要长连接、ping/pong、订阅集合管理，并受 `login + subscribe + unsubscribe <= 480/h/connection`、channel 连接数等约束。当前 spec 的核心 bug 正是 DEX WS 被短周期重连/重订阅打爆；在 CEX lane 复制同类复杂度，会扩大 blast radius。
- **事实落点**：CEX price 目前应明确保留为 OKX CEX REST poll/inline quote。若未来 CEX target 数量上升到 REST 成为瓶颈、或产品真的需要 sub-second CEX UI，再单独设计 `CexMarketStreamProvider` + `okx_cex_ws` source_provider + 独立 worker lane，不在本次吞吐恢复 spec 里混入。

## 数据现状（实测 2026-05-16，docker compose Postgres）

### 端到端漏斗（1h）

| 阶段 | 行数（1h） | 留存率 |
|---|---:|---:|
| `events` 写入（含 watched basic + token channel） | 3,098 | — |
| 含 token 抽取的 events | 445 | 14.4% |
| `token_intents` | 555 | — |
| `enriched_events`（24h 累计 2,061）按 `capture_method` 分： | | |
| └─ `tier3_inline` | 1,723 | 83.6% |
| └─ `tier1_ws`（复用现有 tier1 tick） | 210 | 10.2% |
| └─ `tier2_poll` | 28 | 1.4% |
| └─ `unavailable` | 100 | 4.9% |

→ **架构定义里 Tier 1 stream 应该把"最近 60s 内的 tick 让 inline 复用"，但只有 10% 命中**。说明 Tier 1 在锚定时几乎不贡献。

### Tier 实际填充 vs cap

| Tier | cap | 实际行 | 1h 内有 ws/poll tick 的 token 数 | 覆盖率 |
|---|---:|---:|---:|---:|
| Tier 1（`ws_limit=100`） | 100 | **149** | 101（tier1_ws） | **68%** |
| Tier 2（`poll_limit=500`） | 500 | **950** | 92（tier2_poll） | **10%** |
| Tier 2 24h 内从未被 poll 的 | — | — | 422 | **44% 完全没动过** |

`token_capture_tier` 表里有 149 个 tier=1 行（>cap 100）、950 个 tier=2 行（>cap 500），但 `MarketTickStreamWorker.subscription_limit=100` 是 stream 实际订阅上限——**49 个 tier1 token 永远不会被 WS 订阅**。

### Worker overrun

| Worker | interval | run_once p99 | overrun |
|---|---:|---:|---:|
| `market_tick_stream` | 5s | 14.7s | **3×** |
| `market_tick_poll` | 15s | 105.8s | **7×** |
| `resolution_refresh` | 30s | 120.3s | **4×** |
| `asset_profile_refresh` | 60s | 54.3s + ERRORED (statement_timeout) | — |
| `token_radar_projection` | 10s | 89.7s | **9×** |
| `pulse_candidate` | 60s | 194.1s | **3.2×** |

→ **整条下游 projection chain 都不在 SLA 内**。`/readyz` 当前 `ok=false`，原因是 `asset_profile_refresh` QueryCanceled。

### OKX DEX WS 抖动

近 10 分钟从 docker logs 统计：

| 事件 | 次数 |
|---|---:|
| `state=disconnected` | **71** |
| `state=streaming` | 43 |

Tier1 WS tick 间隙（30 分钟样本）：

| 分位 | 值 |
|---|---:|
| p50 gap | 0.03s（burst） |
| p95 gap | 11.2s |
| max gap | 68.8s |
| 间隙 > 5s 的次数 | 122 |
| 间隙 > 30s 的次数 | 4 |

模式：**reconnect 后短暂 burst 几秒、被 OKX 切断、退避重连、再 burst**。

### Token Radar 价格充填实测

`token_radar_rows` 1h 内 1h:all = 6,212 行：

| 字段 | 充填率 |
|---|---:|
| `factor_snapshot_json -> 'market'` 存在 | **100%** |
| `factor_snapshot_json -> 'market' -> 'decision_latest' ? 'price_usd'` | **74.4%** |
| `factor_snapshot_json -> 'market' -> 'readiness' ->> 'latest_status'` 存在 | **100%** |
| `factor_snapshot_json -> 'data_health' ->> 'market'` 为健康标量（`ready`/`partial`/`missing`） | **100%** |
| `market_json IS '{}'` | **100%**（死字段） |

→ 三件事：① `market_json` 列是**死字段**（下游全部从 `factor_snapshot_json.market` 读，CLI 诊断在 `app/surfaces/cli/main.py:1251` 甚至把 `market_json` 非空标为"legacy violation"）；② `decision_latest.price_usd` 有 74% 充填；③ `latest_status` 的正确 contract 是 `factor_snapshot.market.readiness.latest_status`，不是 `data_health.market.latest_status`。`data_health.market` 按 contract 是标量健康枚举（`ready`/`partial`/`missing`），不能被改成对象。

### Radar 滞后

`token_radar_rows.computed_at_ms` 最新一批的滞后：

| window:scope | n | 滞后 |
|---|---:|---:|
| `5m:all` | 8,873 | 72s |
| `5m:matched` | 50 | **583s（≈10 min）** |
| `1h:all` | 5,407 | 115s |
| `1h:matched` | 95 | 106s |
| `4h:matched` | 655 | 78s |
| `24h:all` | 8,800 | 174s |
| `24h:matched` | 2,192 | 122s |

→ `5m:matched` 是 pulse 决策最依赖的视图（watched-handle 触发），滞后 10 分钟——**实时性已经退化**。

## Problem（按根因分组，事实证据 + file:line）

### P1：StreamWorker 每 5s 重建 WS → 触发 OKX 480/h 配额 → 抖动

**事实**：
- OKX V5 文档（DEX/CEX WS 共享同套规则）公开限制：`subscribe + unsubscribe + login ≤ 480/h/连接`（调研报告"OKX DEX WebSocket"段）；idle 30s 自动断连。
- `MarketTickStreamWorker.run_once()`（`market_tick_stream_worker.py:71-101, 108-140`）：每 5 秒一个 cycle，每个 cycle 调 `_stream_and_persist_ticks` 新建 iterator → 调 `provider.stream_price_info(targets)` → 内部 `websockets.connect(...)` 新开 WS → auth → subscribe 100 个 args。
- 算次数：若按 WebSocket request 计，`3600/5 × (login + subscribe)` 已约 1,440 ops/h，超过 OKX 480/h/连接；若 provider 按 subscribe args 计，则上界接近 `3600/5 × (1 login + 100 subscribe args) ≈ 72,720 arg-ops/h`。无论按哪种计数，**每 cycle 重连/重订阅都违反 WS 长连接语义**。
- 间接证据：tick 间隙 p50=30ms（burst） vs max=68s（silent）；近 10min `disconnected=71` 次。

**为什么是设计层面**：`run_once()` 被理解成"每 5 秒重做一轮"——这是 REST polling 的语义，错误移植到 WebSocket 长连接客户端上。WS 的工程语义是"一个长连接 + 增量 sub/unsub"，不是"周期性重建"。

### P2：tier1 容量 149 > sub_limit 100，且 CEX target 会被 DEX-only stream 跳过

**事实**：
- `token_capture_tier` 表实测 tier=1 行数 = 149。
- `MarketTickStreamWorker.subscription_limit = 100`（`market_tick_stream_worker.py` 默认 + `workers.yaml.market_tick_stream.subscription_limit=100`）。
- `TokenCaptureTierWorker.project_once()`（`token_capture_tier_worker.py:77-163`）每个 cycle 取 `active_live_market_targets(limit=batch_size=500)`，按 score 排序，**只对前 500 个写 tier 1/2/3**；**不在 batch 内的旧 tier1/2 行不会被 demote**。
- 历史上某段时间 batch_size 配置过大（或 tier worker 跑了多次 + 不同时间不同候选），导致 149 个行被打过 tier1 后留在表里。
- `MarketTickStreamWorker._stream_targets()` 只接受 `target_type='chain_token'`；如果 `TokenCaptureTierWorker` 把 `cex_symbol` 分到 tier1，这些 CEX target 会被 stream worker 计为 skipped，且不会被 tier2 poll worker 轮询。

**下游后果**：
- StreamWorker 读 `list_by_tier(1, limit=100)`（`market_tick_stream_worker.py:103-106`），只订前 100。剩 49 个 tier1 token 既不被 stream 也不被 poll（因为它们被标 tier=1 不会被 poll worker 取）。
- tier1 中的 `cex_symbol` 也属于"逻辑 tier1、物理未订阅"：CEX 价格当前只有 OKX CEX REST，没有 CEX WS lane，应进入 tier2 poll 或单独设计 CEX stream lane。
- 实测：tier1 1h 内 WS 覆盖率 68%，余下 32% 包含这 49 个"被遗忘的 tier1"。

### P3：PollWorker 同步串行 → tier2 覆盖率 10%

**事实**：
- `MarketTickPollWorker._run_once_sync()`（`market_tick_poll_worker.py:64-211`）每 15s 取 `batch_size=100` 个 tier2 target。
- CEX targets：`for target in targets: provider.ticker(inst_id=target)`（`:181-211`）——**完全串行**，sync httpx。
- DEX targets：`provider.token_quotes(requests)` 是 batch 调用（`:103-103`），但失败时 fallback 到单个串行（`:141-172`）。
- OKX REST 单次 timeout 15s。
- 单 cycle p99=105s vs interval=15s，**每 cycle overrun 7×**。
- 950 个 tier2 / 100 batch = 9.5 batches；如果每 batch 105s，**理论一轮全扫完要 16 分钟**。
- 没有 rotation cursor——下一 cycle 又从同一排序起点取（按 score DESC），所以 ranking 不变时永远卡在前 100 个。
- 实测：950 tier2 token / 1h 仅 92 个 (10%) 被 poll 到，**422 个 24h 内从未被 poll 过**。

### P4：内联 Tier 3 capture 在 collector frame 处理路径上同步等 GMGN/OKX

**事实**：
- `CollectorService.handle_frame()`（`collector_service.py:195`）：`ingested = await asyncio.to_thread(self.store.ingest_event, event, is_watched=is_watched)` —— frame 处理串行 await。
- `bootstrap.py:448-492` `_PooledIngestStore.ingest_event`：先写 events transaction，**释放 session**，**事务外**调 `event_market_capture.capture_for_event(...)`（`:479-486`），最后重新进 transaction 写 enriched_events / market_ticks（`:490-492`）。
- `event_market_capture.py:74-99`：先查 60s 内 existing tick（`tick_lookup.latest_at_or_before`），未命中**直接调 provider**（`providers.dex_quote_market.token_quotes` / `okx_cex.ticker`）。
- **provider 调用链**（`providers_wiring.py:252-272` `FallbackDexQuoteProvider`）：先调 GMGN OpenAPI（timeout=5s，`config.yaml.gmgn.timeout_seconds`），无返回则调 OKX DEX REST（timeout=15s，`config.yaml.providers.okx.timeout_seconds`）。最坏情况 5s + 15s = **20s 同步阻塞**。
- 实测 capture_method 分布（24h，n=2061）：
  - `tier3_inline` 1723 条中：`inline_quote` 1254 + `inline_ticker` 234（共 86% 主动调 provider），`fresh_tick` 235（14% 复用 60s 内 tick）
  - 内联实际写入的 `source_provider`：**`gmgn_dex_quote` 1453 (84%)**、`okx_cex_rest` 282 (16%)、`okx_dex_rest` 88 (5%)
- 实测 1h 内 token-event = 445 / 60min = 7.4/min。每个事件最坏 20s timeout。**任一 provider 同时降级时，collector loop 7.4 × 20s / 60s = 247% 用于等待——pipeline 完全停摆**。

**当前没爆只是因为**：
1. token-bearing event 占 14%；
2. GMGN OpenAPI 在 short-tail 上命中率 80%+，平均响应 < 1s；
3. OKX DEX REST 作为 fallback 大部分时候健康；
4. 三者都同时挂的概率低。

**核心风险**：**真正的阻塞点是 GMGN OpenAPI，不是 OKX**（实测内联 84% 走 GMGN）。GMGN 一旦抖动，inline 落到 OKX 5+15s 双 timeout，**比 OKX 单独挂还慢一倍**。

### P5：enriched_events trigger + ON CONFLICT DO NOTHING 让 capture 失败不可重试

**事实**：
- enriched_events PK(`event_id`, `intent_id`)（`20260515_0046_event_anchor_capture_redesign.py:108`）。
- Trigger `forbid_enriched_events_update`（`:164-168`）拒绝**任何** UPDATE 操作——`RAISE EXCEPTION 'market facts are append-only'`。
- INSERT SQL（`enriched_event_repository.py:41`）：`ON CONFLICT(event_id, intent_id) DO NOTHING`。
- 当前流程：capture 失败 → 写 `capture_method='unavailable', tick_id=NULL` 一条 enriched_events。**之后这条行再也不能被升级**（UPDATE 被 trigger 拒，INSERT 被 DO NOTHING 忽略）。
- 实测 unavailable 100 条 / 24h，5% 永久缺锚价。

**含义**：本 spec 要做的"内联同步调 OKX → 异步 backfill"改造，**必须先放宽 trigger**，否则 backfill worker 改不了 unavailable 行。

### P6：TokenRadarProjection selected work_items 串行 + source 全量扫描

**事实**：
- `token_radar_projection_worker.py:106-140` 主循环 `for window, scope in work_items: rebuild(...)` 串行。
- 当前 worker 常态不是每轮固定跑满 8 个 `(window, scope)`；它先跑 `hot_windows × scopes`，再用 cursor 选一个 background `(window, scope)`。当 coverage 缺失时会把 missing items 加入 work_items 补齐。
- `token_radar_projection.py` 调 `TokenRadarSourceQuery.source_rows(since_ms=analysis_since_ms, ...)` ——`analysis_since_ms` 对 5m 窗口约 `now - 2h`（lookback 2 小时 = 该 window 长度的 24×）。
- 该 SQL（`token_radar_source_query.py:20-232`）是巨型 LEFT JOIN：`events + token_intents + token_intent_resolutions + enriched_events + market_ticks (event_price_tick) + market_ticks (latest_price_tick) + market_ticks (first_price_tick) + asset_identity_current + ...`，**没有 token id 过滤参数**——wake-in 的 `market_tick_written {target_id}` 信号无法降维。
- `repository.replace_rows`（`token_radar_repository.py:52-90`）：先 DELETE 全部，再 INSERT 全部——**truncate + insert 语义，rank 基于本轮全集**。
- `pulse_candidate` 读 `latest_rows`（`token_radar_repository.py:105-118`）：`SELECT * WHERE computed_at_ms = MAX(computed_at_ms)`——**只看最新一批**。

**关键约束**（决定优化方案）：
- rank 是全局排序——**不能简单"只刷 dirty token，其他不动"**，否则 rank 会乱、pulse 会因 `computed_at_ms` 不一致漏掉 token。
- 所以可行优化空间：**保持 truncate+insert 语义，但 selected work_items 可并发跑，并把 hot / cold window 的 cadence 显式分层**。

### P7（撤销误报）：`latest_status` 路径写在 `market.readiness`，不是 `data_health.market`

**事实**：
- `token_radar_projection.py:745-763` 定义 `_latest_status(decision_latest, now_ms)`：根据 `decision_latest.observed_at_ms` 计算 `live`/`fresh`/`stale`。
- 该函数返回值被打包进 `_market_readiness(..., now_ms=now_ms)` 的 `latest_status` 字段，并挂在 `factor_snapshot.market.readiness.latest_status`。
- `factor_snapshot_contract.py` 明确要求 `market.readiness` 包含 `anchor_status`、`latest_status`、`dex_floor_status`、`missing_fields`、`stale_fields`。
- `factor_snapshot.data_health.market` 是标量健康枚举（`ready`/`partial`/`missing`），不是对象；因此 `factor_snapshot.data_health.market.latest_status` 为 NULL/不存在是**正确行为**，不是 bug。

**结论**：本 spec 不应包含"修 data_health.market.latest_status"的实现项。正确的 guard 是验证 `factor_snapshot.market.readiness.latest_status` 充填率为 100%，并确保消费方从 `market.readiness.latest_status` 读价格新鲜度。

## First Principles

### 业务真实需要的价格层次（4 层）

| 层 | 集合定义 | 时效要求 | 当前架构对应 | 真实容量需求 |
|---|---|---:|---|---:|
| A 锚定 | 当下被 mention 的 token，TTL = 事件后 60s | < 5s | tier3 inline + 复用 tier1/2 | 7.5 token-event/min → 平均同时活跃 < 50 |
| B 热集 | rank top N 且 5min 内被讨论 | < 10s | Tier 1 WS | **真实 < 50**，不是 100 |
| C 滚动 | 24h 内有 attention 的 | 1–5 min | Tier 2 poll | 几百 |
| D 冷尾 | 24h 外 | 按需 | 不订阅 | 0 |

→ 当前架构把 B + C 都塞 WS + REST 双轨，物理上跑不动。**真实 hot set 远小于 100**——成熟系统（Jupiter "top 200 提前 revalidate"、Birdeye "100 sub/连接"、Helius "10min idle"）都默认 hot set 是数十到百级，不是上千。

### 不能违反的架构思想

1. **写读分离不动**：API 用 `api_pool`，worker 用 `worker_pool`，wake 用 `wake_pool`。本 spec 所有改动只在 worker 侧。
2. **Kappa/CQRS 不动**：`market_ticks` / `events` / `enriched_events` 是 fact 或 from-fact projection；`token_capture_tier` / `token_radar_rows` / `pulse_candidates` 是 rebuildable read model。
3. **One writer per read model 不动**：`token_capture_tier` 仍只由 `TokenCaptureTierWorker` 写；新增 backfill worker **只写 market_ticks（fact 多入口允许，UNIQUE 自然去重）+ 升级 enriched_events**——但仍由 `enriched_events` 的现有"capture write path"语义控制。
4. **Wake hint 非 truth 不动**：backfill worker 不依赖 wake 信号正确性，按 interval 扫 unavailable 集合。
5. **三层 capture lane 划分不动**：tier1/2/3 各自的职责保留，只把每条 lane 的实现做对。
6. **append-only invariant 不动**：market_ticks 不可 UPDATE；enriched_events 允许从 `unavailable → tier3_inline` 的**有限**升级（schema 改动见 §Target Architecture）。

### 成熟系统的 4 条普适规律（调研 CoinGecko / DEXScreener / Birdeye / Helius / Jupiter / OKX / Pyth）

1. **客户端按数量分层，后端按热度分层**——Jupiter top 200 提前 revalidate；本仓库目前把"分量层"和"分热层"混在 token_capture_tier 一张表里，没问题，但 worker 没按热度差异化处理。
2. **WS 是奢侈品**——只有当客户端**已知精确订阅集合 + 真要 sub-second** 时 WS 才划算；冷尾走 REST batch。
3. **TTL 15s 是甜区**——Jupiter 15s、CoinGecko 30s、Birdeye 100 addr/conn 推送。没人在万级 token 维度做亚秒级。
4. **WS 强制 idle 断连 + subscribe 限速**——OKX 30s idle + 480/h sub；客户端必须自实现 keep-alive + 节流 + **持久连接**，不能每周期重建。

## Goals（每条可证伪，给 SQL/命令）

- **G1** OKX DEX WS `login + subscribe + unsubscribe` request ops/h ≤ 100，且 subscribe args churn 只来自 tier 集合实际变化（当前实现每 5s 重连/重订阅，按 request 计约 1,440 ops/h，按 args 计上界约 72,720 arg-ops/h）。验证：worker 日志 grep `"WS subscribe op"` + 小时桶计数。
- **G2** 在 last 1h 内，tier=1 token（实际订阅集合 ≤ ws_limit）中 ≥ 95% 至少有 1 条 `market_ticks(source_tier='tier1_ws')`（当前 68%）。
- **G3** 在 last 1h 内，tier=2 token 中 ≥ 80% 至少有 1 条 `market_ticks(source_tier='tier2_poll')`（当前 10%）。
- **G4** `enriched_events.tick_lag_ms` p95 ≤ 5,000 ms、p99 ≤ 30,000 ms（当前 p95=37s, p99=56s）。
- **G5** Collector frame 处理路径不受 provider IO 阻塞：手动让 GMGN OpenAPI **和** OKX REST 同时 timeout 15s（chaos test），新到帖子的 `events.created_at_ms - frame_received_at_ms` p95 ≤ 200 ms（验证两个 quote provider 任一/双挂都不卡 ingest）。
- **G6** `factor_snapshot.market.readiness.latest_status ∈ {live, fresh, stale, missing}` 充填率 = 100%，且 `factor_snapshot.data_health.market` 保持标量健康枚举（`ready`/`partial`/`missing`）。
- **G7** `5m:matched` 的 `token_radar_rows` 滞后（now - max(computed_at_ms)） p95 ≤ 30 s（当前 583s）。
- **G8** `token_capture_tier` 表里 `tier=1` 行数 ≤ `ws_limit`，`tier=2` 行数 ≤ `poll_limit`，且 `tier=1 AND target_type='cex_symbol'` 行数 = 0（当前 149 / 950 over，且 CEX tier1=31）。
- **G9** `enriched_events.capture_method='unavailable'` 在 last 1h 的占比 ≤ 1%（当前 5%）。
- **G10** 跑 `make check-all` 0 退出 + 现有 `tests/test_src_domain_architecture.py` 全通过（架构不变量未被破坏）。

## Non-goals

- **N1** 不引入新表、不改 `market_ticks` / `events` schema。
- **N2** 不引入 Kafka / Redis / Materialize；继续在 Postgres + LISTEN/NOTIFY。
- **N3** 不换 provider（DEX streaming 仍 OKX DEX WS；DEX quote 仍 GMGN OpenAPI REST primary + OKX DEX REST fallback；CEX quote 仍 OKX CEX REST）。
- **N4** 不动 frontend；前端继续读 `factor_snapshot_json.market.*`。
- **N5** 不动 resolver；resolver dominance gap 已有独立 spec。
- **N6** 不删除 `market_json` 字段（Schema 改动尽量少；下游已绕过，留它不动）。
- **N7** 不引入 Worker 之间的"任务队列"；backfill worker 是普通 `WorkerBase` + 扫 DB pending 集合，符合现有模式。
- **N8** 不做"任意历史 timestamp 的精确报价"——provider 物理不支持。
- **N9** 不动 token_radar source_query 的 SQL 形状（incremental 改造在 P6 已论证不可行）。
- **N10** 不新增 GMGN price WS 或 OKX CEX WS；本 spec 只修已有 provider lane 的执行契约。GMGN price WS 目前无公开/已接入 capability，OKX CEX WS 需另起 `STREAM_CEX` 设计。

## Target Architecture

### 总览：保持三层 capture lane 不变，每条 lane 的实现做对

```
ingestion (collector)                                    ┌──────────────┐
   │ frame 1                                             │  market_ticks│ append-only fact
   ▼ await ingest_event()  (collector frame path 不再等 provider) └──────▲───────┘
evidence: events + intents + resolutions (TX1)                  │
   │                                                            │ tier1 / tier2 / tier3
   ▼ event_id, intent_id                                        │
asset_market.capture_for_event_lookup()                         │
   │ 只查 enriched_events.tier1_cached + 60s 内现有 market_ticks │
   │ 命中 → tick_id                                              │
   │ 未命中 → 写 enriched_events(capture_method='unavailable',  │
   │          capture_reason='pending_backfill')                │
   ▼ (TX2: market_ticks if hit + enriched_events)               │
                                                                │
新 worker: EventAnchorBackfillWorker (interval=2s, concurrency=5)│
   - 扫 enriched_events.capture_method='unavailable'             │
     AND created_at_ms > now - 300s                              │
   - async + Semaphore: 调 OKX DEX/CEX (1s timeout)              │
   - 命中 → INSERT market_ticks (UNIQUE 自然去重) +              │
     UPDATE enriched_events (capture_method, tick_id, ...)       │
     ←─ trigger 放行：unavailable → tier3_inline 的 column 子集 ─┘

MarketTickStreamWorker (改造)              MarketTickPollWorker (改造)
  - 持久 WS client (跨 cycle)                - asyncio.gather + Semaphore=10
  - 增量 sub/unsub (diff)                    - rotation cursor (offset 跨 cycle)
  - 25s ping watchdog                        - 单 cycle p99 < 5s
  - 1h subscribe ops < 100                     - tier2 全集 / 2min 覆盖一遍

TokenCaptureTierWorker (改造)
  - 单 SQL: WITH new_batch AS (SELECT top batch_size ...)
            UPSERT tiers from new_batch
            UPDATE tier=3 WHERE NOT IN new_batch AND tier IN (1,2)
    全部在 tier worker 的 advisory lock 内完成 → 原子

TokenRadarProjectionWorker (改造)
  - hot_windows (5m) interval 5s
  - cold_windows (1h/4h/24h) interval 60s 或 round-robin catch-up
  - selected (window, scope) 在 asyncio.gather 内并发 (各自一个 to_thread)
  - rank / truncate+insert 语义不变 → pulse 兼容
```

### 改动 1 — `MarketTickStreamWorker` 改长连接 + 增量 sub（修 P1, P2 关联）

**机制**：
- WS client 实例由 worker 持有（`self._ws_client`），跨 run_once 复用——`WorkerBase` 对 worker state 无生命周期假设（`worker_base.py:104-105, 207-211` 确认），合法。
- `OkxDexWebSocketMarketProvider` 新增方法：`async ensure_connected() -> None`、`async subscribe(targets: list) -> None`、`async unsubscribe(targets: list) -> None`、`async iter_ticks() -> AsyncIterator[Tick]`。**保留** `stream_price_info(targets)` 旧签名作为薄包装（一次性场景用），不破坏 Protocol。
- StreamWorker.run_once：
  1. `ensure_connected()`（首次或断连后重连，带指数退避）
  2. diff：`new_targets = list_by_tier(1, limit=subscription_limit)`；`to_sub = new - current_subscribed`、`to_unsub = current_subscribed - new`
  3. 只发增量：`await client.subscribe(to_sub)`、`await client.unsubscribe(to_unsub)`
  4. `async for tick in client.iter_ticks(): … insert + emit wake; deadline 到 break`
- 25s 主动 ping（OKX 30s idle 切断）；reconnect 时清空 `current_subscribed`，下个 cycle 全量重订。
- OKX 错误 frame 升 WARN（当前 INFO，看不见）。

**预算**：
- 平稳时 1h subscribe ops ≈ `connect 0–3 次 + sub/unsub 跟 tier 变化`，假设 tier1 集合每分钟变 5 个 token，1h = 600 个 ops + 偶发 reconnect 全订 ≤ 100 ops = **< 1000 ops/h**，远低于 OKX 480/h（即使单连接配额触顶，新建第二条连接前最多累 480）。
- 若仍触顶，**保守把 subscription_limit 调到 50**（这是 Birdeye 公开的单连接上限值，给 OKX buffer）；超出的 token 自动降级到 tier2 由 poll 覆盖。

**撞上的约束 + 化解**：
- ❓ run_once 超时 120s vs 长连接：在 deadline 内 yield ticks 到列表，break 后写 DB；`asyncio.shield(task)` 保护 task 不被 timeout 直接 cancel（`worker_base.py:192`）；aclose 时 cancel 触发 `websockets` context manager 自动关闭（`dex_ws_client.py:85`, `close_timeout=5`）。
- ❓ advisory lock：当前 stream worker 没设——单 ASGI worker 假设。本 spec **不变**；新增 lock 是过度。
- ❓ wake 信号：tick 插入后 emit `market_tick_written` 仍同函数同步触发（`market_tick_stream_worker.py:142-149` 写法保留），下游 RadarProjection 唤醒不变。

**对 token_radar 价格更新的传染面**：
- 正面：tier1 WS 覆盖从 68% → 95%，意味着 `factor_snapshot.market.decision_latest.price_usd` 在 hot token 上 fresh 比例上升，pulse `5m:matched` 决策的 `data_health.market` 从 `"partial"` → `"ready"` 的比例上升。
- 中性：`market_tick_written` 唤醒下游的频率会下降（因为不再每 5s burst 一次），但 RadarProjection 仍按 interval 兜底，不影响正确性。

**对帖子锚定的传染面**：
- 正面：tier1 持续 streaming 意味着内联 capture 的 60s `fresh_tick` 命中率上升（当前 14%）→ 即便 backfill worker 没改也减少 inline OKX 调用次数。

### 改动 2 — `TokenCaptureTierWorker` demote 旧 tier1/2 行 + CEX 不进 tier1（修 P2, G8）

**机制**：
先按 provider contract 做 KISS 分层：`chain_token` 才有资格进入 tier1 WS；`cex_symbol` 没有 CEX stream lane，最高只能进入 tier2 REST poll。然后单一 SQL upsert + 同事务里 `UPDATE tier=3 WHERE (target_type, target_id) NOT IN (new_batch) AND tier IN (1,2)`。在 `TokenCaptureTierWorker.project_once` 的现有 advisory_lock（`2026051503`）内完成，原子。

候选分层规则：

- `tier1`: score 排名前 `ws_limit` 的 `chain_token`。
- `tier2`: 未进入 tier1 的 `chain_token` + `cex_symbol`，按 score 排名前 `poll_limit`。
- `tier3`: 其余候选和所有不在新 batch 内的旧 tier1/2。

```sql
WITH new_batch AS (
  SELECT target_type, target_id, tier, reason, score, $now_ms AS updated_at_ms
  FROM unnest($tiers_input)  -- ranked candidates
)
INSERT INTO token_capture_tier (target_type, target_id, tier, reason, score, updated_at_ms)
SELECT * FROM new_batch
ON CONFLICT (target_type, target_id) DO UPDATE SET
  tier=EXCLUDED.tier, reason=EXCLUDED.reason, score=EXCLUDED.score,
  updated_at_ms=EXCLUDED.updated_at_ms;

UPDATE token_capture_tier SET tier=3, reason='inline_only', updated_at_ms=$now_ms
WHERE tier IN (1,2)
  AND (target_type, target_id) NOT IN (SELECT target_type, target_id FROM new_batch);
```

**撞上的约束 + 化解**：
- ❓ stream worker 读 tier=1 list 与 demote 之间的并发：PostgreSQL READ COMMITTED 下 stream worker 的 SELECT 是单语句快照——demote 的 UPDATE 单语句也是原子。stream worker 拿到的列表始终是某一时刻的一致集合，最坏情况是"刚被 demote 的 token 多订一个 cycle"，下个 cycle diff 时 unsub 即可。**无需引入锁协议**。
- ❓ poll worker 同理。

**对 token_radar 的传染面**：
- 直接：tier=1 集合稳定 ≤ 100，对应 stream 订阅集合也稳定。Token Radar 的 hot 集合不变。
- 间接：原 49 个僵尸 tier1 现在变成 tier3——它们的 capture 走 inline，由 backfill 兜底；factor_snapshot.market 仍有数据，只是不再有 WS streaming。

**对帖子锚定**：无直接影响。

### 改动 3 — `MarketTickPollWorker` async 并发 + rotation cursor（修 P3, G3）

**机制**：
- 把 sync httpx 客户端封装层换成 async（`GmgnOpenApiClient` / `OkxDexClient` / `OkxCexClient` 三个 sync httpx，或在 worker 侧用 `asyncio.to_thread + Semaphore` 包 sync 调用——后者侵入小，推荐先做后者）。
- 注意 `FallbackDexQuoteProvider.token_quotes`（`providers_wiring.py:259-272`）当前是**串行调 primary → 串行调 fallback**——并发化后 fallback 链仍保留，只是 gather 的内部每个 task 各自经过 GMGN→OKX 串行；fallback 语义不变。
- worker 内 `asyncio.Semaphore(10)`，CEX targets 用 `asyncio.gather`：

```python
sem = asyncio.Semaphore(10)
async def one(target):
    async with sem:
        return await asyncio.to_thread(provider.ticker, inst_id=target.instrument)
results = await asyncio.gather(*[one(t) for t in targets], return_exceptions=True)
```

- DEX targets：`provider.token_quotes(requests)` 已是 batch，保留；fallback 的串行重试改并发。
- **rotation cursor**：worker state 存 `self._poll_offset`，每 cycle 从 `tier2_targets[offset : offset+batch_size]` 取，offset 自增；wrap-around 到 0。
- 选 `batch_size=100` + `concurrency=10` → 单 cycle 期望 ~100×200ms/10 = 2s；950 token / 100 per cycle / (15s + 2s) ≈ 17 分钟一轮（如果 batch_size 不变）。**把 batch_size 调到 200**：950/200 = 5 cycles × 17s = 85s 全覆盖一遍。

**预算**：OKX REST 限速保守 10 RPS（公开无明确数字，参考 DEXScreener 60 rpm = 1 rps 估 OKX 应 ≥ 10）→ 10 并发 sustained 安全。

**撞上的约束 + 化解**：
- ❓ `worker_session` short-borrow 契约（worker spec G2/AC1）：DB session 不持有跨 provider IO。当前 `_run_once_sync` 已分开两个 session 块；并发改造保持"先取 targets → 释放 session → gather provider → 重新取 session 写"。
- ❓ tick INSERT 冲突：`(target_type, target_id, source_provider, observed_at_ms)` UNIQUE 自然去重（`market_tick_repository.py:72`）。并发 gather 不可能同 ms 写同一 tick，无 race。

**对 token_radar 的传染面**：
- 直接：tier2 token 在 1h 内有 tick 的比例从 10% → 80%+；`factor_snapshot.market` 的"非热门 token 仍有 price"覆盖率上升。
- pulse `1h:matched` / `24h:matched` 视图里中长尾 token 的 `decision_latest` 不再为空。

**对帖子锚定**：tier2 持续刷新意味着 inline capture 的 `fresh_tick` 复用窗口从仅 tier1 token 扩大到 tier2，命中率进一步上升。

### 改动 4 — 内联 Tier 3 → 异步 backfill worker（修 P4, P5, G4, G5, G9）

**机制**：
- `event_market_capture.capture_for_event()` 改造：**去掉同步 provider 调用**。只做：
  1. 查 60s 内 existing tick → 命中：返回 `EnrichedEventCapture(method=tier1_cached/tier2_cached, tick_id=...)`
  2. 未命中：返回 `EnrichedEventCapture(method='unavailable', reason='pending_backfill', tick_id=NULL)`
- ingest transaction 写 enriched_events 行（capture_method='unavailable' 时）。
- 新 worker `EventAnchorBackfillWorker(WorkerBase)`：
  - interval = 2s（hot path），advisory_lock_key 新分配
  - 每 cycle 扫 `enriched_events WHERE capture_method='unavailable' AND capture_reason='pending_backfill' AND created_at_ms > now - 300s`（5 分钟窗口；> 5min 视为永久失败，不再补）
  - 按 `target_type, target_id` 去重 batch，**async + Semaphore=5** 调 `providers.dex_quote_market.token_quotes(...)`（保留现有 FallbackDexQuoteProvider 链：GMGN primary → OKX fallback）
  - 命中：`INSERT market_ticks ... ON CONFLICT DO NOTHING`（UNIQUE 自然去重）+ `UPDATE enriched_events SET capture_method='tier3_inline', tick_id=..., tick_lag_ms=..., capture_reason='backfill_ok'`

**Schema 改动（唯一）**：放宽 `forbid_enriched_events_update` trigger：

```sql
CREATE OR REPLACE FUNCTION forbid_enriched_events_update()
RETURNS trigger AS $$
BEGIN
  -- 仅允许：unavailable → tier3_inline 的"锚定升级"
  IF OLD.capture_method = 'unavailable'
     AND NEW.capture_method = 'tier3_inline'
     AND OLD.tick_id IS NULL
     AND NEW.tick_id IS NOT NULL
     AND OLD.event_id = NEW.event_id
     AND OLD.intent_id = NEW.intent_id
     AND OLD.resolution_id = NEW.resolution_id
     AND OLD.target_type = NEW.target_type
     AND OLD.target_id = NEW.target_id
     AND OLD.t_event_ms = NEW.t_event_ms
     AND OLD.created_at_ms = NEW.created_at_ms  -- 只能补价，不能改时间
  THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'enriched_events: only unavailable→tier3_inline backfill allowed';
END;
$$ LANGUAGE plpgsql;
```

→ 这是 spec 唯一动 schema 的地方。所有其他字段保持 append-only；只放行严格的"补锚价"路径。**append-only invariant 在精神上不变**（事件的 identity 字段不可改），只是允许一次性补一个空 tick_id。

**撞上的约束 + 化解**：
- ❓ `market_ticks` 同样有 trigger 禁 UPDATE + UNIQUE 索引：backfill 写新 tick 时 INSERT ON CONFLICT DO NOTHING 即可——同一个 provider 在同一 ms 不会双写，UNIQUE 自然去重；append-only invariant **不动**。
- ❓ `enriched_events.market_ticks_fk`（`tick_id REFERENCES market_ticks(tick_id) ON DELETE RESTRICT`）：先 INSERT market_ticks 再 UPDATE enriched_events，FK 顺序正确。
- ❓ `one writer per read model`：enriched_events 在上一轮 spec 里就是 ingest 写入；本 spec 让 ingest 写"骨架"（unavailable）+ backfill 写"补丁"——**两阶段提交但唯一写路径仍是 capture pipeline**。同 `pulse_candidate_worker` 写 `pulse_candidates.decision_*` 然后再写 `pulse_agent_run_steps` 类似分阶段模式。在 `docs/RELIABILITY.md` 同 PR 内更新说明这条放宽。
- ❓ collector frame path 解阻塞：去掉 `provider.token_quotes` / `provider.ticker` 调用后，`ingest_event` 只剩 DB 写，p95 应该 < 50ms。

**对 token_radar 的传染面**：
- 直接：`enriched_events.capture_method='unavailable'` 从 5% → < 1%；TokenRadarSourceQuery JOIN enriched_events + market_ticks 拿事件锚价的命中率提升。
- `factor_snapshot.market.event_anchor.price_usd` 的非 NULL 率上升。
- **不影响 rank/排序逻辑**——补价是补现有 row 的 tick_id，不增减 source_rows 数量。

**对帖子锚定的传染面**：
- 这是核心改动。事件→锚定的 p95 lag：当前 37s（需要等 GMGN/OKX 同步返回 + ingest commit），改造后：
  - 命中现有 tick → < 1s
  - 未命中 → 写 unavailable，2s 内 backfill 调 GMGN（fallback OKX），5s 内补好 → p95 ~3s
- ingest commit 不依赖任何 quote provider 健康度，**GMGN/OKX 全挂时 ingest 仍正常推进**，只是 backfill 队列堆积；任一 provider 恢复后队列在 5 分钟 TTL 内自动消化。
- **特别的**：当前实测内联 84% 落在 GMGN OpenAPI 上（`gmgn_dex_quote`），这条改动把 GMGN 的同步依赖从 collector hot path 拆出来——这是相比"OKX 抖动修复"更高 ROI 的解耦点。

### 改动 5 — `TokenRadarProjection` selected work_items 并发 + 分窗口 interval（修 P6, G7）

**机制**：
- workers.yaml.token_radar_projection 配置改：
  ```yaml
  token_radar_projection:
    interval_seconds: 5             # 用于 hot_windows
    cold_interval_seconds: 60       # 新字段，用于非 hot_windows
    hot_windows: ["5m"]
    windows: ["5m", "1h", "4h", "24h"]
    scopes: ["all", "matched"]
  ```
- run_once：
  - 每个 cycle 决定要跑哪些 (window, scope)：hot_windows × scopes 每次都跑；cold_windows 按 cycle 计数 round-robin（每 12 cycle = 60s 跑一次），coverage missing 时补 missing items。
  - 把 selected 集合 `asyncio.gather(*[rebuild_one(w, s) for w, s in selected])`，每个 `rebuild_one` 内部仍 `await asyncio.to_thread(...)` 把 SQL 跑在线程池——DB IO bound，多个 to_thread 可真并发占 worker_pool 连接。
- worker_pool 已经分离（`DBPoolBundle`），不会饿死 API。

**保持不变（关键）**：
- `replace_rows` truncate+insert 不变 → rank 全局一致不变
- pulse 读 `MAX(computed_at_ms)` 语义不变（每个 (window, scope) 各自一个 max，独立时间戳，pulse `latest_rows` 按 window/scope 取 max 兼容）

**撞上的约束 + 化解**：
- ❓ worker_pool 连接数：现在 `pool_max_size=10`（`config.yaml`）。selected work_items 并发时每个 `to_thread` 可能占 1 条 worker connection。可能给其他 worker 留余地不够——**plan 阶段调 pool_max_size 到 16，或限制 projection 并发 = 4**。
- ❓ advisory_lock_key `2026051501` 单 writer 仍保留——并发的是同一进程内的 (window, scope) 多 task，不是多进程。

**对 token_radar 价格更新**：5m:matched 滞后从 583s → 期望 < 15s。Pulse 5m 决策的实时性恢复。

**对帖子锚定**：无直接影响（projection 不写锚价）。

### 改动 6（小） — `latest_status` contract guard（修正文档误报，守 G6）

**机制**：不改 runtime 字段路径。Plan 阶段只补/校准测试与诊断 SQL：`latest_status` 必须从 `factor_snapshot.market.readiness.latest_status` 读取；`factor_snapshot.data_health.market` 必须继续是标量健康枚举。若发现前端、Pulse、notification 读错 `data_health.market.latest_status`，应改消费方读取路径，而不是改 factor snapshot contract。

**对 token_radar 价格更新**：消费方（前端、pulse、notification）能正确判断价格新鲜度。

**对帖子锚定**：无。

## 影响面矩阵（改动 × 下游）

| 改动 | TokenRadar projection | Pulse Candidate | 帖子内联锚定 | enriched_events 查询 | Frontend /api | Notification rule | Watchlist timeline |
|---|---|---|---|---|---|---|---|
| 1 StreamWorker 长连接 | ↑ market 新鲜度 | ↑ live 比例 | ↑ tier1_cached 命中 | 无 SQL 变化 | ↑ 实时价 | 无 | 无 |
| 2 Tier demote | tier1 stream 集合稳定 | 无 | 无 | 无 | 无 | 无 | 无 |
| 3 PollWorker 并发 | ↑ 中长尾 market | ↑ 中长尾 decision_latest | ↑ tier2_cached 命中 | 无 | 无 | 无 | 无 |
| 4 内联 → backfill | ↑ event_anchor 命中 | ↑ event_anchor.price | ↑↑ 解阻塞 + 锚定 lag ↓ | tick_id 在 2s 内出现 vs 同步 | ↑ event_anchor | 无 | ↑ tick_id |
| 5 Radar 并发 | 5m:matched p95 583s→<30s | ↓ 决策延迟 | 无 | 无 | ↑ 5m 实时 | ↑ 实时 | 无 |
| 6 latest_status guard | contract 防回归 | gate 读 `market.readiness.latest_status` | 无 | 无 | 显示"价格已过期" | 读 `market.readiness.latest_status` | 无 |

## 实施顺序（按 ROI + 风险）

1. **改动 6（半小时）** — 修正文档误报 + 加 latest_status contract guard；零风险，避免 plan 误改 `data_health.market`。
2. **改动 2（半天）** — Tier demote；单 SQL，advisory lock 内原子，零并发风险。
3. **改动 1（2 天）** — StreamWorker 长连接；中风险（OKX 实际行为需观察），但是 OKX 抖动根因。
4. **改动 3（1 天）** — PollWorker 并发 + rotation；改动局部，受益面大。
5. **改动 5（1 天）** — Radar selected work_items 并发 + 分窗口 interval；改 worker 行为不改 SQL，pulse 兼容性已论证。
6. **改动 4（3 天，含 schema migration + backfill worker + 集成测试）** — 内联 → backfill；动 trigger，需要在 ARCHITECTURE.md / RELIABILITY.md 同步更新不变量措辞。**最后做**：前面 5 项做完后，inline 同步调 OKX 的命中率已经从 60% 升到 ≥ 90%，backfill 改造的紧迫性下降；但仍要做，因为它是单点故障保险。

**每一步独立 PR + 独立 verification**——本仓库的"硬切"风格（user memory `feedback_hard_cut_style`）允许单步直接生效，不需要 feature flag。

## 验证（每条 G 给可执行命令）

```bash
# G1: OKX subscribe ops/h
docker compose logs --since=1h app | grep -c "okx_dex_ws.subscribe"

# G2: tier1 1h ws 覆盖
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
WITH t1 AS (SELECT target_type, target_id FROM token_capture_tier WHERE tier=1),
ticks AS (SELECT DISTINCT target_type, target_id FROM market_ticks
          WHERE source_tier='tier1_ws'
            AND observed_at_ms > (EXTRACT(EPOCH FROM NOW())*1000)::bigint - 3600000)
SELECT ROUND(100.0 * (SELECT COUNT(*) FROM t1 JOIN ticks USING (target_type,target_id))
       / NULLIF((SELECT COUNT(*) FROM t1),0), 1) AS pct_covered;"

# G3: tier2 1h poll 覆盖 (同模式，source_tier='tier2_poll')

# G4: tick_lag_ms p95/p99
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY tick_lag_ms) AS p95,
       PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY tick_lag_ms) AS p99
FROM enriched_events
WHERE t_event_ms > (EXTRACT(EPOCH FROM NOW())*1000)::bigint - 3600000
  AND tick_lag_ms IS NOT NULL;"

# G5: collector 解阻塞 (chaos: 用 iptables / 暂停 OKX 连接，观察 events.created_at_ms - timestamp_ms p95)

# G6: market.readiness.latest_status 充填 + data_health.market 保持标量
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT factor_snapshot_json->'market'->'readiness'->>'latest_status' AS status, COUNT(*)
FROM token_radar_rows
WHERE computed_at_ms > (EXTRACT(EPOCH FROM NOW())*1000)::bigint - 3600000
GROUP BY 1;"

docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT jsonb_typeof(factor_snapshot_json->'data_health'->'market') AS data_health_market_type, COUNT(*)
FROM token_radar_rows
WHERE computed_at_ms > (EXTRACT(EPOCH FROM NOW())*1000)::bigint - 3600000
GROUP BY 1;"

# G7: 5m:matched 滞后
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT (EXTRACT(EPOCH FROM NOW())*1000)::bigint - MAX(computed_at_ms) AS lag_ms
FROM token_radar_rows WHERE \"window\"='5m' AND scope='matched';"

# G8: tier 容量
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT tier, COUNT(*) FROM token_capture_tier GROUP BY tier;"

# G9: unavailable 占比
docker compose exec -T postgres psql -U gmgn_app -d gmgn_twitter_intel -c "
SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE capture_method='unavailable')
       / NULLIF(COUNT(*),0), 2) AS pct_unavailable
FROM enriched_events
WHERE t_event_ms > (EXTRACT(EPOCH FROM NOW())*1000)::bigint - 3600000;"

# G10: architecture tests
make check-all
```

## Risks / Follow-ups

- **R1**：OKX DEX WS subscribe 增量协议（单 sub vs batch sub）需要实测——OKX 公开文档没明确说"已订阅集合是 idempotent 的 sub"还是"重复 sub 报错"。Plan 阶段先单元测试 + 灰度。
- **R2**：放宽 `forbid_enriched_events_update` trigger 后，必须在 `tests/unit/test_event_anchor_backfill.py`（新建）覆盖：① 允许的升级路径成功；② 任何 identity 字段不一致的 UPDATE 被 trigger 拒绝；③ tier3_inline → tier3_inline 二次升级被拒。
- **R3**：backfill worker 与 ingest 写"骨架"之间的 race（同一 (event,intent) 同时两个写者）：ingest 先 INSERT、backfill 后 UPDATE，PK 冲突 ON CONFLICT DO NOTHING 保证 ingest 永远赢；backfill 看到 unavailable 才补，看到 tier3_inline 跳过。
- **R4**：跨 spec 文档更新——`ARCHITECTURE.md` invariant #2 / #3 / RELIABILITY.md "Market tick capture lanes" 段需要小幅修订（"内联 Tier 3 在 transaction 内写 enriched_events" → "ingest 写 unavailable 骨架，backfill 在 5 分钟窗口内补"）。同 PR 内做。
- **R5**：跨 spec 协调——若 `2026-05-15-event-anchor-capture-redesign-cn.md` 仍在 active 状态，本 spec 应作为它的"实施修正"列在它的 Risks / Follow-ups 内。
- **R6**：worker_pool 大小：改动 5 并发 selected work_items 可能与其他 worker 抢连接。Plan 阶段加 `worker_pool_max_size` 监控，必要时调整 `config.yaml.storage.postgres.pool_max_size` 到 16 或限制 projection 并发。
- **R7**：本 spec 不解决 `asset_profile_refresh` 的 QueryCanceled——它是独立慢查询问题，单独 follow-up。
- **R8**：本 spec 不解决 resolver dominance gap（已有独立 spec），但 G3 提升 tier2 覆盖率会让 resolver refresh worker 的下游受益。
- **R9**：本 spec 改动后，`docs/TECH_DEBT.md` 应记入：①  `market_json` 死字段，未来一次性删除（不是本 spec 范围）；② OKX V6 DEX WS 官方文档缺失，订阅协议靠实测。

## 与"写读分离 / 核心架构思想"的对齐声明

- **写读分离**：所有改动只在 worker 侧（`worker_pool`），API/Frontend 侧零改动；查询读 `factor_snapshot_json.market` 的 SQL 行为不变；新增的 backfill worker 走 `worker_session` 短借模式，符合 worker spec 契约。
- **Kappa/CQRS**：`market_ticks` 仍是唯一右手边时序状态，三层 lane 都写它；`enriched_events` 仍是 (events × ticks) 投影，可重建性不变——backfill 补的是同一条 row 的 tick_id 引用，重建时按 events × market_ticks join 出的 tick_lag 与 backfill 写入值逐字段相等。
- **One writer per read model**：`token_capture_tier`、`token_radar_rows`、`pulse_candidates` 的 single writer 未变；`enriched_events` 不是 read model（是 fact projection 与 events 同 lane），保留 ingest + backfill 两阶段写入但属同一"capture pipeline"职责。
- **Wake hint 非 truth**：backfill worker 不依赖 wake 信号，按 interval 扫 DB——符合 invariant #6。
- **三层 capture lane**：tier1/2/3 划分不变；本 spec 让每条 lane 的实现兑现契约。
- **单 ASGI worker**：StreamWorker 长连接仍跑在唯一 ASGI 进程内；新 backfill worker 同进程。

—— **End of Spec** ——
