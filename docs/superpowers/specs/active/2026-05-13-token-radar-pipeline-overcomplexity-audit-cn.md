# Token Radar 链路过度复杂账本与目标架构 Spec

**Status**: Draft, awaiting review
**Date**: 2026-05-13
**Owner**: Claude with Qinghuan
**Scope**: 仅诊断 + 目标架构方向；具体 implementation plan 另起一篇
**Related**（按链路上下游排序）:

- `docs/superpowers/specs/active/2026-05-11-okx-dex-ws-market-stream-and-radar-recovery-cn.md`（runtime 实施，`dex_ws_enabled=false` 默认未启）
- `docs/superpowers/specs/active/2026-05-11-token-radar-anchor-live-worker-simplification-cn.md`（anchor/live 拆分已实施，留下双源未合并的尾巴）
- `docs/superpowers/specs/active/2026-05-11-token-radar-market-boundary-hard-cut-cn.md`（field-level 边界部分实施）
- `docs/superpowers/specs/active/2026-05-11-token-factor-engineering-hard-cut-cn.md`（social factor 重写已实施）
- `docs/superpowers/specs/active/2026-05-12-gmgn-dex-market-provider-split-cn.md`（GMGN DEX provider 拆分）
- `docs/superpowers/specs/active/2026-05-12-token-radar-hot-resolution-market-readiness-cn.md`（hot resolution 已实施）
- `docs/superpowers/specs/active/2026-05-12-symbol-only-resolution-gap-cn.md`（已实施）
- `docs/superpowers/specs/active/2026-05-12-market-data-pipeline-gap-cn.md`（采集层诊断）
- `docs/superpowers/specs/active/2026-05-12-signal-lab-pulse-agent-pipeline-current-state-cn.md`（消费层诊断）

## 一句话结论

> Token Radar 主干（10 worker + 4 层域划分 + provider 抽象）**结构是清的**，但当前把同一个事实流拆成了多套领域概念。§4 列出的 13 个绕路点不是 13 个独立问题，而是 **4 个抽象被重复建模**：(A) 市场观测散布成 anchor / live / projection / overlay 4 处；(B) Provider 能力散布成 4+ 个独立 port；(C) Worker 协调散布成 callback 链 + inline 调用 + poll loop 3 种模式；(D) IO 会话状态散布成 5 个隐式状态机。修订后的目标架构借鉴 **Kappa / CQRS**：raw facts 是唯一事实源，`token_radar_rows` / pulse / API / UI 都是可重建 read model；跨 worker 通信只是 wake hint，不是事实本身；本次实施采用 **single-plan hard cut，不保留旧 snapshot/schema 兼容代码**。

## 1. 背景与触发

### 1.1 这次审计的触发

- 2026-05-13 用户在 max effort 模式下连续 4 次提问"梳理 token radar 整体启动链路、worker、价格与数据同步机制、provider、前端组件，分析耦合与状态机"。
- 工作区里有 4 个 OKX/Live gateway 相关的修改（`dex_ws_client.py`、`live_price_gateway.py`、对应两个测试），明显是在补 `dex_ws_enabled=true` 上线前的最后两个洞。
- 近 4 天 main 落了 6 个 hard cut，但 `2026-05-12-signal-lab-pulse-agent-pipeline-current-state-cn.md` 的端到端症状（27/27 token_target 全是 trade_candidate）没有变化——说明上游采集已经修齐，下游消费 + 双源合并这一段还是堵的。

### 1.2 本 spec 的位置

| Spec | 视角 | 现状 |
|---|---|---|
| `2026-05-12-market-data-pipeline-gap` | 采集层（数据从哪儿来） | 已实施 |
| `2026-05-12-signal-lab-pulse-agent-pipeline-current-state` | 消费层（数据怎么用） | 已诊断，4 个 G 项待修 |
| **本 spec** | 全链路复杂度 + 目标架构 | 草稿 |

本 spec **不重复**那两份 spec 已经讲过的根因——本 spec 的视角是把"采集 + 消费 + UI"作为单条链路看，识别"链路上整体绕路的设计"，而不是某个具体函数的 NULL 处理。

## 2. 链路全景图（现状）

以下是 service 模式下，从一条 GMGN frame 到 UI 屏幕的真实路径。每个方框标 `(域 / 文件:行 / 触发方式)`。**★** 标记本 spec 关心的绕路点。

```
                               ┌─────────────────────────────────────────────────────┐
                               │            采集源（5 个，独立调度）                  │
                               └─────────────────────────────────────────────────────┘

  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
  │ GMGN Direct WS       │  │ GMGN OpenAPI         │  │ OKX REST search      │  │ OKX REST CEX ticker  │  │ OKX DEX WS           │
  │ integrations/gmgn    │  │ integrations/gmgn    │  │ integrations/okx     │  │ integrations/okx     │  │ integrations/okx     │
  │ /direct_ws.py        │  │ /openapi_client.py   │  │ /dex_client.py       │  │ /cex_client.py       │  │ /dex_ws_client.py    │
  │ (event stream)       │  │ (REST poll, anchor)  │  │ (resolution refresh) │  │ (anchor + live CEX)  │  │ (live DEX, ★ off)    │
  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘
             │                         │                         │                         │                         │
             │ frame                   │ dex_quote               │ search_tokens           │ ticker                  │ price-info
             ▼                         ▼                         ▼                         ▼                         ▼
  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
  │ CollectorService     │  │ AnchorPriceWorker    │  │ ResolutionRefresh    │  │ AnchorPriceWorker    │  │ LivePriceGateway     │
  │ ingestion runtime    │  │ asset_market runtime │  │ Worker               │  │ (CEX path)           │  │ ._stream_dex         │
  │ snapshot gate ★      │  │ DEX path             │  │ asset_market runtime │  │                      │  │ asset_market runtime │
  │ 0.5s 隐式 debounce   │  │                      │  │ inline rebuild ★     │  │                      │  │                      │
  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘
             │ IngestService           │ price_observations      │ identity_evidence       │ price_observations      │ _cache[(tt,tid)]
             │ (single txn)            │ (message_anchor;        │ + registry_assets       │ (message_anchor;        │ in-memory only ★
             ▼                         │  mcap/liq/holders ✓)    │ + asset_identity_*      │  mcap/liq/holders NULL) │ on_live_market_update
  ┌──────────────────────┐             │                         │ + inline rebuild        │                         │  → hub.publish
  │ events + entities    │             │                         │   token_radar ★         │                         │
  │ token_evidence       │             │                         │                         │                         │
  │ token_intents        │             │                         │                         │                         │
  │ token_intent_*       │             │                         │                         │                         │
  │ registry_assets      │             │                         │                         │                         │
  └──────────┬───────────┘             │                         │                         │                         │
             │                         │                         │                         │                         │
             │      ┌──────────────────┴─────────────────────────┴─────────────────────────┘                         │
             │      │   (on_observations_written → request_rebuild ★ asyncio.Event 跨线程 set)                       │
             ▼      ▼                                                                                                │
  ┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐       │
  │ TokenRadarProjectionWorker (token_intel runtime; asyncio.Event wake OR 10s timeout)                     │       │
  │   TokenRadarSourceQuery.source_rows()  ← 11 个 JOIN（events + intents + resolutions + baselines +       │       │
  │                                            event_price_observation + account_profiles +                │       │
  │                                            social_event_extractions + registry_assets +                │       │
  │                                            asset_identity_current + cex_tokens + price_feeds×2）       │       │
  │   build_token_factor_snapshot()                                                                         │       │
  │     _market()      ← 从 event_price_observation 读 mcap/liq/holders；price_usd 始终 None；             │       │
  │                       不读 LivePriceGateway ★                                                            │       │
  │     _gates()       ← _DEX_FLOOR_REASONS 对 NULL `continue`，不阻断 high_alert ★                          │       │
  │     families       ← social_heat/propagation/semantic_catalyst/timing_risk(weight=0)                    │       │
  │     cross_section_normalizer  ← 单成员 cohort = 100 分；全员同分 = 50 分 ★                              │       │
  │   token_radar_rows.factor_snapshot_json                                                                 │       │
  └─────────────────────────────────────┬───────────────────────────────────────────────────────────────────┘       │
                                        │                                                                            │
                                        ▼                                                                            │
  ┌──────────────────────────────────────────────────────────────────────────────┐                                  │
  │ HTTP GET /api/token-radar                                                    │                                  │
  │   AssetFlowService._public_row(row)                                          │                                  │
  │     row.anchor_price ← factor_snapshot.market.anchor_price_usd（DB）         │                                  │
  │     row.live_market  ← {status:"missing"}                                    │                                  │
  │   AssetFlowService._overlay_live_market(row, gateway, now_ms)  ★ 只在 API 合 │◄──┐                              │
  │     gateway.snapshot(tt, tid)                                                │   │                              │
  │     命中即 row.live_market = {...snapshot}                                    │   │ in-memory dict               │
  └──────────────────────────────────────┬───────────────────────────────────────┘   │                              │
                                        │                                            │                              │
                                        ▼                                            │                              │
  ┌──────────────────────────────────────────────────────────────────────────────┐  │  ┌──────────────────────┐    │
  │ Frontend  useQuery(["token-radar"], 10s refetch)                             │  │  │ PublicWebSocketHub   │◄───┘
  │   ↓                                                                          │  │  │ /ws subscribe        │
  │   patchTokenRadarLiveMarketUpdate (features/live/liveMarketUpdatePatch.ts)   │◄─┼──┤ market_targets       │
  │     only liveMarketUpdates[0] each effect cycle ★ 丢中间帧                    │  │  │ publish              │
  │     row.live_market 整体替换（key: target_type+target_id）                    │  │  └──────────────────────┘
  │   ↓                                                                          │  │
  │   tokenRadarRowToTokenItem → TokenFlowItem                                   │  │
  │   ↓                                                                          │  │
  │   TokenRadarRow.tsx · TokenTargetPage.tsx · SearchIntelPage.tsx              │  │
  │     marketPrimary() / marketLine() / radarSummary()                          │  │
  │     isDexMarket 在 3 处重复 ★                                                 │  │
  │     TokenTargetPage 绕过 store 直调 getApi("/api/token-radar") ★              │  │
  └──────────────────────────────────────────────────────────────────────────────┘  │
                                                                                    │
                                                                                    │
  ┌────────────────────────────────────────────────────────────────────────────────┴─┐
  │ PulseCandidateWorker                                                              │
  │   独立线程 + 独立 event loop ★                                                     │
  │   60s poll → repos.token_radar.latest_rows → _is_asset_trigger                    │
  │   写 pulse_candidates / pulse_agent_runs（request_json 只存 context_hash）         │
  └───────────────────────────────────────────────────────────────────────────────────┘
```

