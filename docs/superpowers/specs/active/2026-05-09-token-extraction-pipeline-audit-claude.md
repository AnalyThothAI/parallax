# Spec — Token 提取链路审计与最小手术

**Status**: Draft
**Date**: 2026-05-09
**Owner**: aaurix（与 Claude Code Opus 4.7 协作）
**Related**: `docs/superpowers/specs/2026-05-08-auditable-token-radar-design-cn.md`、`docs/superpowers/plans/2026-05-06-token-identity-resolution-production.md`、`docs/superpowers/specs/2026-05-04-token-posts-evidence-scoring-design.md`

---

## TL;DR · 一句话结论

**Token 提取代码本身已经是生产级别（95.92% 解析率，registry 无重复）。剩下 10% 失败的根因是两个 worker 之间缺一个"真正被引用"过滤器：`TokenDiscoveryWorker` 为了 dominance 选择，必然把每个新 symbol 的所有跨链候选（HANTA 一次 608 个）拉进 registry；`asset_market_sync_worker` 然后无差别按"最旧观测"轮询全 registry，14,303 资产 / 80 名额每 5min = 14.7 小时一轮，把 36% 名额浪费在 5,114 个从未被任何推文引用过的 orphan 上。修复路径是双层手术：(1) `asset_market_sync_worker` 改成只刷"被 token_intent_lookup_keys 或 candidate_ids 引用过的资产"并按 1h/24h/ever 三档优先级排序 + limit 提到 200，能把 1h-active 资产刷新周期缩到 17 分钟；(2) resolver 双档 freshness（FRESH ≤ 5min / STALE ≤ 4h），让暂时滑出 fresh 窗口的候选仍能完成身份解析、下游接 stale_market cap。OKX API 不是瓶颈（search 命中率 99.76%），价格绑定写入逻辑不是 bug，token 表也不存在重复——问题在两个 worker 的责任划分。**

---

## 1. Background · 背景与现状审计

本审计覆盖 token 提取链路：从 Twitter 事件进入 collector，到一条 `token_intent_resolutions` 行被下游 radar / timeline / alerts 消费。穿过四层：实体抽取、intent 构造、决定性解析、asset 市场同步，以及消费它们的 projection 评分。所有现状声明都基于代码（`file:line`）和 2026-05-09 05:35–06:35 UTC 这一小时本机 PostgreSQL 真实流量。

### 1.1 模块清单

| 阶段 | 文件 | 职责 |
|------|------|------|
| 实体抽取 | `src/gmgn_twitter_intel/pipeline/entity_extractor.py`（正则识别 EVM/Solana/TON CA、cashtag、hashtag、mention、URL、domain）| 把推文 surface 切成带 span 锚点的强类型实体 |
| 证据 | `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py` | CA → strong / cashtag → medium / gmgn_payload → strong |
| Intent | `src/gmgn_twitter_intel/pipeline/token_intent_builder.py`（display alias 配对）| 证据聚合成 intent，键为 `ca:chain:addr` 或 `symbol:NORM` |
| 解析 | `src/gmgn_twitter_intel/pipeline/token_intent_resolver.py` + `deterministic_token_resolver.py`（`MentionKeys` → `DeterministicResolution`）| Intent 落到 `EXACT / UNIQUE_BY_CONTEXT / AMBIGUOUS / NIL` 之一，附带 `reason_codes`、`candidate_ids`、`lookup_keys` |
| Registry | `src/gmgn_twitter_intel/storage/registry_repository.py`（`registry_assets`、`cex_tokens`、`price_feeds`、`price_observations`）| 身份与最新观测查询 |
| 同步 | `src/gmgn_twitter_intel/pipeline/asset_market_sync.py` + `asset_market_sync_worker.py` | OKX CEX universe + OKX DEX search/price 刷新 |
| 重解析 | `src/gmgn_twitter_intel/pipeline/token_resolution_refresh.py` + `token_intent_rebuild.py` | lookup-key 驱动的滚动再决策 |
| 编排 | `src/gmgn_twitter_intel/pipeline/ingest_service.py:62-148` | 单事务 9 表 5 仓 |
| 评分 | `src/gmgn_twitter_intel/pipeline/token_radar_feature_builder.py` + `token_radar_projection.py` + 6 个 `retrieval/*_scoring.py` | v5 六个 score block，hard-cut 已落地 |

### 1.2 数据流与状态机

```
Twitter ws → events ───────────────────────────────────────────────┐
                │                                                   │
                ▼                                                   ▼
        extract_entities  ─►  build_token_evidence  ─►  build_token_intents
                                                                    │
                                                                    ▼
                       ┌────────────────────────────────────────────┴─────┐
                       │ DeterministicTokenResolver.resolve               │
                       │   keys: symbol / chain+addr / addr / pricefeed   │
                       │   ↓ 分支                                          │
                       │   • cex_pricefeed   →  EXACT (CexToken)          │
                       │   • chain+address   →  EXACT (Asset)             │
                       │   • address-only    →  UNIQUE/AMBIGUOUS          │
                       │   • symbol          →  cex_token? / fresh? /     │
                       │                        dominance? / stale? / NIL │
                       └────────────────────┬─────────────────────────────┘
                                            ▼
                  写 token_intent_resolutions (is_current=true)
                  替换 token_intent_lookup_keys
                  写 account_token_alerts（watched 且已解析时）
                  入队 enrichment_jobs（watched 且 priority 命中时）
                                            ▼
                ────────── 全部在一个事务里 ──────────
                                            │
                                            ▼
                  AssetMarketSyncWorker（每 300s）
                    ├── okx_cex_universe        → cex_tokens + price_obs
                    ├── okx_dex_search/price    → registry_assets + price_obs（limit=80）
                    └── refresh_recent_token_state(lookup_keys)
                                            ▼
                  TokenRadarProjection.rebuild
                    → build_radar_features → 6 个 score block → opportunity decision
                    → token_radar_rows.projection_version = "token-radar-v5-auditable"
```

Symbol 解析分支的状态机：

```
                       ┌──── EXACT ─── chain+addr 命中 registry / cex_pricefeed
intent {pending} ─►   │
                       ├──── UNIQUE_BY_CONTEXT ─── 已确认的 cex_token
                       │                       └── 唯一 fresh 链上资产
                       │                       └── market-dominant fresh 链上资产
                       │                       └── 跨链地址唯一
                       ├──── AMBIGUOUS ─── 多资产无 dominance
                       │                  跨链地址多匹配
                       └──── NIL ────── symbol 不在 registry / 候选全 stale / cex_pricefeed 缺失
```

### 1.3 11 个硬编码阈值

| 常量 | 值 | 来源 | 作用 |
|---|---|---|---|
| `FRESH_OBSERVATION_MS` | 20 min | `deterministic_token_resolver.py:10` | symbol 候选若最新 observation 早于此就被排除 |
| `MIN_DOMINANT_MARKET_CAP_USD` | 250,000 | `deterministic_token_resolver.py:11` | 三低 OR 阈值之一 |
| `MIN_DOMINANT_HOLDERS` | 1,000 | `deterministic_token_resolver.py:12` | 同上 |
| `MIN_DOMINANT_LIQUIDITY_USD` | 100,000 | `deterministic_token_resolver.py:13` | 同上 |
| `MAX_AUDIT_CANDIDATE_IDS` | 20 | `deterministic_token_resolver.py:14` | candidate_ids 截断 |
| dominance 权重 | 0.55·log10(mcap+1) + 0.30·log10(holders+1) + 0.15·log10(liq+1) | `deterministic_token_resolver.py:353-358` | 排序键 |
| `DEX_PRICE_STALE_MS` | 5 min | `asset_market_sync_worker.py:13` | 资产「需刷新」边界 |
| `DEX_PRICE_REFRESH_LIMIT` | 80 | `asset_market_sync_worker.py:14` | 每 tick DEX 价格刷新上限 |
| `interval_seconds` | 300 | `asset_market_sync_worker.py` | worker tick |
| `MARKET_FRESH_MS` | 5 min | `token_radar_projection.py:28` | radar `market_status="fresh"` 边界 |
| `public_only_unconfirmed` cap | 68 | `retrieval/opportunity_scoring.py:38-39` | 当 `public_stream_coverage` 风险存在且无 watched 确认时 |