**这张图里 13 个 ★ 就是本 spec 的复杂度账本主体。**

## 3. 复杂度账本：13 个绕路点

每条结构：**位置 / 现状 / 为什么这么绕 / 危害 / hard-cut 建议**。按严重度倒序。

### R1（高） anchor↔live 双源在 projection 层不合并

**位置**: `src/parallax/domains/token_intel/services/token_radar_projection.py:604-675` `_market()`

**现状**: `_market()` 只从 `event_price_observation` JOIN 读 `mcap/liq/holders`。`LivePriceGateway` 持有的实时 snapshot **完全不进 factor_snapshot**——它只在 `AssetFlowService._overlay_live_market` 这一处、API 出口、每次请求时合一次，不持久化、不传给 pulse agent。

**为什么这么绕**: `2026-05-11-token-radar-anchor-live-worker-simplification` spec 设计上是对的（projection 保持 platform/db purity，live 走 in-memory），但实施时把"projection 接 gateway snapshot"这一步留给了 API 层，**没人接到 projection 里**。

**危害**:

- `factor_snapshot.market.holders/liquidity_usd/market_cap_usd` 在 DEX 路径下几乎永远 NULL（因为 anchor DEX 路径走 GMGN OpenAPI 写得到这些字段，但 `event_price_observation` 这个 JOIN 是否命中 DEX 行不稳定）
- pulse agent 看不到 live market；它读 factor_snapshot 而不是 API row
- `_gates` 永远拿到 NULL（见 R8），DEX floor 形同虚设
- live 与 anchor 的"双真相"靠每次 API request 临时合并，**前端拿到的 row 跟 pulse agent 拿到的 snapshot 是不同的世界**

**hard-cut 建议**: projection 也调一次 `live_market_gateway.snapshot(tt, tid)`。命中且未 stale → 把 mcap/liq/holders/volume 写进 `factor_snapshot.market`，并标 `market_data_source='live'`。未命中 → 保留 anchor-only 并标 `market_data_source='anchor_only'`。projection 跟 platform/db 的边界依然干净（gateway 走 interface 注入，不引 db）。

### R2（高） OKX 多源采集无统一调度

**位置**: 散落在三个 worker 里

- `AnchorPriceWorker._write_cex_observation` (anchor_price_observation.py:170) → `OkxCexClient.ticker`
- `ResolutionRefreshWorker` → `OkxDexClient.search_tokens` (dex_client.py:39)
- `LivePriceGateway._poll_cex` (live_price_gateway.py:198) → `OkxCexClient.ticker` again
- `LivePriceGateway._stream_dex` → `OkxDexWebSocketMarketProvider...` → `OkxDexWsClient.stream_price_info`

**现状**: 同一份 OKX 数据在系统里有 **4 个独立采集点**，没有共享调度、没有共享 cache、没有共享 rate limit budget。`OkxCexClient.ticker` 在 anchor 路径和 live 路径**被同一进程双采**——anchor 5s 一次写 DB，live 30s 一次写内存。

**为什么这么绕**: anchor 和 live 是不同时期分开演进的——anchor 是为了"event-time 持久化"，live 是为了"实时屏幕显示"。但二者共享 100% 的 provider 客户端代码，只是消费端不同。

**危害**:

- OKX 配额浪费——CEX ticker 对同一 token 每分钟被采 ≥ 12 次（anchor 12 + live 2）
- 失败处理不一致——anchor 失败有 backoff，live 失败按 cycle bound 兜底，两边的"OKX 是否健康"信号不互通
- 加 provider 一次性需要改 4 个地方
- 调试时"为什么 X token 没数据"很难定位是哪个采集点失败

**hard-cut 建议**: 把 OKX 视为一个 provider bundle，而不是在业务层散布 3 个独立采集点。保留窄 provider capability（CEX quote / DEX search / DEX stream），但由同一个 OKX adapter 层拥有 rate limit、cache、health、credentials 和状态观测。CEX ticker 一次拿到的结果，anchor 和 live 都用同一份标准化 `MarketObservation`。

(本 spec 不细化 supervisor 形态——目标架构节再展开。)

### R3（中） GMGN WS 帧 price 字段被类型层硬切，但下游消费者不知道这条边界为什么存在

**位置**:
- `src/parallax/integrations/gmgn/gmgn_token_payload.py:17-45` —— `parse_gmgn_token_payload` 只读 `{a, c, s, i, tt}`
- `src/parallax/domains/ingestion/services/normalizer.py:50` —— `TokenSnapshot` 类型无 price 字段
- `src/parallax/domains/asset_market/services/anchor_price_observation.py:205-244` —— DEX anchor path 调 `gmgn_dex_quote.token_quotes`（**GMGN OpenAPI**），写完整 mcap/liq/holders/volume

**现状**: 同一 provider（GMGN）的两个客户端在系统里承担**不同角色**：

| Client | 角色 | 字段集 |
|---|---|---|
| `direct_ws.py`（社交流） | identity-only（address/chain/symbol） | WS frame 内的 price/mcap **被类型层丢弃** |
| `openapi_client.py`（OpenAPI REST） | exact-address DEX market | price + mcap + liquidity + holders + volume |

这是 `2026-05-12-gmgn-dex-market-provider-split-cn.md`（已批准实施）的 "capability beats brand" 原则：social stream frame 里的 price 是 tweet 触发时刻 snapshot 而非市场实时价；market 必须由 exact-address provider call 提供。**架构是对的**——但代码里没有任何 docstring/comment 解释这条边界，新人/agent 读 `parse_gmgn_token_payload` 完全不知道"为什么丢 price"。

**为什么这么绕**:
- 边界来自 spec 决策，但 spec 决策没沉淀到代码 docstring
- `TokenSnapshot` 类型连 price 字段都没定义——只能从"缺字段"反推意图
- 同一 provider 维护两套客户端代码，二者字段语义割裂

**危害**:
- 新人/agent 看到 frame 里有 price 字段就想顺手写，被类型层挡掉但拿不到 "why"
- 后续如果 GMGN 改 frame schema 或 GMGN 暴露新 WS 市场 endpoint，这条边界没有自检——靠"代码里没字段"防御
- 跨 spec 阅读才能拼出"GMGN WS = identity / GMGN REST = market"这条规则；进入项目的成本高