### 1.4 真实数据账本（1h，2026-05-09 05:35–06:35Z）

方法：本机 PostgreSQL `SELECT` 只读，`received_at_ms BETWEEN now-1h AND now`。SQL 见附录 A。样本量：3,758 events / 696 token_intents / 3,583 current resolutions / 14,123 registry chain assets / 12,568 fresh price observations。

**吞吐**

| 指标 | 值 |
|---|---|
| events | 3,758 |
| watched events | 43 (1.14%) |
| 含 token intent 的 events | 515 / 3,788 (14%) |
| 同事件 ca+symbol（display alias 候选）| 41 / 515 (8.0%) |
| ca-only events | 258 / 515 (50.1%) |
| symbol-only events | 216 / 515 (41.9%) |
| token_intents — ca | 348 |
| token_intents — symbol | 348 |
| 唯一 ca intent_keys | 184 |
| 唯一 symbol intent_keys | 181 |

**Resolution 状态分布**

| status | n | pct |
|---|---|---|
| UNIQUE_BY_CONTEXT | 2,645 | 73.82% |
| EXACT | 792 | 22.10% |
| AMBIGUOUS | 84 | 2.34% |
| NIL | 62 | 1.73% |

**Top reason codes**

| reason | n | status |
|---|---|---|
| MARKET_DOMINANT_CHAIN_ASSET | 1,824 | UNIQUE_BY_CONTEXT |
| CHAIN_ADDRESS_EXACT | 792 | EXACT |
| CONFIRMED_CEX_TOKEN | 586 | UNIQUE_BY_CONTEXT |
| SINGLE_ACTIVE_CHAIN_ASSET | 118 | UNIQUE_BY_CONTEXT |
| ADDRESS_UNIQUE_ACROSS_TRACKED_CHAINS | 117 | UNIQUE_BY_CONTEXT |
| NO_MARKET_DOMINANT_CHAIN_ASSET | 71 | AMBIGUOUS |
| **SYMBOL_CANDIDATES_STALE** | **35** | **NIL** |
| SYMBOL_NOT_IN_REGISTRY | 17 | NIL |
| ADDRESS_EXISTS_ON_MULTIPLE_CHAINS | 13 | AMBIGUOUS |
| ADDRESS_NOT_IN_REGISTRY | 10 | NIL |

**Symbol-only 348 个 intent 的归宿**

| reason | n | 占比 |
|---|---|---|
| MARKET_DOMINANT_CHAIN_ASSET | 146 | 42.0% |
| CONFIRMED_CEX_TOKEN | 107 | 30.7% |
| SYMBOL_CANDIDATES_STALE | 35 | 10.1% |
| SINGLE_ACTIVE_CHAIN_ASSET | 30 | 8.6% |
| SYMBOL_NOT_IN_REGISTRY | 17 | 4.9% |
| NO_MARKET_DOMINANT_CHAIN_ASSET | 13 | 3.7% |

**STALE 候选决策时刻的实际年龄（35 笔 NIL，317 个候选行）**

| 百分位 | decision_time − last_observed | 含义 |
|---|---|---|
| min | 21 min | 刚踩过 20min 线 |
| p10 | 31 min | 偶尔踩线 |
| p50 | 6.8 h | **绝大多数候选已 6+ 小时无观测** |
| p90 | 24.2 h | 一天没刷 |
| p95 | 37.5 h | 一天半没刷 |
| max | 40.4 h | 接近两天 |

**放宽窗口能救回多少（按 intent 最优候选年龄）**

| 窗口 | 救回 intents | 占比 |
|---|---|---|
| ≤ 30 min | 5 / 38 | 13.2% |
| ≤ 60 min | 16 / 38 | 42.1% |
| ≤ **4 h** | **21 / 38** | **55.3%** |
| ≤ 24 h | 36 / 38 | 94.7% |

**Registry 实际 fresh 比例**

| chain | 资产数 | 无观测 | >20min stale | >5min stale | ≤5min fresh |
|---|---|---|---|---|---|
| solana | 9,806 | 270 | 9,239 | 9,495 | 41 |
| eip155:56（BSC）| 2,240 | 13 | 2,125 | 2,209 | 18 |
| eip155:1（ETH）| 1,085 | 63 | 966 | 1,011 | 11 |
| eip155:8453（Base）| 807 | 36 | 752 | 767 | 4 |
| ton | 182 | 30 | 150 | 152 | 0 |
| tron | 3 | 0 | 3 | 3 | 0 |
| **合计** | **14,123** | **412** | **13,232（93.7%）** | **13,634（96.5%）** | **74（0.5%）** |

**Price observation 1h 内吞吐**

| kind / provider | n |
|---|---|
| refresh / okx_cex | 11,004 |
| refresh / okx_dex_search | 1,528 |
| **refresh / okx_dex_price** | **30** |
| message_quote / okx_dex_price | message-level quote worker owns this path |

**Symbol 跨链碰撞 top 10（registry 内）**

| symbol | 候选数 | 链数 |
|---|---|---|
| HANTA | 608 | 5 |
| UAP | 268 | 3 |
| VIRUS | 181 | 3 |
| ELIEN | 112 | 3 |
| UFO | 104 | 4 |
| HANTAVIRUS | 100 | 3 |
| NOROVIRUS | 96 | 2 |
| SATO | 93 | 4 |
| SPACEXAI | 92 | 4 |
| JAVIER | 87 | 2 |

**Dominance margin 边缘 case**

按 (top_score − second_score) 升序，log10 加权单位：

| symbol | 候选数 | top | second | margin | top mcap | top holders |
|---|---|---|---|---|---|---|
| CRMX | 3 | 2.9948 | 2.9948 | 0.0000（→ AMBIGUOUS）| 278,658 | null |
| **CELIA** | **3** | **2.1278** | **2.1277** | **0.0001（当前判赢）** | **4,055** | **2** |
| **AIPANDA** | **3** | **2.1273** | **2.1271** | **0.0002（当前判赢）** | **4,047** | **2** |
| SCRIBBLI | 3 | 4.0153 | 4.0142 | 0.0011 | 41,194 | 570 |
| TRACKHANTA | 58 | 5.0092 | 5.0061 | 0.0031 | 6,552,857 | 129 |

**Dominance 优胜者质量（520 个 distinct winners / 1h）**

| 指标 | n |
|---|---|
| 三字段全低（mcap<250k AND holders<1k AND liq<100k）| 0 |
| mcap < 50k | 0 |
| holders < 100 | 33 (6.3%) |
| liquidity < 10k | 16 (3.1%) |
| mcap ≥ 250k | 511 (98.3%) |

**Token-radar 决策分布（1h projection runs）**

| window | scope | discard | watch | driver |
|---|---|---|---|---|
| 1h | all | 248 | 24 | 0 |
| 1h | matched | 0 | 2 | 0 |
| 4h | all | 100 | 100 | 0 |
| 24h | all | 100 | 100 | 0 |
| 24h | matched | 20 | 68 | 0 |

**account_token_alerts（watched 路径，1h）**：2 笔 alert，1 first_seen_by_author，0 first_seen_global。

---

## 2. Problem · 问题本质

### 2.1 实际的两-worker 配合（修订后）