**hard-cut 建议**:
1. `gmgn_token_payload.py` 顶部加 docstring：明确"This intentionally drops embedded GMGN frame price/mcap fields. Market facts for resolved DEX assets flow via gmgn OpenAPI through `asset_market.anchor_price_worker` per `2026-05-12-gmgn-dex-market-provider-split-cn.md`."
2. `TokenSnapshot` 添加单元测试，断言 raw frame 里若出现 `t.x.price / mcap / liquidity` 字段，**`parse_gmgn_token_payload` 返回的 raw 子集里仍不含这些 key**（防御性 lock）
3. **不改 provider 选择**——保持 GMGN OpenAPI 做 anchor exact-address quote、OKX 做 live + discovery + CEX（即 split spec 决策）

> ⚠️ 重要：本 spec 明确**不建议**砍 GMGN OpenAPI 的 anchor 路径。该路径是 `2026-05-12-gmgn-dex-market-provider-split-cn.md` 的 G3 落地；下游真正的问题是 R1（projection 不读 live gateway），不是 anchor provider 选错了。

### R4（高） `dex_ws_enabled=false` 默认未启

**位置**:
- `src/parallax/platform/config/settings.py:297` `dex_ws_enabled: bool = False`
- `src/parallax/integrations/okx/dex_ws_client.py`（工作区刚改了 timestamp 格式 + arg merge——见 R5）

**现状**: 整个 DEX live 路径"runtime 已实施"（2026-05-11 spec），但默认关。代码热路径上 24h 0 个 update。

**为什么这么绕**: 引入时怕 OKX 配额——`2026-05-11-okx-dex-ws-market-stream-and-radar-recovery` spec line 113 写了"default false until deployed and verified"。但**已经 2 天过去，没有验证步骤**，工作区里的两个 commit（timestamp 修复 + cycle bound）说明这条线还有真 bug，证明默认 false 是必要的，但**"何时打开"没有 owner**。

**危害**:

- 整条 DEX live 路径在生产环境零流量——任何依赖 LivePriceGateway 的下游（前端 live overlay、`/api/live-market`、pulse agent 间接）对 DEX target 永远是"missing"
- 工作区的 timestamp + arg merge 两个 bug 之前没被发现，正是因为这条路 0 流量
- "代码看起来完整但生产环境没跑"这种状态比"代码不完整"更危险——会让人误以为已经在跑

**hard-cut 建议**:

1. 工作区两个修复合入后，必须在 staging 跑 24h smoke test（看 `live_market_updates_published / dex_targets_selected` 比例、OKX 配额峰值、reconnect 频次）
2. 通过后 **删掉 `dex_ws_enabled` flag**——改成"`dex_ws_url` 存在即启用"，flag 本身是过渡期产物
3. 同期把 R1 落地（projection 消费 LivePriceGateway snapshot），让"DEX live 已启用"这个事实真正传到 factor_snapshot.market

### R5（高） OKX DEX WS 状态机隐式

**位置**: `src/parallax/integrations/okx/dex_ws_client.py`

**现状**: 没有 `ConnectionState` enum、没有公开的状态属性。状态完全藏在 `stream_price_info()` 这个 async generator 的控制流：

```
DISCONNECTED → CONNECTING → AUTHENTICATING → SUBSCRIBED → DISCONNECTED
```

`_wait_for_login()` 循环里**静默 discard 非 login 帧**——如果 OKX 在 login ack 前先发了 subscribe ack（比如协议改了顺序），ack 会被丢，订阅状态外部不可知。

工作区刚改了两个 bug：
1. timestamp 从 ISO-8601 改成 Unix epoch seconds（之前哪怕开了也连不上）
2. `_rows_from_message` 把 subscription `arg` context 合并进每行（之前 `chainIndex/tokenContractAddress` 永远是 None）

**为什么这么绕**: 直接照搬了 `websockets` 库的"一个 generator 一次连接"风格，没有把"我现在在哪个阶段"显式建模。

**危害**:

- 上面两个 bug 在生产环境从来没暴露过（dex_ws_enabled=false），如果是显式状态机 + 状态 metric，更容易被监控发现
- `/api/status.live_price_gateway` 只能暴露 "task running" + "last_result" 这种粗粒度——dex_ws_enabled=true 上线时如果连不上 OKX，告警里看不到是"卡在 CONNECTING"还是"卡在 AUTHENTICATING"
- 测试覆盖只能 mock 整个 generator，不能针对每个状态写边界 case

**hard-cut 建议**: 加 `ConnectionState` enum + 一个 `state: ConnectionState` 公开属性 + 一个 `last_state_change_at_ms` 时间戳。状态变化时写一行 structured log。`/api/status.live_price_gateway` 暴露 `dex_ws.state` 字段。这个改造非常小（~30 行 + 测试），收益是把 DEX 流量上线时的故障定位从"看 stack trace"变成"看 state metric"。

GMGN Direct WS 同病——`integrations/gmgn/direct_ws.py` 同样的状态机隐式。一并改。

### R6（高） `_gates` NULL `continue` 不阻断 high_alert

**位置**: `src/parallax/domains/token_intel/scoring/factor_snapshot.py:307-373`

**现状**:

```python
for key, reason in _DEX_FLOOR_REASONS.items():
    value = _optional_float(market.get(key))
    if value is None:
        metadata_missing = True
        continue                       # ← NULL 跳过，不 block
    if _is_below(value, key):
        blocked_reasons.append(reason)
if metadata_missing:
    risk_reasons.append("market_metadata_missing")   # 只进 risk
```

**为什么这么绕**: 写这段逻辑的时候，假设了"NULL = 数据还没采到 → 暂时不阻断"。但因为 R1（projection 不读 live gateway）+ R4（DEX live 0 流量）的存在，"NULL = 永远采不到"是默认状态，"NULL = 数据正常但还在采"是少数。

**危害**:

- `DEX_HIGH_ALERT_FLOORS` 字典定义了 `holders >= 100, liquidity >= $25k, mcap >= $50k`，但对真实流量 **从未生效**——24h 内 `pulse_candidates.factor_snapshot_json.market.holders=NULL` 占比 100%
- 这是 `2026-05-12-signal-lab-pulse-agent-pipeline-current-state` G3 的核心遗留

**hard-cut 建议**:

```python
if value is None:
    blocked_reasons.append(f"{key}_unverified")
    continue
```

部署顺序必须是 **R1 → 等 mcap/liq/holders 真的开始流 → 再 R6**，否则会"清零"pulse 输出。

### R7（中） Worker 间唤醒的三条边都是次优手段

**位置**:

| 边 | 当前手段 | 文件 |
|---|---|---|
| AnchorPriceWorker → ProjectionWorker | `on_observations_written` callback → `asyncio.Event.set()` **从 `to_thread` 线程发起** ★ | `anchor_price_worker.py:58-59` → `token_radar_projection_worker.py:70-72` |
| ResolutionRefreshWorker → token_radar | **inline 直接调** `rebuild_token_radar_windows()` ★ | `resolution_refresh_worker.py:207-213` |
| ResolutionRefreshWorker → AnchorPriceWorker | **inline 直接调** `observe_anchor_prices()` ★ | `resolution_refresh_worker.py:200` |

**现状**: 三条边都没走 "wake another worker"模式——一条用 `asyncio.Event` 跨线程 set（语义上 not thread-safe，CPython GIL 救命），两条直接在自己的 `to_thread` 里 inline 调对方的工作。

**为什么这么绕**: 引入顺序：先有 ResolutionRefreshWorker（inline 一切是最简单写法），再有 AnchorPriceWorker→ProjectionWorker 的唤醒边（`be742c83` 这次提交），所以两套机制并存。

**危害**:

- `asyncio.Event.set()` 跨线程在 free-threaded Python / 其他 runtime 上是 UB；当前靠 CPython GIL
- inline rebuild 让两个 worker **并发写同一组 `(window, scope)` 的 `token_radar_rows`**——靠 Postgres 行锁 + INSERT ON CONFLICT 保证不损坏，但 `projection_runs / projection_offsets` 计数可能漂
- "谁负责重建 token_radar"这个职责被拆到两个 worker，调试时"为什么这一帧是 ResolutionRefresh 写的而不是 ProjectionWorker 写的"答不上来

**hard-cut 建议**:

- 改 `request_rebuild()` 为线程安全：用 `loop.call_soon_threadsafe(event.set)` 包一层，或者把它改成一个 `threading.Event`（projection worker 端在 sleep 边界检查）
- `ResolutionRefreshWorker` 的两条 inline 调用都改成 wake：
  - `resolved_intents > 0` → `projection_worker.request_rebuild()`，不 inline rebuild
  - `resolved_intents > 0` → `anchor_price_worker.request_run()` （新加一个 wake event），不 inline observe
- 收益：每个表只有**一个 writer worker**

### R8（中） `cross_section_normalizer` 在 cohort 边界上两头都错

**位置**: `src/parallax/domains/token_intel/scoring/cross_section_normalizer.py:13-28`

**现状**:

- 单成员 cohort：`avg_rank=(0+0+2)/2=1, percentile=1.0`，×100=**100** —— 一只 token 自己跟自己比，永远 100 分
- cohort 全员同 raw score：所有 token tie 在中位，percentile=0.5，×100=**50** —— 全员都坏看起来"中性"

**为什么这么绕**: 标准 fractional ranking 算法在这两个边界 case 上的数学是"对的"，但**语义是错的**——产品意义上"我自己跟自己比"和"大家都坏"都应该是 None，不应该是个分数。

**危害**:

- spec `2026-05-12-signal-lab-pulse-agent-pipeline-current-state` G4：27/27 trade_candidate 的 `timing_risk=50, semantic_catalyst=49`，pulse agent 把 50 当"中性"读，实际是"全员都坏"
- 反过来：冷门小 cohort 里的 token 单成员 100 分，pulse agent 把 100 当"绝对强"读，实际是"没人比"

**hard-cut 建议**:

- cohort_size < N（建议 N=10）→ 该 family 的 percentile 返回 None，下游消费者必须显式处理"无 cohort"语义
- cohort 全员 raw score 相同（或全员都坏：`data_health != 'ready'` 占比 ≥ 90%）→ 该 family 返回 None
- pulse_recommendation_agent_instructions 加一段：family.score=None 时不要解读为"中性"，要解读为"cohort 无信号"

### R9（中） snapshot gate 是 0.5s 隐式 debounce

**位置**: `src/parallax/domains/ingestion/runtime/collector_service.py:96-116` `_handle_item`

**现状**:

- 有 `tw` 且 `cp != 1`：起 0.5s asyncio task `_dispatch_snapshot_after_timeout`
- 同 key 来了 `cp == 1`：cancel pending，立刻处理
- 0.5s 到了还没等到：用现 frame 当 snapshot

**为什么这么绕**: GMGN frame 有 "incremental + complete" 双语义，0.5s 是为了"等一下完整版"的实用值。但概念上这是"我在等一个状态变化"，**不是命名状态**——没有 `WAITING_FOR_COMPLETE_PAYLOAD` 状态，没有 metric 标记"我等到了 vs 我超时了"。

**危害**:

- 0.5s 是 magic number，不在 config 里
- `public_broadcast` channel 永远没有 `cp` 字段，debounce 永远不触发——`_dispatch_snapshot_after_timeout` 对这条 channel 是死代码
- 无法观测"被 debounce 的 frame 比例"——监控盲区
- 同 frame 在 0.5s 内被 cancel 重发的语义不在任何文档里

**hard-cut 建议**:

- 加 enum `SnapshotGateOutcome = {IMMEDIATE_COMPLETE, DEBOUNCED_COMPLETE, DEBOUNCED_TIMEOUT, NON_TW_CHANNEL}`
- 加 metric `snapshot_gate_outcomes_total{outcome=...}`
- 0.5s 提到 `settings.ingestion.snapshot_gate_debounce_ms`
- `public_broadcast` channel 显式跳过 debounce 分支（消除死代码）

### R10（中） PulseCandidateWorker 独立线程独立 event loop

**位置**: `src/parallax/app/runtime/app.py` `_start_threaded_async_worker` 启动

**现状**: PulseCandidateWorker 不在主 event loop 上——它在一个独立的 daemon thread 里跑自己的 `asyncio.run(...)`。`stop()` 只翻 `_stopped = True`，要等下一轮 poll 边界才能结束。

**为什么这么绕**: 大概率是因为 pulse agent 调 OpenAI LLM API，怕单次调用阻塞主 loop。但 LLM API 本身是 async 的，**它阻塞不了 event loop**——只是单次调用慢（几秒到几十秒）。

**危害**:

- 线程边界让 graceful shutdown 慢——`stop()` 必须等 60s poll 边界，最坏 case 是等 LLM 调用完成
- `/readyz` 检查"task 是否活着"对线程不适用——用了一个 polling watchdog 兜底
- 跨 loop 没法 cancel——主 loop 关闭时这个线程不能用 asyncio 标准的 cancel/await/timeout 收尾
- 跟其他 9 个 worker 行为风格不一致，新人需要单独学这条分支

**hard-cut 建议**: 删掉独立线程，让 PulseCandidateWorker 跟其他 worker 一样作为 asyncio task 在主 loop 跑。OpenAI 调用本来就是 `await`-able 的。如果担心单个 LLM 调用阻塞太久，用 `asyncio.wait_for(timeout=...)` 包，不要用线程。

### R11（中） 前端 useLiveData 丢中间 live 帧

**位置**: `web/src/features/live/useLiveData.ts:156`

**现状**:

```tsx
useEffect(() => {
  const latest = socket.liveMarketUpdates[0];   // 只取第一个（最新）
  if (latest) patchTokenRadarLiveMarketUpdate(queryClient, latest);
}, [socket.liveMarketUpdates]);
```

`socket.liveMarketUpdates` 是 prepend-newest 数组，cap=100。effect 依赖整个数组 reference。**两次 React render 之间多帧到达只会处理最新一帧**，中间帧静默丢弃。

**为什么这么绕**: 把 WS 帧累积在 `useState` 数组里，"我去读最新一帧"的写法是最直觉的；但这跟"我必须 apply 每一帧"的语义不一致。

**危害**:

- 价格类是"持续累积"语义，丢中间帧无害（最新即正确）
- mcap/liq/holders **不是连续函数**——丢帧会导致下游看到的瞬态值跳跃
- React StrictMode 双渲染下 effect 可能跑两次但状态没变，潜在重复 patch 风险

**hard-cut 建议**:

- 把 `useIntelSocket` 改成 callback 注入：`onLiveMarketUpdate(payload)` 在每帧到达时同步触发，不累积
- `useLiveData` 直接传入 callback，不读数组
- 累积数组保留给 UI"最近 N 帧"调试面板用，不参与业务 patch

### R12（中） TokenTargetPage 绕过 store 直调 api

**位置**: `web/src/components/TokenTargetPage.tsx:85`

**现状**: 组件内直接 `useQuery(["token-radar-page", ...], () => getApi("/api/token-radar", ...))`，绕过 `useTraderStore`。

**为什么这么绕**: 应该是为了避免污染主 `["token-radar"]` 缓存——用了独立 queryKey。但这违反 `docs/FRONTEND.md` 的 "components 不直接调 api/"。

**危害**:

- 同一 endpoint 在系统里有两个调用点，缓存策略不一致
- `patchTokenRadarLiveMarketUpdate` 只 patch `["token-radar"]`，**TokenTargetPage 的 `["token-radar-page"]` 缓存永远拿不到 live 帧**——这条页面上的 live 数据是死的
- store 分层规则在这里被打破，后续可能扩散

**hard-cut 建议**: 用 store/feature hook 包装，让两个 caller 共享同一缓存 key（或者明确"页面级 fork 缓存"是个 store 暴露的策略，写入文档）。

### R13（低） isDexMarket 三处重复

**位置**:
- `web/src/components/TokenRadarRow.tsx:208`
- `web/src/components/TokenTargetPage.tsx:571`
- `web/src/components/SearchIntelPage.tsx:537`

**现状**: 三个组件各有一份 `isDexMarket` 谓词，逻辑一致但独立维护。工作区刚做的 "DEX-vs-CEX market primary" UI 改造里这三处需要同步修。

**hard-cut 建议**: 提到 `web/src/domain/tokenTarget.ts`，跟 `targetRefEquals`/`targetRefFromTokenItem` 放一起。

## 4. 多源数据合并专题（GMGN + OKX）

把 R1/R2/R3 提到的多源问题用一张矩阵表完整呈现：

### 4.1 采集 → 写入 → 读取矩阵

| 采集源 | 客户端 | 调用方 | 写入位置 | 读取位置 | 字段集 |
|---|---|---|---|---|---|
| GMGN Direct WS | `direct_ws.py` | CollectorService | `events/event_entities/token_evidence/token_intents/registry_assets/...` | TokenRadarSourceQuery 11 个 JOIN 之一 | identity-only：address/chain/symbol/icon |
| GMGN OpenAPI | `openapi_client.py` | AnchorPriceWorker.DEX path | `price_observations(message_anchor)` + `token_market_price_baselines` | TokenRadarSourceQuery JOIN `event_price_observation` | DEX 市场全字段：price/mcap/liq/holders/vol |
| OKX REST search | `dex_client.py` | ResolutionRefreshWorker | `asset_identity_evidence(provider=okx)` | resolution policy + asset_identity_current | identity + 部分市场字段（不进 price_observations） |
| OKX REST CEX ticker | `cex_client.py` | AnchorPriceWorker.CEX path + LivePriceGateway._poll_cex | anchor: `price_observations(message_anchor)`；live: `_cache` 内存 | anchor: SourceQuery JOIN；live: API overlay + WS push | CEX：price/quote/volume，无 mcap/liq/holders |
| OKX DEX WS | `dex_ws_client.py` | LivePriceGateway._stream_dex | `_cache` 内存 | API overlay + WS push | DEX live：price/mcap/liq/holders/vol |