token 提取链路其实是**两个 worker + 一个 sync 服务**协作的：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 推文 $HANTA 进来                                                    │
│                                                                     │
│ ① IngestService (sync, in-request)                                  │
│   - 创建 symbol:HANTA token_intent                                  │
│   - 写 token_intent_lookup_keys "symbol:HANTA"                      │
│   - 仅当推文里有 CA 时 upsert_chain_asset (source=tweet_ca)         │
│                                                                     │
│ ② TokenDiscoveryWorker (每 30s tick)                                │
│   读 due lookup_keys → dex_client.search_tokens(query="HANTA",      │
│       chain_indexes=("501","1","56","8453","607"))                  │
│   → OKX 返回 608 个跨链 HANTA 候选                                  │
│   → 对每个 candidate: upsert_chain_asset(source="okx_dex_search")   │
│       + write price_observation                                     │
│   → registry 一次膨胀 +608 行                                       │
│   ※ spam 入库的真正源头在这一步，但它是 dominance 必需的            │
│                                                                     │
│ ③ asset_market_sync_worker (每 300s tick)                           │
│   chain_assets_needing_price_refresh: 按 observed_at_ms ASC LIMIT 80│
│   完全不读 token_intent_lookup_keys，对 14k 资产无差别轮询           │
│   → 14,303 / 80 / 5min = 14.7 小时一轮                              │
│   → 36% 名额浪费在 5,114 个 orphan（从未被任何推文 mention 也未作为 │
│      candidate）上                                                   │
│                                                                     │
│ ④ DeterministicTokenResolver (sync, in-request, 在 ① 内)            │
│   find_assets_by_symbol_with_latest_observation("HANTA")            │
│   filter to fresh ≤20min                                            │
│   → 14k / 14.7h 轮转下，绝大多数候选 stale                          │
│   → 一刀切 SYMBOL_CANDIDATES_STALE / NIL                            │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 真实数据印证

| 指标 | 1h | 24h | 7d/ever | 全 registry |
|---|---|---|---|---|
| 推文真正 mention 选中的资产 (`target_id`) | 187 | 2,720 | 4,594 | — |
| 含 dominance 候选 (`target_id ∪ candidate_ids`) | **669** | 6,192 | **9,189** | — |
| Orphan（从未引用 / 候选） | — | — | — | **5,114（36%）** |
| Registry 总量 | — | — | — | **14,303** |

**Mention 频率分布（24h 内 2,720 个 active 资产）：**
- 1,331 个 singleton（48.9%）
- 910 个 mention 2-5 次（33.5%）
- 368 个 mention 6-20 次（13.5%）
- 111 个 mention >20 次（4.1%）

**不同刷新策略下的轮询周期：**

| 策略 | 候选池大小 | 80 limit / 5min | 200 limit / 5min |
|---|---|---|---|
| **现状（全 registry）** | 14,303 | **14.7h** | 5.9h |
| 排除 orphan（only ever-referenced） | 9,189 | 9.6h | 3.8h |
| 仅 24h 引用过 | 6,192 | 6.5h | 2.6h |
| **仅 1h 引用过** | 669 | 0.7h | **0.28h ≈ 17min** |
| 仅 1h target | 187 | 0.2h | 5min |

→ **配合 limit=200 + 仅刷 1h-引用资产，刷新周期能从 14.7h 缩到 17 分钟**，远低于任何合理的 fresh 窗口。

### 2.3 三层根因（修订）

**L1 · 两-worker 责任划分错位（最严重，真正的根因）**
- `TokenDiscoveryWorker` 必须把所有 OKX 同 symbol 候选拉进 registry——dominance 选择需要候选集（HANTA 608 个跨链候选不可少）
- 但 `asset_market_sync_worker` 不应该把这些 spam 候选当一等公民和"被推文引用过"的资产平等轮询
- 当前 `chain_assets_needing_price_refresh` 仅按 `observed_at_ms ASC` 排序，完全不读 `token_intent_lookup_keys` 和 `token_intent_resolutions.candidate_ids`
- 后果：14,303 资产 / 80 名额每 5min = 14.7h 轮一遍；36% 名额浪费在 orphan；真正 active 的 669 个（1h 内被引用过）只能等

**L2 · resolver 强求 fresh，无降级路径（次严重，把 L1 放大成 NIL）**
- `deterministic_token_resolver.py:10` `FRESH_OBSERVATION_MS = 20min` 是硬过滤。
- `_fresh()` 把超时候选直接丢出 active set。
- active set 空 → `_resolve_symbol` 落 `SYMBOL_CANDIDATES_STALE / NIL`。
- **关键设计错误**：候选身份信息明明在 registry 里完整，仅价格观测过期就丢候选，等于把"身份解析"和"价格新鲜度"硬绑死。Stale 候选应该可以做 best-effort dominance 选择 + 下游标记 stale_market cap。
- 1h 实测：35 笔 stale NIL 中 p50 候选年龄 6.8h、p95 = 37.5h——并非刚过线，是积压几小时的有效身份信号被抛弃。
- 推论：即使 L1 修好，registry 真有 stale 长尾时（比如所有 worker 临时挂掉），resolver 仍应优雅降级。

**L3 · 工程耦合层（影响小但不修会增加返工）**
- `IngestService.ingest_event` 单事务跨 9 表 5 repo，任何子步骤失败连 `events` 行都丢。
- `token_radar_feature_builder.py` 的 `seed_lag_ms` / `phase_hint` / `lookahead_risk` 永远 None/False，propagation/timing/tradeability 评分静默走默认路径。
- resolver 用 `FRESH_OBSERVATION_MS=20min`、projection 用 `MARKET_FRESH_MS=5min`，两个语义"fresh"对不上。

### 2.4 不是什么（订正）

| 你的怀疑 | 是否成立 | 数据 |
|---|---|---|
| 「消息太多导致管道压不住」 | ❌ 不成立 | 3,758 events/h，无积压队列 |
| 「token 解析代码逻辑错了」 | ❌ 基本不成立 | 95.92% 解析率，dominance 公式正确 |
| 「价格绑定写入有问题」 | ❌ 不成立 | GMGN payload price path 已硬切；消息价格由 `message_quote` worker 负责 |
| 「token 表存在重复（同 ca/chain/大小写）」 | ❌ **不成立** | **0 笔重复**（addr lower、symbol upper、PK on asset_id） |
| 「OKX API 命中率不行」 | ❌ 不成立 | search 写入 1h 837 条，**99.76% 含 price_usd** |
| 「DEX 价格回灌写不动」 | ❌ 不成立（之前我误判）| 实际 1h 写 ~867 条价格观测（search 主路径）；问题在 registry 14k 太大 |
| **「两 worker 责任划分错位」** | **✅ 这是根因** | **9,189 ever-referenced + 5,114 orphan，worker 不区分** |
| **「resolver 强求 fresh 没降级」** | **✅ 把 L1 放大成 NIL** | **35/348 = 10% symbol-only 落 NIL，55% ≤4h 可救** |
| 「dominance 公式选错了」 | ⚠️ 部分成立 | 公式合理，缺 margin gate（CELIA/AIPANDA margin 0.0001 也判赢）|
| 「IngestService 太大」 | ⚠️ 部分成立 | 单事务 9 表，是工程弱点，不是 NIL 根因 |
| 「v5 评分公式有 bug」 | ❌ 不成立 | 6 个 score function 与 spec 一致 |
| 「driver lane 没启用」 | ⚠️ UI 体感 | 0/272 触达是 cap=68 + 门槛 72 binding |

---

## 3. Diagnosis · 八条诊断

每条带 file:line 证据 + 实测 + 文献映射 + 修复方向。

### F1 · resolver 强求 fresh 无降级路径（次严重，把 F4 放大成 NIL）
- **证据**：`deterministic_token_resolver.py:10` `FRESH_OBSERVATION_MS = 20min` 硬过滤；`_resolve_symbol`（line 248-304）在 `active_assets` 为空时一刀落 `SYMBOL_CANDIDATES_STALE / NIL`，**完全无视** `assets`（含 stale 候选的全集）里的有效身份信息。
- **影响**：35 / 348（10%）symbol-only intent 落 NIL；候选年龄 p50 = 6.8h、p95 = 37.5h——不是"刚过线"，是 6+ 小时积压。Resolver 把"身份解析"和"价格新鲜度"硬绑死，丢掉了 registry 里完整存在的身份信息。
- **修复方向**：双档 freshness — `UNIQUE_BY_CONTEXT_FRESH`（≤ MARKET_FRESH_MS）/ `UNIQUE_BY_CONTEXT_STALE`（≤ STALE_OBSERVATION_MS = 4h）/ NIL。stale 在 tradeability 自动加 stale_market cap = 70。
- **文献**：Babcock PODS 2002 stream freshness/completeness tradeoff；Centola Science 2010 long-tail 复杂传染。

### F2 · dominance 没有最小 margin gate（log10 下平局也判赢）
- **证据**：`deterministic_token_resolver.py:317-333` 仅在 `top_score <= second_score` 时拒绝。CELIA margin = 0.0001 / AIPANDA margin = 0.0002 当前判赢，"赢家"分别只有 2 个 holder、~$4k mcap。
- **影响**：跨链 spam token 上 winner 的可重现性差——下次相同候选可能挑到不同 token。
- **修复方向**：`MIN_DOMINANCE_MARGIN = 0.05`（log10 单位 ≈ 12% 倍差），平局走 AMBIGUOUS 并把候选全留在 candidate_ids 里。
- **文献**：Buckley & Voorhees 2004 retrieval 中不可区分分数不能排序。

### F3 · holders-only winner 占 6.3%，无下游审计标记
- **证据**：520 winners → 33 个 holders < 100；即 winner 单靠 mcap 或单靠 liquidity 突破阈值。
- **影响**：holders inflation 是已知 web3 spam 信号，目前没标记让下游降权。
- **修复方向**：`data_health.dominance_signal = "holders_only"`。本期不直接扣分（避免误伤合规小盘），但前端可见。

### F4 · 两-worker 责任划分错位（**真正的根因**）
- **证据**：
  - `TokenDiscoveryWorker._process_dex_symbol_lookup`（`token_discovery_worker.py:222-250`）调 `dex_client.search_tokens(query=symbol, chain_indexes=...)`，把 OKX 上**所有同 symbol 跨链候选**全部 upsert 入 registry；HANTA 一次进 608 行（必要：dominance 选择需要候选集）。
  - `asset_market_sync_worker.py:13-15` 配合 `chain_assets_needing_price_refresh`（`registry_repository.py:268-298`）按 `observed_at_ms ASC` 轮询**全 registry**，**完全不读** `token_intent_lookup_keys`，**也不看** `token_intent_resolutions.candidate_ids`。
  - 1h 数据：14,303 资产 / 80 名额每 5min = **14.7h 一轮**；其中 5,114（36%）是 orphan（从未被任何推文 mention 也未作为候选）；669 个 1h-active 资产被 5,114 个 orphan 拖累等待。
- **影响**：worker 36% 名额浪费在 orphan 上；真正"被推文最近 mention 过"的资产平均要等 14.7h 才能轮一次刷新——这是让 resolver 看到全 stale 候选的根源。
- **修复方向**：
  - `asset_market_sync_worker` 改成只刷"过去 N 天内被 `token_intent_lookup_keys` 或 `token_intent_resolutions.candidate_ids` 引用过的资产"。
  - 三档优先级排序：(1) **Hot** = 1h 内被引用 → 每 tick 必刷 / (2) **Warm** = 24h 内被引用 → 每 30min 刷一次 / (3) **Cold** = ever 引用过但近 24h 没动 → 4-12h 刷一次 / (4) **Orphan** = 从未被引用 → 不进刷新队列（保留 registry 行但不消耗名额）。
  - `DEX_PRICE_REFRESH_LIMIT` 从 80 提到 200。
- **数据预期**：1h-active 669 个资产 / 200 limit / 5min = **17 分钟一轮**；配合 resolver `STALE_OBSERVATION_MS=4h` 完全充足，配合 `MARKET_FRESH_MS=5min` 也接近达标。

### F5 · IngestService 单事务跨 9 表 5 repo
- **证据**：`ingest_service.py:62-148` 一个 `transaction(self.evidence.conn)` 包住 events + event_entities + token_evidence + token_intents + registry_assets + token_intent_resolutions + token_intent_lookup_keys + account_token_alerts + enrichment_jobs。
- **影响**：任意子环节失败（registry 冲突、resolver 输入畸形）会让 events 行也丢失，调试 + retry 粒度受限。
- **修复方向**：A 段（事实必落）/ B 段（决策可重放）两段提交，market observation 完全留给异步 worker。
- **文献**：Garcia-Molina & Salem 1987 Sagas。

### F6 · feature_builder 三个静默死字段
- **证据**：`token_radar_feature_builder.py:232,235`：`seed_lag_ms = None` 和 `phase_hint = None` 永远；`lookahead_risk` 只读不写。
- **影响**：propagation_score 的 `seed_lag` contribution 永远 0；timing_score 的 `chase_risk` 永不触发；tradeability 永不收到 lookahead 风险。"已实现的合约"实际是 ghost。
- **修复方向**：要么按现有 timeline 数据计算（seed_lag = 第一条 watched − 第一条 total；phase_hint = 由 concentration/new-author/duplicate 派生；lookahead_risk = price_at_reference > price_at_first_snapshot × 1.5），要么从 contract 删除。不能保留 None。

### F7 · resolver 与 projection 用不同的 fresh 常量
- **证据**：resolver:10 = 20min；projection:28 = 5min。同一个 token 可在 resolver 看作 fresh，在 radar 看作 stale。
- **影响**：UI 与 resolver 决策不一致，调试困难。
- **修复方向**：统一到一个 `MARKET_FRESH_MS`，stale 用独立常量 `STALE_OBSERVATION_MS`。

### F8 · driver lane 实质死亡
- **证据**：过去 1h 跨 6 个 window×scope 组合全部 0 driver。`opportunity_scoring.py:38-39` 的 `public_only_unconfirmed` cap = 68 是 binding constraint（driver 门槛 72）。
- **影响**：即使 matched scope（仅 watched 事件）也是 0 driver，UI 该区域无内容。
- **修复方向**：当 `propagation.reasons` 含 `watched_seed_link` 时把 cap 放宽到 75（保留 cap 精神，仅在 watched 确认下放松）。其他 gate 不动。
- **文献**：Bakshy WSDM 2011 ordinary-influencer hypothesis 支持 cap 的存在。

---

## 4. First principles · 不可动的契约

- **身份可复盘**：每条 resolution 必须有 `reason_codes` + `candidate_ids` + `lookup_keys` + `decision_time_ms` + `resolver_policy_version`。已被 `intent_resolution_repository.py` 强制。新增 outcome 必须遵守。
- **分数可复盘**：每个 score block 携带 `score_version` + `contributions` + `reasons` + `risks` + `risk_caps` + `data_health`。已被 `retrieval/scoring_common.score_payload` 强制。新增 cap 用同一形状。
- **事件不可变 / 决策可重放**：重解析路径已存在（`token_resolution_refresh.reprocess_recent_token_intents`）；`events` 与 `event_entities` 永远不依赖 resolver 状态。
- **不引入新持久化层（除非有量化痛点）**：AGENTS.md 红线明令；本审计明确量化痛点后只做最小手术。
- **coverage = public_stream**：`events.coverage = 'public_stream'`，下游 payload 不得伪造更广覆盖。

---

## 5. 为什么是这些数 · 阈值定值依据

每个建议值都来自数据，不是拍脑袋。Plan 阶段可调，但定值依据如下：

### 5.1 `STALE_OBSERVATION_MS = 4 h` 的依据

候选年龄分布（35 笔 stale intent）：

| 窗口 | 救回率 | 含义 |
|---|---|---|
| 30 min | 13.2% | 几乎没救——候选大多 30 分钟以上 |
| 60 min | 42.1% | 只能救 4 成 |
| **4 h** | **55.3%** | **一半以上能救，且最旧候选不超过 4 小时** |
| 6 h | ~67%（外推）| 只多救 4 个 intent |
| 24 h | 94.7% | 救最多但 24 小时旧的报价已不可信 |

选 4h 的逻辑：

- **下界（不选 1h 或 30min）**：DEX 真实刷新速率决定大部分 long-tail 在 1h 内必定 stale，1h 窗口下 NIL 仍会高于 6%。
- **上界（不选 24h）**：tradeability_score 的 `stale_market` cap = 70 是按"几小时"量级设计的，24 小时旧的报价让 cap 失去意义；前端用户看到 24h 前的价格也无法做交易判断。
- **甜点**：4h 救回过半，且配合 `data_health.market_freshness_tier=stale_4h` 让下游 + UI 都明确"价格已延迟"。