**5 个采集源、5 套客户端、3 个写入路径（DB anchor / 内存 live / identity evidence）、2 套读取通路（projection SQL + API overlay）。**

### 4.2 合并语义的混乱

合并发生在**三个位置**，每个位置语义不同：

| 合并点 | 位置 | 合并语义 | 输出消费者 |
|---|---|---|---|
| 合并 A | `token_radar_projection._market()` | anchor only（不读 live gateway） | factor_snapshot.market → pulse agent / 历史评估 |
| 合并 B | `AssetFlowService._overlay_live_market` | row from projection + live snapshot from gateway，每请求合一次 | HTTP `/api/token-radar` response |
| 合并 C | `patchTokenRadarLiveMarketUpdate` 前端 | TanStack Query cache row + WS push payload | UI 渲染 |

**结果**: pulse agent 看到的 row（来自合并 A）≠ 前端看到的 row（来自合并 B + C）。这是 R1 的核心症状：**同一概念的"market" 在系统里有两个真相版本**。

### 4.3 GMGN OpenAPI vs OKX DEX WS：DEX 市场数据的两条主路

| 维度 | GMGN OpenAPI（anchor 路径） | OKX DEX WS（live 路径） |
|---|---|---|
| 触发 | AnchorPriceWorker 5s 轮询 | 事件流，subscribe 后实时推 |
| 延迟 | 几秒到几十秒 | < 200ms |
| 完整性 | 看 GMGN OpenAPI 返回稳定度 | OKX 协议保证完整 |
| 持久化 | `price_observations` | 进程内 |
| 在生产现在跑吗 | 跑（CEX 路径 16 个 target，DEX 路径 84 个 target） | **0 updates**（dex_ws_enabled=false） |
| 一致性 | 二者**没有交叉验证**，谁对谁错由 schema 决定 | 同上 |

本 spec **不**砍二者中的任何一个——按 `2026-05-12-gmgn-dex-market-provider-split-cn.md` 已批准的角色划分（GMGN = exact-address quote/profile/candle，OKX = discovery/CEX/DEX-live-stream），二者各司其职。**真正的绕路是 projection 层不合并这两条数据**（R1），而不是 provider 选错了。

## 5. 半完成 hard cut 清单

按 spec id 追溯。每条标"已实施 / 剩余"。

### HC1 `2026-05-11-okx-dex-ws-market-stream-and-radar-recovery-cn.md`

- **已实施**: LivePriceGateway runtime / `OkxDexWsClient` / WS push 链路 / `/api/live-market` endpoint / 测试基线
- **剩余**:
  - `dex_ws_enabled=false` 默认值，没有"启用流程" owner（R4）
  - 工作区里的 timestamp + arg merge 两个真 bug 是合上线前发现的（R5）
  - 部署验证 acceptance criteria 列了但没有跑（"deployed and verified" 是空话）

### HC2 `2026-05-11-token-radar-anchor-live-worker-simplification-cn.md`

- **已实施**: anchor/live 拆分；`price_observations.observation_kind='message_anchor'` only；migration `20260511_0029`；LivePriceGateway 设计成 in-memory
- **剩余**:
  - projection 层没有接 live gateway snapshot（R1）——这是"设计上 anchor/live 分两个真相源"的必然后果，但当时 spec 没有把 "projection 怎么消费 live" 落实
  - factor_snapshot.market 永远缺 live 字段，pulse agent 永远拿不到 live mcap/liq/holders

### HC3 `2026-05-11-token-radar-market-boundary-hard-cut-cn.md`

- **已实施**: 字段级边界（market 仅 anchor + readiness）；snapshot 合同里把 market 标"不是 alpha 家族"
- **剩余**:
  - `_market()` 改了 `price_usd / price_quote = None`（confirmed at token_radar_projection.py:636-637），但**没有改 mcap/liq/holders 的 DEX 来源**，这一段被认为是数据可用性问题而非合同问题
  - 实际上是 R1 的另一面：合同写了，数据流没接上

### HC4 `2026-05-12-market-data-pipeline-gap-cn.md`

- **已实施**: hot resolution refresh、symbol-only resolution、anchor DEX provider 已切到 GMGN OpenAPI（`gmgn-dex-market-provider-split` G3）
- **剩余**:
  - factor_snapshot.market 仍不消费 LivePriceGateway（projection 层 R1）；anchor 写到 `price_observations` 的 mcap/liq/holders 经过 baseline JOIN 后才能进 snapshot，且只在 GMGN OpenAPI 成功命中时有值
  - `_gates` NULL `continue`（R6）
  - `okx_dex_search` 路径周期化（spec 提到 24h 跑了 25 次，没改）

### HC5 `2026-05-12-signal-lab-pulse-agent-pipeline-current-state-cn.md`

- **设计了 G1-G4 但都没改**：
  - G1 (`_market()` 消费 live gateway) → R1
  - G2 (`_gates` fail-closed) → R6
  - G3 (agent prompt 标注 percentile) → 另一篇 spec 范围
  - G4 (`request_json` 持久化 prompt) → 另一篇 spec 范围

## 6. 隐式状态机清单

| # | 状态机 | 当前藏在哪儿 | 应有的命名状态 |
|---|---|---|---|
| 1 | OKX DEX WS 连接 | `dex_ws_client.py` generator 控制流 | `DISCONNECTED / CONNECTING / AUTHENTICATING / SUBSCRIBED / DRAINING` |
| 2 | GMGN Direct WS 连接 | `direct_ws.py` generator 控制流 | `DISCONNECTED / CONNECTING / SUBSCRIBING / STREAMING / IDLE_TIMEOUT` |
| 3 | snapshot gate（GMGN tw frame 是否等 cp=1） | `collector_service._handle_item` 的 asyncio task pending | `IMMEDIATE_COMPLETE / DEBOUNCED / DEBOUNCE_TIMEOUT / NON_TW_CHANNEL` |
| 4 | `live_market.status` flag | 一个 string 字段，可能值散落多处 | `Literal["missing","unsupported","live","stale","partial","fresh","anchored"]` |
| 5 | TokenRadarProjectionWorker rebuild 状态 | `_wake_event.is_set()` + sleep loop | `IDLE / WAKING / REBUILDING_HOT / REBUILDING_BACKGROUND` |

5 个状态机里，**1 个会直接影响 dex_ws_enabled=true 上线时的故障定位**（#1），**1 个会影响 ingest 调试**（#3），**1 个会影响前端 status 展示**（#4）。

（PulseCandidateWorker 的 `_stopped` flag 是简单 bool，不算状态机；其线程隔离问题已在 R10 单独处理。）

## 7. 跨域耦合违规

按 ARCHITECTURE.md 的 dependency direction 检查，发现以下硬违规：

| # | 违规 | 位置 | 严重度 |
|---|---|---|---|
| C1 | evidence 域 `IngestService` 编译期 import `asset_market.RegistryRepository / IdentityEvidenceRepository` | `src/parallax/domains/evidence/services/ingest_service.py:8-16` | **高** |
| C2 | CLI surface 直接 import `OkxCexClient / OkxDexClient / GmgnDirectoryClient / GmgnOpenApiClient` | `src/parallax/app/surfaces/cli/main.py:55-58, 737, 784` | 低（已知 surface exception） |
| C3 | 前端 `TokenTargetPage` 直调 `getApi` | `web/src/components/TokenTargetPage.tsx:85` | 中（R12 同义） |
| C4 | 前端 `useSearchInspectQuery` 直读 `useTraderStore` | `web/src/api/useSearchInspectQuery.ts:16` | 低 |

**C1** 是最严重的——`tests/test_src_domain_architecture.py::test_cross_domain_imports_use_interfaces` 应该捕到但没捕到（说明 archtest 规则可能漏了 evidence→asset_market 这条边，或者 evidence 把 import 放到了 interfaces.py 引导处）。

## 8. 目标架构（target state）—— Kappa / CQRS hard cut

### 8.1 设计立场：事实源唯一，读模型可重建

本修订版把 §4 的 13 个绕路点收敛到一个更小的架构命题：**raw facts 是唯一事实源；所有面向产品的表、API payload、pulse context、前端 cache 都是 read model**。这借鉴 Kappa/CQRS 的成熟做法，但不引入 Kafka/NATS 等新基础设施；本项目当前体量用 PostgreSQL facts + projection worker + LISTEN/NOTIFY wake hint 足够。