### 5.2 `MIN_DOMINANCE_MARGIN = 0.05` 的依据

log10 加权空间下 0.05 的实际含义：

- 加权和差 0.05 等价于综合"市值×holders×流动性"组合差异约 12%（10^0.05 ≈ 1.122）。
- 正常 dominance 案例：DEXE margin = 0.014（top mcap 2.8 亿、second 也是 1 亿级）—— 0.014 实际上是 ~3% 倍差，不可信。本期阈值会把 DEXE 也判 AMBIGUOUS，让前端显示候选清单。
- 边际 case：CELIA / AIPANDA / TRACKHANTA 都在 0.0001–0.003 之间，0.05 阈值能把它们全部送进 AMBIGUOUS，避免随机选 winner。
- 实际观测「真正有意义的差距」最低值：从 1h 数据看，>0.05 的 winner 都是有数量级差距的（如 SLOP eip155:1 mcap=2.27M vs Solana mcap=49k → log10 差 ≈ 1.66）。0.05 接近"明显差距"的下界。

### 5.3 `DEX_PRICE_REFRESH_LIMIT = 200` 的依据

- 现状 80 个 / 5min = 960 / h 的额定容量；实际 `okx_dex_search` 写入 837 条/h（99.76% 含 price_usd），所以"价格写入"瓶颈不在 OKX 命中率，而在 worker 限额 / registry 规模。
- registry 14,303 vs 限额 80：现状 14.7h 一轮。
- 配合 F4 修复（仅刷"被引用过"的资产 + 三档优先级排序）的实际刷新需求：
  - 1h-active: 669 个 / 200 limit / 5min = **17 分钟一轮**
  - 24h-active: 6,192 个 / 200 limit / 5min = **2.6h 一轮**
  - 选 200 让 24h-active 也能在 4h 内轮一遍，配合 STALE_OBSERVATION_MS=4h 完美匹配。
- OKX 单批 20 个 DEX 价格请求（`DEX_PRICE_BATCH_SIZE = 20`）保护 provider 限速；200 = 10 批 / tick，可控。
- 不选 500 或更高：`okx_dex_search` 路径每个资产单独发请求，200 已是合理上限；继续提高需要先验证 OKX 端速率限制。

### 5.4 `public_only_unconfirmed` 在 watched_seed_link 下放宽到 75

- 当前 cap = 68，driver 门槛 score ≥ 72 → 永远卡死。
- watched_seed_link 是已经过 watched 作者确认的信号，不是匿名 public stream。把 cap 放到 75 让综合分能踩到 72-75 之间通过门槛。
- 不选 80 或移除 cap：tradeability `stale_market` cap 也是 70 量级，cap 75 让 stale-market token 也踩不到 driver——保留了 stale_market 的保护。
- 不选 70：和 driver 门槛 72 一样的 cap 等价于不放宽。

---

## 6. 修复前后对比（基于 1h 真实数据回放）

### 6.1 解析层

| 指标 | 修复前 | 修复后（预期，基于 1h 数据） | 说明 |
|---|---|---|---|
| symbol-only NIL 比例 | 35/348 = 10.1% | 14/348 ≈ 4% | 21 笔由 NIL 转 STALE-tier，加 stale_market cap |
| symbol-only NIL（除 SYMBOL_NOT_IN_REGISTRY）| 35/348 = 10.1% | ~4% | 排除"完全不在 registry"的结构性 NIL |
| AMBIGUOUS 数 | 84 | 92 ± 5 | CELIA/AIPANDA/SCRIBBLI 等 margin<0.05 case 由 UNIQUE 转 AMBIGUOUS |
| holders-only winners 标记率 | 0% | 100% | 所有 6.3% 的 winner 在 data_health 标 holders_only |
| `UNIQUE_BY_CONTEXT_STALE` | 不存在 | 21 笔 / 1h | 新增的中间档，前端可见 stale_4h 徽章 |

### 6.2 数据通道层

| 指标 | 修复前 | 修复后（预期）| 说明 |
|---|---|---|---|
| Registry 完整轮询周期 | **14.7h** | **17 min**（仅刷 1h-active 669 个 / limit 200）| 主要靠 F4 修复，limit 配合 |
| 1h-active 资产 fresh ≤ 5min 比例 | ~19%（127/669）| **≥ 95%** | 配合 17min 周期 + STALE_OBSERVATION_MS=4h 给宽容 |
| 24h-active 资产 fresh ≤ 4h 比例 | ~27%（1,654/6,192）| **≥ 90%** | 24h 池在 2.6h 内能轮一遍 |
| Orphan 资产 fresh 比例 | 0.04% (2/5,114) | 0%（**不再刷**）| Orphan 退出 worker queue，节省 36% 名额 |
| `okx_dex_search` 写入 /h | 837 | 1,000–1,500（200 limit / 周期更短，但 active 池小）| 总写入小幅上升 |
| `okx_dex_price` 二次写入 /h | 24 | 30–60（命中率仍受 OKX 限制）| 路径 B 第二阶段，影响小 |

### 6.3 工程层

| 指标 | 修复前 | 修复后（预期）|
|---|---|---|
| IngestService 失败 → events 仍落库 | 否（一锅端）| 是（Stage A 独立 commit）|
| `seed_lag_ms` / `phase_hint` 非空率 | 0% | ≥ 80%（≥3 author 且 ≥2 event 时）|
| resolver/projection fresh 概念一致 | 否（20min vs 5min）| 是（一个 `MARKET_FRESH_MS` + 独立 `STALE_OBSERVATION_MS`）|
| Driver lane 在 fixture 上触达 | 0 | ≥ 1（仅当 fixture 含 watched_seed_link 且 score ≥ 72）|

### 6.4 不变量

| 指标 | 修复前后 | 原因 |
|---|---|---|
| events 入库吞吐 | 不变 | Stage A 顺序与现状一致 |
| EXACT 比例（chain+address 直命中）| 不变 | EXACT 路径不动 |
| CONFIRMED_CEX_TOKEN 比例 | 不变 | CEX 路径不动 |
| score 公式 | 不变 | 6 个 score_version 不变 |
| API/WebSocket payload 形状 | 不变 | 仅新增 data_health 子键 |

---

## 7. Goals · 可证伪目标

- **G1**：symbol-only NIL（除 `SYMBOL_NOT_IN_REGISTRY`）≤ 5% — 当前 35 / 348 = 10.1%，回放后 14 / 348 ≈ 4%。`SYMBOL_NOT_IN_REGISTRY`（4.9%）是结构性问题不在本审计范围。
- **G2**：dominance margin < 0.05 时 100% 落 AMBIGUOUS — 用 CRMX / CELIA / AIPANDA / TRACKHANTA fixture 回归。
- **G3**：当 ≥3 独立作者 ∧ ≥2 events 时 `seed_lag_ms` 与 `phase` 非空率 ≥ 80%；否则字段从 `RadarFeatureSet.propagation` 移除（不允许保留 None 字段）。
- **G4**：IngestService Stage B 失败时，对应 `events` 行已落库且 `reprocess_recent_token_intents` 下次 tick 能拾起。
- **G5**：当 `propagation.reasons` 含 `watched_seed_link` 且 fixture 内综合分 ≥ 72 时，`token_radar_rows` 内出现 ≥ 1 条 driver。其余 gate（heat ≥ 68、tradeability ≥ 70 等）保持。
- **G6**：每条 NIL/AMBIGUOUS resolution 的 `candidate_ids` + `reason_codes` + `lookup_keys` 在 token 详情页非空（v5 contract 已在，本期验真）。
- **G7**：`asset_market_sync_worker` 一轮选中的资产中 ≥ 95% SHALL 在过去 24h 内被 `token_intent_lookup_keys` 或 `token_intent_resolutions.candidate_ids` 引用过；orphan 资产（从未引用）SHALL 不进入 worker queue。
- **G8**：1h-active 资产（Hot 档，~669 个）任意时刻 ≥ 90% 有 `price_observations` 在过去 20 分钟（≤ resolver `FRESH_OBSERVATION_MS`）内；24h-active 资产（Warm + Hot 档，~6,192 个）≥ 90% 有 `price_observations` 在过去 4 小时（≤ `STALE_OBSERVATION_MS`）内。具体档位时长 / 名额分配 plan 阶段做仿真后定。