本次 hard cut 不保留旧 `factor_snapshot.market` / `anchor_price` / `live_market` 兼容代码。需要保留的是业务事实本身：`events`、`token_intents`、`token_intent_resolutions`、`asset_identity_*`、`price_observations`。需要重建的是 derived state：`token_radar_rows`、projection offsets/runs、pulse candidate context、前端 TanStack cache。

### 8.2 五条不变量

1. **One fact type**：市场事实只有 `MarketObservation` 一种 value object；GMGN anchor、OKX CEX quote、OKX DEX WS update 都只是不同 `source` / `observed_at_ms`。
2. **Two time roles**：`MarketContext` 明确区分 `event_anchor`（社交事件时刻，用于回测与因果）和 `decision_latest`（投影/决策时刻，用于 gate、pulse、UI 当前态）。不要把二者压成一个万能 market。
3. **One writer per read model**：`token_radar_rows` 只由 `TokenRadarProjectionWorker` 写；pulse candidate 只由 `PulseCandidateWorker` 写；resolution refresh 只写 discovery/resolution/identity facts。
4. **Notifications are hints**：`LISTEN/NOTIFY` 只负责唤醒；正确性来自消费端重读 DB facts + periodic catch-up。丢 NOTIFY 不得导致事实丢失。
5. **No compatibility layer**：新 schema 生效后，旧 snapshot 字段、API live overlay、前端重复合并逻辑全部删除；验证通过后用重建读模型恢复服务。

### 8.3 核心模型

语义模型如下，具体签名和文件级编辑写入对应 plan。

```text
MarketObservation
  target_type / target_id
  observed_at_ms / received_at_ms
  source / provider / pricefeed_id
  price_usd / price_quote / quote_symbol / price_basis
  market_cap_usd / liquidity_usd / holders / volume_24h_usd / open_interest_usd
  raw_payload_hash

MarketContext
  event_anchor: MarketObservation | None
  decision_latest: MarketObservation | None
  readiness:
    anchor_status
    latest_status
    dex_floor_status
    missing_fields
    stale_fields
```

`event_anchor` 的语义是 "as-of social signal start"，不可被当前 live price 覆盖。`decision_latest` 的语义是 "as-of projection computation"，允许来自 OKX DEX WS / OKX CEX poll / 最新 GMGN exact quote。Signal Pulse 和 UI 读取同一份 `factor_snapshot.market.decision_latest`，不再在 API 层或前端临时拼一个第二真相。

### 8.4 目标数据流

```
[ADAPTER] GMGN Direct WS / GMGN OpenAPI / OKX REST / OKX DEX WS
    ↓
[COMMAND] CollectorService / IngestService / ResolutionRefreshWorker / AnchorPriceWorker / LivePriceGateway
    ↓ writes
[FACT] events, token_intents, token_intent_resolutions, asset_identity_*, price_observations
    ↓ NOTIFY wake hint + periodic catch-up
[PROJECTION] TokenRadarProjectionWorker
    ↓ reads facts, builds MarketContext, gates, ranks
[READ MODEL] token_radar_rows.factor_snapshot_json
    ↓
[QUERY] AssetFlowService / SignalPulseService / TokenTarget read models
    ↓
[SURFACE] HTTP / WS / CLI
    ↓
[UI] one token-radar store/cache, per-frame live updates, no API overlay
```

这条链路对应 CQRS：command side 只写 facts；query side 只读 read models；projection 是唯一的 derived-state 生产者。`LISTEN/NOTIFY` 在图中只连接 fact write 和 projection wake，不承载完整业务 payload。

### 8.5 目录/文件角色标记

实施计划必须给所有触达文件打标。标记语义如下：

| 标记 | 含义 |
|---|---|
| `[ADAPTER]` | 第三方 API/WS 客户端与 provider adapter，只翻译外部协议。 |
| `[COMMAND]` | 接收事件、执行写入事实的 worker/service。 |
| `[FACT]` | repository / migration / table contract，事实源可重放。 |
| `[WAKE]` | NOTIFY/LISTEN、catch-up、worker 唤醒，不承载事实。 |
| `[PROJECTION]` | 从 facts 构造 read model。 |
| `[SCORING]` | gates、normalizer、factor snapshot 合同。 |
| `[QUERY]` | 读取 read model 并序列化领域视图，不写事实。 |
| `[SURFACE]` | HTTP / WS / CLI public contract。 |
| `[UI]` | 前端 cache、hook、component、domain helper。 |
| `[DELETE]` | 本次 hard cut 必须删除的旧路径。 |

核心文件标记：

| 文件 | 标记 | 目标职责 |
|---|---|---|
| `domains/asset_market/providers.py` | `[ADAPTER]` | 保留窄 provider capability；删除业务层散布的 provider 语义。 |
| `app/runtime/providers_wiring.py` | `[ADAPTER]` | 统一 OKX/GmGN adapter wire、health/cache/rate-limit 所有权。 |
| `domains/asset_market/runtime/anchor_price_worker.py` | `[COMMAND][WAKE]` | 写 `price_observations` 后 NOTIFY；删除 callback。 |
| `domains/asset_market/runtime/live_price_gateway.py` | `[COMMAND][FACT][WAKE]` | live update 写入 observation stream；publish WS 只作为 surface fan-out。 |
| `domains/asset_market/runtime/resolution_refresh_worker.py` | `[COMMAND][WAKE]` | 只写 discovery/resolution/identity facts；删除 inline anchor/projection。 |
| `domains/asset_market/services/anchor_price_observation.py` | `[COMMAND][FACT]` | 标准化 GMGN/OKX quote 为 `MarketObservation`。 |
| `domains/asset_market/repositories/price_observation_repository.py` | `[FACT]` | `MarketObservation` 持久化与 as-of/latest 查询。 |
| `domains/token_intel/runtime/token_radar_projection_worker.py` | `[WAKE][PROJECTION]` | LISTEN + catch-up；唯一写 `token_radar_rows`。 |
| `domains/token_intel/services/token_radar_projection.py` | `[PROJECTION]` | 构造 `MarketContext`；删除 `_market()` anchor-only 语义。 |
| `domains/token_intel/queries/token_radar_source_query.py` | `[QUERY][FACT]` | 从 facts 拉 projection input；不做 API overlay。 |
| `domains/token_intel/scoring/factor_snapshot.py` | `[SCORING]` | 新 market schema、DEX floors fail-closed。 |
| `domains/token_intel/scoring/cross_section_normalizer.py` | `[SCORING]` | insufficient/all-tied cohort 返回 no-signal。 |
| `domains/token_intel/read_models/asset_flow_service.py` | `[QUERY][DELETE]` | 删除 `_overlay_live_market`；只序列化 read model。 |
| `domains/pulse_lab/runtime/pulse_candidate_worker.py` | `[WAKE][QUERY]` | 主 event loop task；listen read model updates；不独立线程。 |
| `app/runtime/app.py` | `[SURFACE][WAKE][DELETE]` | 删除 threaded pulse wrapper；wire listeners。 |
| `app/surfaces/api/http.py` / `ws.py` | `[SURFACE]` | 暴露新 market contract；WS live event 不再修补旧 row。 |
| `web/src/api/useIntelSocket.ts` | `[UI]` | 每帧 callback，不以数组 head 表示业务事件。 |
| `web/src/features/live/useLiveData.ts` | `[UI][DELETE]` | 删除 `liveMarketUpdates[0]` patch 模式。 |
| `web/src/features/live/liveMarketUpdatePatch.ts` | `[UI]` | 只 patch 新 `decision_latest` shape。 |
| `web/src/components/TokenTargetPage.tsx` | `[UI][DELETE]` | 删除直接 `getApi("/api/token-radar")` 旁路 cache。 |
| `web/src/domain/tokenTarget.ts` | `[UI]` | 统一 target/ref/market helper。 |

### 8.6 必删路径

以下代码路径是复杂度根源，不做兼容保留：

| 路径 | 删除原因 |
|---|---|
| `AssetFlowService._overlay_live_market` | API 出口临时合并制造第二真相。 |
| `TokenRadarProjection._market()` anchor-only schema | 与 `decision_latest` 语义冲突。 |
| `AnchorPriceWorker.on_observations_written` | 跨线程 callback wake。 |
| `ResolutionRefreshWorker` inline `observe_anchor_prices()` | 一个 worker 代写另一个 worker 的事实。 |
| `ResolutionRefreshWorker` inline `rebuild_token_radar_windows()` | 破坏 `token_radar_rows` 单 writer。 |
| `_start_threaded_async_worker` for pulse | 独立 event loop 造成 shutdown/cancel 复杂度。 |
| `dex_ws_enabled` flag | 过渡开关；改为 credentials + capability 自检测。 |
| 前端 `liveMarketUpdates[0]` patch | 丢中间帧且重复合并。 |
| 三处 `isDexMarket` | 重复业务谓词。 |
| 旧 `anchor_price` / `live_market` API fallback | 新 schema 是唯一 public contract。 |

### 8.7 R 项映射

| R 项 | hard cut 后归属 |
|---|---|
| R1 / R6 / R11 | `MarketObservation` + `MarketContext(event_anchor, decision_latest)` + 删除 overlay。 |
| R2 / R4 | Provider capability router + 删除 `dex_ws_enabled`。 |
| R3 | GMGN WS identity-only doc/test；GMGN OpenAPI quote 仍是 market fact source。 |
| R5 / R9 | WS connection state + snapshot gate outcome metrics；不强行套一个万能状态机。 |
| R7 / R10 | LISTEN/NOTIFY wake hint + periodic catch-up + 主 loop pulse task。 |
| R8 | insufficient/all-tied cohort 返回 no-signal。 |
| R12 / R13 | 前端单 cache/store + domain helper。 |

### 8.8 成功状态

- `token_radar_rows.factor_snapshot_json.market` 只有新 schema：`event_anchor`、`decision_latest`、`readiness`。
- `/api/token-radar` 不再构造 `live_market` overlay；Signal Pulse 与 UI 读到同一份 market context。
- `token_radar_rows` 只有一个 writer worker；resolution refresh 不再 inline projection。
- live market facts 不只存在于 `LivePriceGateway._cache`；它们进入可被 projection 重放/读取的 observation stream。
- `make check-all`、projection rebuild、HTTP/WS/UI smoke 全部通过后，旧 derived rows 被重建，不保留旧读路径。

## 9. 收益估算

### 9.1 按业务指标

| hard cut | 指标 | 现状 | 目标 |
|---|---|---|---|
| MarketContext schema | `factor_snapshot.market.decision_latest.holders` 非 NULL 比例（1h 内 DEX rows） | 0% | ≥ 50% |
| DEX gates fail-closed | trade_candidate 在 pulse_candidates 占比（1h 内） | 100% (27/27) | ≤ 50% |
| Wake hint + projection | live update p99 延迟（fact write → read model visible） | next refetch (≤10s) | < 500ms |
| Provider capability routing | OKX CEX ticker 调用频率（每 token 每分钟） | ≥ 12 次（双采） | ≤ 2 次（单采） |
| One writer | `token_radar_rows` writer worker 数 | 2 | 1 |
| Cohort no-signal | `normalization.cohort_status="insufficient"|"all_tied"` 比例 | 0% | 真实比例 > 0% |
| Main-loop pulse | graceful shutdown 时间 p95 | ~60s（poll 边界 + LLM 调用） | < 5s |
| Frontend single cache | token-radar API/cache 源数 | 2（store + page direct） | 1 |
| No compatibility layer | `_overlay_live_market` / old `live_market` fallback grep | 存在 | 0 结果 |

### 9.2 按抽象数量（核心收益）

**hard cut 的价值不在于代码总量，而在于事实源与读模型的边界变少。**

| 维度 | 现状 | 目标 | 减少幅度 |
|---|---|---|---|
| 市场事实类型 | 4（anchor / live / overlay / projection-market） | 1（MarketObservation） | -75% |
| 市场时间角色 | 隐式混合 | 2 个显式角色（event_anchor / decision_latest） | 明确化 |
| Worker 协调模式数 | 3（callback / inline / poll） | 1（NOTIFY hint + catch-up） | -67% |
| `token_radar_rows` writer 数 | 2 | 1 | -50% |
| 跨线程边界数 | 2（AnchorPrice→Projection event 跨线程；PulseCandidate 独立 loop） | 0 | -100% |
| API/UI market 合并位置 | 3（projection / API / web） | 1（projection read model） | -67% |

### 9.3 按代码体量

**删除**：

| 项 | 行数 |
|---|---|
| `AssetFlowService._overlay_live_market` + 测试 | ~80 |
| `dex_ws_enabled` flag + 散布 conditional | ~30 |
| `ResolutionRefreshWorker` 内联 `rebuild_token_radar_windows` + `observe_anchor_prices` | ~50 |
| `PulseCandidateWorker` 独立线程包装（`_start_threaded_async_worker`） | ~80 |
| `on_observations_written` callback 链 + `_wake_event` 跨线程 set | ~30 |
| 旧 `anchor_price` / `live_market` public fallback | ~50 |
| `isDexMarket` 重复 2 处 | ~20 |
| snapshot gate `public_broadcast` 死代码 | ~15 |
| `factor_snapshot.market` anchor_* / live_* 分裂 schema | ~40 |
| **删除合计** | **~395** |

**新增**：

| 项 | 行数 |
|---|---|
| `MarketObservation` + `MarketContext` 类型与 mappers | ~120 |
| Provider-level capability router / health/cache wrappers | ~120 |
| LISTEN/NOTIFY wake hint + catch-up loop | ~90 |
| WS connection state + snapshot gate outcome metrics | ~70 |
| cohort_size 门槛 + 全员同分检测 | ~30 |
| 前端 per-frame callback + single cache path | ~70 |
| **新增合计** | **~500** |

**净变化：约 +100 行**。可接受，因为删除的是重复合并/重复 writer，新增的是显式事实模型与可观测 wake。

> 关键洞察：这不是为了少写代码，而是为了让每一行代码只属于一个角色：fact write、wake hint、projection、query、surface、UI。复杂度下降来自角色边界，而不是 diff stat。

### 9.4 业务逻辑变化

业务规则不变，public contract 会 hard cut：

- token identity、provider 角色划分、社交因子、ranking 公式主体不变。
- API / WS / frontend market payload 改为 `market.event_anchor` + `market.decision_latest`。
- Signal Pulse 不再读与 UI 不同的 market 世界。
- DEX floor 缺失从 risk 改为 blocker；这是业务正确性修复，不是新 alpha。

## 10. Out of Scope

- 不改 cohort 归一化排序算法主体；只改 insufficient/all-tied 边界语义。
- 不动 `2026-05-12-gmgn-dex-market-provider-split-cn.md` 已批准的 provider 角色划分（GMGN exact-address quote/profile/candle、OKX discovery/CEX/DEX-live）。
- 不引入新 provider（DEX Screener / Birdeye / Jupiter）
- 不引入 Kafka / Redpanda / NATS 等独立 event bus；Postgres `LISTEN/NOTIFY` 只作为 wake hint。
- 不动 LLM agent prompt（HC5 G3 范围）
- 不动 `pulse_agent_runs.request_json` 持久化（HC5 G4 范围）
- 不动 schema 迁移工具链
- 不动前端 routing 结构（`/search` / `/token/:tt/:tid` 保留）
- 不动 closed_loop_harness / notifications / account_quality 域（本 spec 只覆盖 Token Radar 主链）
- 不动 GMGN Direct WS 协议层（重连 / 订阅）；只加可观测状态/outcome。
- 不删 `token_radar_rows` 物化表（forward-return settlement 依赖它；query-time view 是另一份 spec）

## 11. 风险与权衡

### 11.1 hard cut 引入的新风险

| 风险 | 严重度 | 缓解 |
|---|---|---|
| **read model truncate/rebuild 窗口**：不保留旧 schema 兼容，部署期间 Token Radar / Pulse 可能短暂 pending | 高 | 维护模式窗口；先迁移与测试，再 truncate derived rows，最后立即 rebuild hot windows。 |
| **`MarketObservation` as-of/latest 查询性能**：需要按 `(subject_type, subject_id, observed_at_ms DESC)` 命中索引 | 中 | 复用/补齐索引；计划里加入 explain/benchmark 验证。 |
| **LISTEN/NOTIFY 丢消息** | 中 | NOTIFY 只作为 wake hint；projection/pulse 保留 periodic catch-up cursor。 |
| **live facts 写入 DB 后 OKX 配额/写放大** | 高 | subscription_limit + per-target debounce；只写 changed/ttl-expired observations。 |
| **DEX fail-closed 过早导致输出清零** | 高 | 同一个 hard cut 中先接通 `decision_latest` fill，再启用 fail-closed；验证 fill rate 后才完成。 |
| **前端 schema breaking change** | 中 | 同 PR 更新 `web/src/api/types.ts`、store、components；删除旧 fallback 测试并新增新 contract 测试。 |
| **历史 settlement 读取旧 rows** | 中 | 不保留旧 row 兼容；部署时清空/重建 derived rows，settlement 对新 `projection_version` 运行。 |