---

## 8. Non-goals · 红线

- **N1**：不新建 PostgreSQL 表 / 物化视图 / 后台 worker。
- **N2**：不引入贝叶斯 / 概率合并、不做 ground-truth 标注、不做 holdout / cross-validation。
- **N3**：resolver 与 projection 内不引入 LLM 调用；LLM 仅留在 `enrichment_worker` 的 watched-account social-event extraction 路径。
- **N4**：不重写 cashtag / CA 正则。1h 数据显示 EVM `_single_evm_chain_hint` 跨链冲突 13/117 cases（10%），不是主要痛点。
- **N5**：不动 v5 score 公式（`social_heat_v2`、`discussion_quality_v2`、`propagation_v2`、`tradeability_v2`、`timing_v4`、`social_opportunity_v3`）。仅修复输入。
- **N6**：不动 `events.coverage`、不扩大对外宣称的数据源。

---

## 9. Target architecture · 目标架构

管道仍是五段。改动局部化。

**T1 · resolver 双档 freshness**
symbol 解析分支区分 `UNIQUE_BY_CONTEXT_FRESH`（最新候选 ≤ `MARKET_FRESH_MS`）/ `UNIQUE_BY_CONTEXT_STALE`（≤ `STALE_OBSERVATION_MS = 4h`）。超出仍落 NIL。STALE 档在 `data_health.market_freshness_tier = stale_4h` 标记，下游 tradeability 自动接 `stale_market` cap = 70（已存在）。

**T2 · dominance margin gate**
top 候选晋升前要求 `top_score − second_score ≥ MIN_DOMINANCE_MARGIN = 0.05`（log10 单位）。平局或近平局落 AMBIGUOUS，候选全留在 `candidate_ids`。当前 `top_score <= second_score` 早返回是相同形状，仅放宽。

**T3 · holders-only winner flag**
当 dominance OR-gate 仅由 `holders ≥ MIN_DOMINANT_HOLDERS` 满足（mcap 与 liquidity 同时低于阈值），resolution 标记 `data_health.dominance_signal = "holders_only"`。本期不扣分。

**T4 · 资产市场同步：仅刷被引用资产 + 三档优先级（核心修复）**
`asset_market_sync_worker` 配合 `chain_assets_needing_price_refresh` SHALL 只选**至少在过去 N 天内被 `token_intent_lookup_keys` 或 `token_intent_resolutions.candidate_ids` 引用过**的资产，按以下优先级排序：

| 档位 | 入选条件 | 刷新频率 |
|---|---|---|
| **Hot** | 过去 1h 被引用 | 每 tick 必扫，≥ 70% 名额优先填 |
| **Warm** | 过去 24h 被引用，1h 未引用 | 每 30 min 扫一次（取最旧观测填剩余名额）|
| **Cold** | ever 引用过，过去 24h 未引用 | 每 4–12 h 扫一次（取最旧观测填残余名额）|
| **Orphan** | 从未被引用 | **不进刷新队列**；可能由 `TokenDiscoveryWorker` 后续重新带回热档 |

`DEX_PRICE_REFRESH_LIMIT` 从 80 提到 200，worker tick 仍 300s。`chain_assets_needing_price_refresh` 输入参数新增"引用门槛"概念。

**核心契约**：`TokenDiscoveryWorker` 仍负责把 dominance 候选拉进 registry（spam 必要），`asset_market_sync_worker` 不再无差别消费 registry——两个 worker 间通过 `token_intent_lookup_keys` 或 `candidate_ids` 隐式协议连接。

**T5 · feature_builder 死字段复活或删除**
`build_radar_features` SHALL 计算：
- `seed_lag_ms = first watched mention − first total mention`，两者都存在时；否则 `None`。
- `phase_hint`：由 propagation 已有的 concentration / new-author / duplicate 比例派生（具体 `seed | concentration | ignition | expansion | fade` 映射在 plan 给出）。
- `lookahead_risk = True` when `price_at_reference > price_at_first_snapshot * 1.5`，否则 `False`。

**T6 · resolver 与 projection 的 fresh 常量统一**
单一 `MARKET_FRESH_MS` 同时驱动 resolver 的"FRESH 档"和 projection 的 `market_status="fresh"`。stale 档使用独立 `STALE_OBSERVATION_MS`。

**T7 · IngestService 两段提交**
`IngestService.ingest_event` 在同一请求里按两个 commit boundary 顺序执行：
- **A 段 — Facts（原子，必须）**：events + event_entities + token_evidence + token_intents。失败丢弃整事件。
- **B 段 — Decisions（原子，可重放）**：registry upserts + token_intent_resolutions + token_intent_lookup_keys + account_token_alerts。失败时 A 已落，事件入 reprocess 队列。

A commit 后 B 开始。每段 idempotent on event_id。GMGN payload price / market cap 不写入任何 market observation；消息价格只由异步 `message_quote` worker 补。

**T8 · opportunity decision 在 watched_seed_link 下放宽 public-only cap**
`public_only_unconfirmed` cap 在 `propagation.reasons` 含 `watched_seed_link` 时设为 75（替代 68）。保留 cap 的精神（Bakshy 2011：ordinary-influencer > untrusted broadcast），让 watched-confirmed 信号可达 driver 门槛。

---

## 10. Conceptual data flow · 概念数据流

```
collector → ingest:Stage A（事实） ──► ingest:Stage B（决策）
                                              │ 失败：reprocess_recent_token_intents 队列
                                              ▼
                                        resolver（FRESH | STALE | NIL）
                                              │
                                              ▼
                                        projection（统一 MARKET_FRESH_MS）
                                              │
                                              ▼
                                        radar / timeline / alerts
```

`asset_market_sync_worker.run` 形状不变，仅刷新选择器换序 + 限额上调。

---

## 11. Core models · 核心模型（语义层）

- **`TokenIntentResolution.resolution_status`** 枚举扩展两档：`UNIQUE_BY_CONTEXT_FRESH` / `UNIQUE_BY_CONTEXT_STALE`，作为现有 `UNIQUE_BY_CONTEXT` 的细化。两者继承现有审计形状（reason_codes、candidate_ids、lookup_keys）。向后读：仍读父值的 reader 不受影响。
- **`TokenIntentResolution.data_health`** 新增可选键：
  - `market_freshness_tier ∈ {fresh, stale_4h}`
  - `dominance_signal ∈ {balanced, holders_only}`
- **`RadarFeatureSet.propagation`** 中 `seed_lag_ms`、`phase_hint`、`lookahead_risk` 必须为真实计算结果或从 contract 删除——不允许第三种"保留为 None"。
- **`IngestStage`**（内部逻辑概念，无 DB）：值 `facts | decisions | observations`。用于 telemetry 痕迹与 retry 契约。
- **统一对外暴露的常量**：`MARKET_FRESH_MS`、`STALE_OBSERVATION_MS`、`MIN_DOMINANCE_MARGIN`、`DEX_PRICE_REFRESH_LIMIT`。集中在一个 resolver-policy 模块，公式调整时 `resolver_policy_version` 一起 bump。

---

## 12. Interface contracts · 对外契约