### 11.2 必须遵守的部署顺序

本次按**一个 plan、一个 hard cut、多个 commit/task**执行，不拆成多个兼容 PR。顺序如下：

```
1. 建立目录/文件角色标记与 architecture docs。
2. 建立 `MarketObservation` / `MarketContext` 与 repository 查询。
3. 写入端统一 observation facts；live facts 不再只存在内存。
4. Projection 切新 schema；删除 API overlay 和旧 snapshot fallback。
5. Worker wake 改成 NOTIFY hint + catch-up；删除 inline/callback/thread。
6. Scoring fail-closed + cohort no-signal。
7. Frontend 切单 cache / per-frame update / 新 market contract。
8. Migration hard cut：truncate/rebuild derived read models。
9. `make check-all` + local seeded DB + API/WS/UI smoke。
```

计划文件必须把以上 9 步拆成可执行任务；每个任务可单独 commit，但最终只在全链路验证通过后合并。

### 11.3 其他权衡

- **现有 trade_candidate 历史信号下游的语义连续性**：bump `projection_version + factor_version`；notification / outcome 表加 `schema_version` 标。
- **OKX adapter 引入 rate limit budget 后短期效率下降**：当前是各 client 自己撞墙；adapter 后是统一调度。调度初版可能保守，2 周后调参。

## 12. 验证标准（端到端）

部署 R1-R13 后，应满足：

### 12.1 数据流验证

```sql
-- 1. factor_snapshot.market.{mcap,liq,holders} 非 NULL 比例
SELECT
  COUNT(*) FILTER (WHERE factor_snapshot_json->'market'->>'holders' IS NOT NULL) * 1.0 / NULLIF(COUNT(*),0) AS holders_fill_rate
FROM pulse_candidates
WHERE updated_at_ms > (EXTRACT(EPOCH FROM NOW()) - 3600)*1000;
-- 目标: >= 0.50（OKX DEX WS 启用后，hot 84 + CEX 16 覆盖大部分）

-- 2. trade_candidate 占比
SELECT pulse_status, COUNT(*)
FROM pulse_candidates
WHERE updated_at_ms > (EXTRACT(EPOCH FROM NOW()) - 3600)*1000
GROUP BY pulse_status;
-- 目标: trade_candidate < 50%; token_watch + blocked + risk_rejected_high_info > 50%

-- 3. factor_snapshot.market.market_data_source 分布
SELECT
  factor_snapshot_json->'market'->>'market_data_source' AS source,
  COUNT(*)
FROM token_radar_rows
WHERE computed_at_ms > (EXTRACT(EPOCH FROM NOW()) - 3600)*1000
GROUP BY source;
-- 目标: live > 0; anchor_only > 0; null/缺失 = 0

-- 4. cohort 无信号比例（normalization.cohort.size < 10 OR all-tied）
SELECT
  COUNT(*) FILTER (WHERE factor_snapshot_json->'normalization'->>'cohort_status' = 'insufficient') * 1.0
  / NULLIF(COUNT(*),0) AS insufficient_cohort_rate
FROM token_radar_rows
WHERE computed_at_ms > (EXTRACT(EPOCH FROM NOW()) - 3600)*1000;
-- 目标: 真实比例 > 0%（不再永远 100% 归一化）
```

### 12.2 健康信号 / metric

- `/api/status.market_providers[*].state` 暴露 OKX/GMGN WS 当前状态，告警基于此（替代原本散布的 `live_price_gateway.dex_ws.state` 等）
- `metrics.market_provider.transition.*` 全部状态切换有 metric
- `metrics.okx_provider.quota_used_pct` < 50%
- `metrics.market_observation.latest_fill_rate` > 50%（DEX live/fresh 路径命中率）
- `metrics.listen_notify.lag_ms` p99 < 100ms（NOTIFY 发出到 LISTEN 端处理）
- `metrics.snapshot_gate.outcome{outcome="DEBOUNCED_TIMEOUT"}` / 总 < 5%

### 12.3 代码体量 / 抽象数量

- `git diff --stat` 显示删除旧合并/writer 路径，新增集中在 fact model、wake hint、projection schema、UI cache。
- 测试覆盖 WS connection state 与 snapshot gate outcome。
- 测试覆盖 `MarketObservation` latest/as-of 时间边界（at_ms 早于/等于/晚于 latest observation）。
- 测试覆盖 provider capability router 缺失 capability 时的错误语义。
- `tests/test_src_domain_architecture.py::test_cross_domain_imports_use_interfaces` 把 evidence→asset_market 这条边加进检测（C1 违规消除）
- `grep -r "_overlay_live_market" src/ web/` 返回 0 结果
- `grep -r "anchor_price_usd\|live_market_usd" src/ web/` 仅剩 migration / backfill / docs，不在 runtime fallback。

### 12.4 回归

- 用最近 1h 的 27 个 trade_candidate 做 backtest：在新版下应有 ≥ 30% 降级为 token_watch 或 blocked
- live update p99 端到端延迟（采集 → 前端可见）< 500ms
- graceful shutdown p95 < 5s
- `dex_ws_enabled` flag 移除后，OKX DEX WS 仍能根据 credentials + capability 自动启用。
- `/api/status` 能看到 OKX/GMGN WS state、projection listener health、market observation fill rate。

## 13. Open Questions

1. **live observations 是否全部持久化**：倾向 yes，并用 per-target debounce / changed-only 写入控制写放大；否则 projection 仍然无法完全重放。
2. **`decision_latest` freshness 阈值**：DEX/ CEX 是否共用 60s live、300s fresh、>300s stale？倾向先共用，再用数据调参。
3. **NOTIFY vs outbox 表**：倾向 LISTEN/NOTIFY + catch-up 起步；如果需要审计每条 wake，再升级 outbox。
4. **cohort 门槛 N**：10 是初始值，需要 backtest；但 all-tied 必须立即返回 no-signal。
5. **C1 evidence→asset_market 编译期依赖**：本 hard cut 先不扩大到 evidence 写入编排；只把新增 market 读写接口放在 `asset_market.interfaces` 可引用边界内。

## 14. 参考数据点（2026-05-13）

| 指标 | 真实值 | 来源 |
|---|---|---|
| service 模式 worker 总数 | 10 | `app/runtime/app.py` 启动表 |
| 采集源数（GMGN + OKX） | 5（GMGN WS / GMGN REST / OKX search / OKX CEX / OKX DEX WS） | 本 spec §2 |
| token_radar 写入 worker 数 | 2（ProjectionWorker + ResolutionRefreshWorker inline） | resolution_refresh_worker.py:207 |
| anchor/live 真相源数 | 2（DB persisted + in-memory gateway） | live_price_gateway.py:295 |
| factor_snapshot.market 合并位置数 | 3（projection `_market()` + API `_overlay_live_market` + 前端 `patchTokenRadarLiveMarketUpdate`） | 本 spec §4.2 |
| 隐式状态机数 | 5（OKX WS / GMGN WS / snapshot gate / live_market.status / projection rebuild） | 本 spec §6 |
| 跨域硬违规数 | 1 高 + 1 中 + 2 低 | 本 spec §7 |
| dex_ws_enabled 默认值 | false | settings.py:297 |
| 工作区未提交修改 | 4（dex_ws_client.py + live_price_gateway.py + 2 tests） | git status |
| 24h pulse_candidates.market.holders NULL 比例 | 100% | HC5 spec § 11 |
| 最近 1h trade_candidate 占比 | 100% (27/27) | HC5 spec § 11 |
| 半完成 hard cut spec 数 | 5（HC1-HC5） | 本 spec §5 |
| target state 后净代码变化 | 约 +100 行（删除重复合并/writer，新增事实模型/wake/projection schema） | 本 spec §9 |
| target state 后核心边界 | raw facts → projection read model → query/surface/UI | 本 spec §8 |
| target state 后 R 项消除映射 | 13 → 0（Kappa/CQRS hard cut + 目录角色标记 + 删除旧路径） | 本 spec §8.7 |

## 15. 一句话给下一个 spec writer

> 本 spec 是**诊断 + Kappa/CQRS hard cut 目标架构**。§4 列 13 个具体绕路点，§8 给出事实源、读模型、目录标记、必删路径和 R 项映射。实施时写一份 single-plan hard cut：不保留旧 `factor_snapshot.market` / `anchor_price` / `live_market` 兼容路径，保留 raw facts，truncate/rebuild derived read models。最重要的两条戒律：(a) `event_anchor` 与 `decision_latest` 是两个时间角色，不能再混成一个 market；(b) `LISTEN/NOTIFY` 只是 wake hint，正确性必须来自 DB facts + projection catch-up。