- **WebSocket `/ws`**：payload 形状不变。`entities` 与 `alerts` 的现有键不变。`token_intent_resolutions` 行内新增 `data_health` 子键，无该键的旧 reader 兼容。
- **HTTP `/api/token-radar`**：payload 形状不变（v5 contract）。`resolution.status` 可能出现 `UNIQUE_BY_CONTEXT_FRESH` / `UNIQUE_BY_CONTEXT_STALE`，按父值 `UNIQUE_BY_CONTEXT` 解析的 reader SHALL 接受任一为成功。
- **HTTP `/api/target-social-timeline`**：每条 post 的 `price.status` 已支持 `ready | stale | pending_observation | missing_observation`，无需新状态。
- **CLI**：无新子命令。`ops` 维持运维入口，`query` 维持只读查询入口。
- **`score_version` 字符串**：不变（`social_heat_v2` 等）。resolver 把 `resolver_policy_version` 从 `token-radar-v5-resolver` 升到 `token-radar-v5-resolver-r1`（后缀）。下游 evaluation services SHALL 在 plan 里跟着升。

---

## 13. Acceptance criteria · 验收

- **AC1**：WHEN 一个 `symbol:*` intent 至少有一个候选最新 pre-decision observation 在 `STALE_OBSERVATION_MS` 内、无任何候选在 `MARKET_FRESH_MS` 内、且 dominance margin ≥ `MIN_DOMINANCE_MARGIN`，THEN 系统 SHALL 返回 `UNIQUE_BY_CONTEXT_STALE` 并设 `data_health.market_freshness_tier = "stale_4h"`。
- **AC2**：WHEN 多候选 symbol 解析中 `top_score − second_score < MIN_DOMINANCE_MARGIN`，THEN 系统 SHALL 返回 `AMBIGUOUS` 并写 `reason_codes = ["NO_MARKET_DOMINANT_CHAIN_ASSET"]` 与完整 `candidate_ids`（受 `MAX_AUDIT_CANDIDATE_IDS` 截断）。
- **AC3**：WHEN dominance 仅由 holders 字段满足（mcap 与 liquidity 同时低于阈值，holders 高于阈值），THEN 系统 SHALL 标记 `data_health.dominance_signal = "holders_only"`。
- **AC4**：WHEN `IngestService.ingest_event` 在 Stage B 抛异常，THEN 对应 `events` 行 SHALL 已在存储层 + `reprocess_recent_token_intents` 下个 tick SHALL 拾起该事件。
- **AC5**：WHEN `asset_market_sync_worker` 一轮 DEX 刷新结束，THEN 100% 被选中的资产 SHALL 在过去 N 天（plan 阶段定 N=7）内被至少一条 current `token_intent_lookup_keys` 或 `token_intent_resolutions.candidate_ids` 引用过（即 orphan 资产 SHALL 不入选）；其中 ≥ 70% SHALL 来自 Hot 档（过去 1h 引用过）；每 tick 限额 SHALL = 200。
- **AC9**：WHEN 任意时刻随机抽样 100 个过去 1h-active 资产，THEN ≥ 90% SHALL 有 `price_observations` 在过去 5 min 内；24h-active 资产 ≥ 90% SHALL 有 `price_observations` 在过去 4 h 内。
- **AC6**：WHEN `token_radar_feature_builder.build_radar_features` 在 ≥ 3 独立作者 ∧ ≥ 2 事件的窗口运行，THEN `propagation.seed_lag_ms` 与 `propagation.phase` SHALL 在 ≥ 80% 的 case 中非空（基于 24h fixture 测量）。
- **AC7**：WHEN `propagation.reasons` 含 `watched_seed_link`，THEN `opportunity_score` SHALL 应用 `public_only_unconfirmed` cap = 75（而非 68）；其他 gate 不变。
- **AC8**：WHEN 计算任意 v5 score block，现有 `score_version` + `contributions` + `reasons` + `risks` + `risk_caps` + `data_health` 键 SHALL 全部存在且非占位（防止合约静默漂移的回归 guard）。

---

## 14. Risks · 风险

| 风险 | 严重 | 缓解 |
|------|------|------|
| 4h stale 窗口让 UI 误以为是 fresh 报价 | 中 | `data_health.market_freshness_tier=stale_4h` 自动传到 tradeability `stale_market` cap = 70；UI 必须渲染该徽章（fixture 验证）|
| HANTA 类 spam 一次进 608 个 candidate 占用大量 Hot 档名额 | 中 | Hot 档以 lookup_key 引用计数 DESC 排序，HANTA 一次推文 = 同一 lookup_key 1 次，spam 进 candidate 仅消耗 1 次"被引用"额度，不会因为候选多就垄断；同时 dominance margin gate 让 AMBIGUOUS 的 spam 不再产生新 lookup_key 写入压力 |
| Orphan 不再刷新可能让历史资产数据陈旧但仍被未来推文引用时回到 Hot | 低 | TokenDiscoveryWorker 每次 lookup 都会重写 price_observation；新引用立即 fresh |
| `UNIQUE_BY_CONTEXT_STALE` 的下游 reader 仍读父值，丢失 freshness 信号 | 低 | 所有已知 reader（`retrieval/token_target_*`）消费 `data_health` 块，fixture 回归验证 |
| Stage B 失败重放和 Stage A 时刻的 registry 状态不同 | 低 | `reprocess_recent_token_intents` 已用 `decision_time_ms = event.received_at_ms` 锚定，时间锚不变 |
| `DEX_PRICE_REFRESH_LIMIT` 提到 200 触发 OKX 限速 | 中 | 现有 `DEX_PRICE_BATCH_SIZE = 20` 的批保护不变；provider 错误路径保留 skip+记数 |
| margin gate 0.05 误杀合规近场判断（DEXE margin 0.014 也会落 AMBIGUOUS）| 低 | DEXE 这种"差距 1.4%"本就是无意义信号，UI 显示候选清单是更诚实的呈现 |
| watched 路径放宽 cap 让单 watched 噪声推到 driver | 中 | cap 75 不是移除；driver 仍要 score ≥ 72 + heat ≥ 68 + ... + 无其他硬 cap；放宽仅在 `watched_seed_link` reason 触发 |
| 双档 freshness 改变 stale 命中下 tradeability_v2 的语义 | 低 | tradeability_v2 已支持 `stale_market` cap（line 64-69），公式不变 |

---

## 15. Evolution path · 演进路径

本审计停在最小手术。下一阶段的方向：

- **Lazy fetch on read**：AMBIGUOUS symbol 在读路径里同步调 `OkxDexClient.search_tokens` + 回灌后再决策，受 < 500ms 请求预算约束。
- **Refresh selector 用 24h 衰减加权 mention 计数**而非硬切「最近被引用」。
- **独立的 `audit_strict` decision lane**给机构消费者更严格的 cap。
- **异步 `token_discovery_worker`** 已有，但 NIL/AMBIGUOUS 反馈环浅；深化是后续工作。

本审计**不**封死以上任何一条。

---

## 16. Alternatives considered · 已否决方案

- **A1 · 物化视图 `token_resolution_outcomes`**。否决。新增持久化层只为了一个审计字段，触发 AGENTS.md "premature complexity" 红线，且不解决 freshness 根因。
- **A2 · resolver 内 lazy DEX fetch**。本期否决（保留为演进路径）。读路径成本在 provider 错误 / 限速时不可控；`chain_assets_needing_price_refresh` 重排能离线拿到大部分收益。
- **A3 · 直接放宽 `FRESH_OBSERVATION_MS` 到 4h、不分档**。否决。1h 旧报价会以 `market_status=fresh` 流入 tradeability，让现有 `stale_market` cap 失效。两档保住 cap。
- **A4 · 手调 dominance 权重（如降 holders 权重到 0.10）**。否决。1h winner 数据没显示 holders 权重驱动错误；问题是 margin gate 缺失，不是权重失衡。
- **A5 · 移除 driver lane**。否决。lane 在原则上可达（matched scope + watched cohort），0% 是采样 + cap 交互的产物，定向放宽保住 lane 的语义。
- **A6 · 引入按作者置信度的 weighting（Bakshy 风）**。否决（新设计）。watched-source 已被 reasons 编码，完整 author-graph weighting 超出范围。

---

## 17. Boundaries · 边界

| 类 | 行为 |
|---|---|
| Always | 每条 resolution 携带 `reason_codes` + `candidate_ids` + `lookup_keys` + `decision_time_ms` + `resolver_policy_version`；每个 score block 携带 `score_version` + `contributions` + `reasons` + `risks` + `risk_caps` + `data_health`；Stage A 永远先于 Stage B commit |
| Ask first | 数值：`STALE_OBSERVATION_MS`（建议 4h）、`MIN_DOMINANCE_MARGIN`（建议 0.05）、`DEX_PRICE_REFRESH_LIMIT`（建议 200）、`public_only_unconfirmed` cap 在 watched_seed_link 下（建议 75）。spec 落种子值，plan 阶段可改 |
| Never | 新增表 / 新增后台 worker / 新增 LLM 调用 / 引入贝叶斯或概率输出 / ground-truth 数据集 / cross-validation harness / `--no-verify` commit / 绕过 events / event_entities 写入 |

---

## 18. Literature mapping · 文献映射

每条引用都对应一个具体的代码选择或目标改动，不导入完整公式。

- **Babcock et al. PODS 2002 "Models and Issues in Data Stream Systems"**。stream 新鲜度与完整度 tradeoff、load-shedding 语义。支持双档 `FRESH | STALE | NIL` 的设计而非二元切。
- **Bonacich 1972 "Factoring and Weighting Approaches to Status Scores"、Saaty 1980 AHP**。对数化输入的权重加权排序。证明现有 0.55 / 0.30 / 0.15 mcap/holders/liq 是合理基线；不授权在没有同等测量的情况下放弃任一权重。
- **Buckley & Voorhees 2004 "Retrieval Evaluation with Incomplete Information"**。不可区分分数不能排序。授权 `MIN_DOMINANCE_MARGIN`。
- **Bakshy et al. WSDM 2011 "Identifying Influencers"**。public broadcast 影响远弱于 cohort confirmed influence。证明现有 `public_only_unconfirmed` cap，并支持 watched_seed_link 下的定向放宽。
- **Centola Science 2010 "The Spread of Behavior in an Online Social Network Experiment"**。复杂传染需要多次独立确认；crypto 中 long-tail 占传染表面的主体。支持引用频率优先的刷新策略。
- **Garcia-Molina & Salem 1987 "Sagas"**。长事务分解为幂等小步 + 补偿动作。授权 Stage A / B / C 拆分。
- **Kleinberg KDD 2002 "Bursty and Hierarchical Structure in Streams"**。`social_heat_v2` 的 `robust_z` / `z_ewma` 分支底层。本期不动；列出为完整性。
- **Goel et al. 2016 "The Structural Virality of Online Diffusion"**。独立作者宽度作为传染代理是 `propagation_v2` 的 `effective_authors` 底层。本期不动；列出为完整性。

---

## Appendix A · 测试夹具骨架

夹具分两部分：真实匿名样本 + 合成 bot pattern。

### A.1 真实数据导出（线上 PostgreSQL）

输出路径（plan 处理）：`tests/fixtures/token_pipeline_real_one_hour/{events.json, intents.json, resolutions.json, observations.json, registry.json, audit_state.json}`。author_handle 用 SHA-256 hash；`intent_id`、`event_id`、`asset_id`、`cex_token_id`、`pricefeed_id`、`chain_id`、`address`、`symbol` 全部保留以保证 resolver 可重放。spec 给 SQL，plan 给导出工具。

```sql
-- A.1 events（匿名化 author_handle）
SELECT
  e.event_id, e.received_at_ms, e.is_watched, e.coverage,
  encode(digest(e.author_handle, 'sha256'), 'hex') AS author_handle_hash,
  e.text, e.text_clean, e.reference_json, e.event_json
FROM events e
WHERE e.received_at_ms BETWEEN :since_ms AND :until_ms
ORDER BY e.received_at_ms;

-- A.2 token_intents
SELECT ti.*
FROM token_intents ti
WHERE ti.event_id IN (
  SELECT event_id FROM events WHERE received_at_ms BETWEEN :since_ms AND :until_ms
);

-- A.3 token_intent_resolutions（仅当前）
SELECT tir.*
FROM token_intent_resolutions tir
JOIN token_intents ti ON ti.intent_id = tir.intent_id
WHERE tir.is_current = true
  AND ti.created_at_ms BETWEEN :since_ms AND :until_ms;

-- A.4 选中 resolutions 引用的 price_observations
SELECT po.*
FROM price_observations po
WHERE (po.subject_type, po.subject_id) IN (
  SELECT DISTINCT target_type, target_id
  FROM token_intent_resolutions tir
  JOIN token_intents ti ON ti.intent_id = tir.intent_id
  WHERE tir.is_current = true
    AND ti.created_at_ms BETWEEN :since_ms AND :until_ms
    AND tir.target_id IS NOT NULL
)
AND po.observed_at_ms BETWEEN :since_ms - 24*3600*1000 AND :until_ms;

-- A.5 触及到的 registry_assets / cex_tokens
SELECT ra.*
FROM registry_assets ra
WHERE ra.asset_id IN (
  SELECT DISTINCT jsonb_array_elements_text(candidate_ids_json)
  FROM token_intent_resolutions tir
  JOIN token_intents ti ON ti.intent_id = tir.intent_id
  WHERE tir.is_current = true
    AND ti.created_at_ms BETWEEN :since_ms AND :until_ms
);

SELECT ct.*
FROM cex_tokens ct
WHERE ct.cex_token_id IN (
  SELECT target_id
  FROM token_intent_resolutions tir
  JOIN token_intents ti ON ti.intent_id = tir.intent_id
  WHERE tir.is_current = true
    AND ti.created_at_ms BETWEEN :since_ms AND :until_ms
    AND tir.target_type = 'CexToken'
);

-- A.6 审计状态分布（验证夹具覆盖）
SELECT resolution_status, COUNT(*) AS n
FROM token_intent_resolutions tir
JOIN token_intents ti ON ti.intent_id = tir.intent_id
WHERE tir.is_current = true
  AND ti.created_at_ms BETWEEN :since_ms AND :until_ms
GROUP BY resolution_status;
```

### A.2 合成 bot pattern fixture

六个最小场景，每个是一个自洽的 Python factory，喂给现有 `IngestService` + `TokenRadarProjection`。Plan 拥有文件布局；spec 定义场景：

| 场景 | 设置 | 期望 resolver 结果 | 期望 radar 结果 |
|---|---|---|---|
| **HANTA 风跨链 spam** | 5 链候选，全 holders < 100，全 mcap < 50k，dominance 几乎相等 | `AMBIGUOUS / NO_MARKET_DOMINANT_CHAIN_ASSET`，candidate_ids 含 5 项 | 仅出现在 attention lane，永不 resolved |
| **CELIA 风 0.0001 margin** | 3 链候选，top 2.1278 vs 2.1277 | `AMBIGUOUS`（margin gate 后）—— 当前是 `UNIQUE_BY_CONTEXT` | 回归测试 margin gate |
| **`$FIGHT` 8h stale 恢复** | 1 候选，最新观测 8h before decision，mcap 1.2M，holders 5,000 | `UNIQUE_BY_CONTEXT_STALE` + `data_health.market_freshness_tier=stale_4h` + tradeability cap=stale_market=70 | resolved lane，watch decision（非 driver）|
| **GMGN payload 直供** | gmgn_token_payload 含 chain+address+mcap+price | `EXACT / CHAIN_ADDRESS_EXACT`，不写 price_observations / current_market_field_facts | timeline post 的 `price.status=pending_observation` 或 `missing_observation`，直到 message_quote worker 写入 |
| **IngestService Stage B 失败** | resolver 抛 ValueError（如 registry 行畸形）| events、event_entities、token_evidence、token_intents 已落库；resolution 缺；reprocess 队列拾起事件 | radar row 缺，直到 reprocess 成功 |
| **watched 作者 seed link** | 2 watched 作者 5 分钟内 mention 同一 target | `propagation.reasons` 含 `watched_seed_link`；`public_only_unconfirmed` cap = 75；opportunity 在 score ≥ 72 时进 driver | fixture 数据中第一条 driver row |

每个场景写出确定性 seed fixture 到 plan 选定路径；断言落到 plan 命名的单测。本 spec 不命名 test 文件或函数。
