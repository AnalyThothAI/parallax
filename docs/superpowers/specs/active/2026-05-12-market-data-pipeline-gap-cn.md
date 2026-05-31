# Market Data Pipeline Gap 诊断与修复 Spec

**Status**: Draft, awaiting review
**Date**: 2026-05-12
**Owner**: Claude with Qinghuan
**Scope**: 仅诊断 + 修复方向；具体 implementation plan 另起一篇
**Related**:

- `docs/superpowers/specs/active/2026-05-10-token-radar-factor-snapshot-architecture-cn.md`
- `docs/superpowers/specs/completed/2026-05-04-market-observation-timing-production-spec-cn.md`
- `docs/superpowers/specs/active/2026-05-08-signal-lab-pulse-agent-hard-cut-cn.md`
- `src/parallax/domains/token_intel/services/token_radar_projection.py`
- `src/parallax/domains/asset_market/runtime/token_discovery_worker.py`
- `src/parallax/integrations/okx/dex_client.py`

## 一句话结论

`token_factor_snapshot_v3_social_attention` 的 `market.holders / liquidity_usd / market_cap_usd / volume_24h_usd` 字段对**所有 DEX 资产恒为 `None`**，导致下游 `_gates`、cohort 百分位归一化、pulse agent 都拿不到真实市场结构。根因不是 OKX 没数据（OKX 实际返回 mcap=664 万、liq=70 万、holders=9664），而是数据在**采集后没有被结构化写入下游消费表**，同时 OKX `search_tokens(query=address)` 对部分 pump.fun 合约直接返回空（必须 `query=symbol` 才命中）。

## 背景

### 产品诉求

Token Radar / Pulse Lab 的 `eligible_for_high_alert` gate 要求一个 DEX 资产同时满足：

- `holders >= 100`
- `liquidity_usd >= 25,000 USD`
- `market_cap_usd >= 50,000 USD`
- `unique_authors >= 3`

(见 `src/parallax/domains/token_intel/scoring/factor_snapshot.py:19-26`)

这是为了把 "几条 tweet 就刷分" 的 rug/scam pump.fun coin 挡在 high_alert 之外。但**该 gate 完全没有起作用**：最近 1h 的 19 个 pulse_candidates **100% 都是 trade_candidate / high_conviction**，而其中至少 NICHEBABY (mcap=16,691 USD 实际 < 50,000 floor)、LAB (mcap=3,878 USD < floor) 等本应被 floor 拒绝。

### 触发本次诊断的现象

2026-05-12 02:31 的 pulse run 把 RKC (合约 `7HgfX...rE3Apump`) 评为 `score=92 / trade_candidate / high_conviction`，agent summary：

> "RKC 在社交媒体上呈现极高的热度与传播动力...社会热度得分高达 99...叙事围绕 Roaring Kitty 账号被黑及社区接管展开..."

但实际情况：

- 18 个 author **无一来自 watched 列表**（`watched_mentions=0`）
- mention 实际下降 36%（`mention_delta_pct=-0.359`）
- z-score 全部 NULL（`baseline_status=insufficient_history`）
- 25 条 mention 中 **0 条**有 LLM 语义标注
- "Roaring Kitty 被黑" 是 LLM 的世界知识幻觉（RKC = Roaring Kitty Coin），不在任何 selected_post 文本中
- **RKC 实际是个 mcap=664 万、liq=70 万、holders=9664 的成熟 pump.fun token**——OKX 接口数据完整

> Agent 端报告详见 `docs/superpowers/specs/active/2026-05-08-signal-lab-pulse-agent-hard-cut-cn.md` 的延伸讨论。本 spec 只覆盖 **市场数据为什么缺失** 这条线。

## 应有的数据流（架构层面）

```
                    ┌──────────────────────────────────────────────┐
                    │ External Provider (OKX DEX REST + WebSocket) │
                    └────────────────┬─────────────────────────────┘
                                     │
                ┌────────────────────┼──────────────────────┐
                │                    │                      │
                ▼                    ▼                      ▼
       /token/search        /dex/market/price          DEX WebSocket
       (mcap/liq/holders/   (only price_usd)           price-info
        price/vol24h ✓)                                (mcap/liq/holders/vol ✓)
                │                    │                      │
                │                    │                      │
                ▼                    ▼                      ▼
   asset_identity_evidence   price_observations       LivePriceGateway
   raw_payload_json          (mcap/liq/holders         in-memory cache only
   (mcap/liq/holders 完整)    columns 存在但全 NULL)    (从不持久化)
                │                    │
                │                    ▼
                │            token_market_price_baselines
                │            (只有价格列，没有 mcap/liq/holders columns)
                │                    │
                │                    ▼
                │            TokenRadarSourceQuery
                │            LEFT JOIN price_baselines ←─── 唯一 JOIN
                ▼                    │
       (从未被读取)                  ▼
                            _market() in token_radar_projection.py
                            硬编码:
                              "market_cap_usd": None,   ← line 635
                              "liquidity_usd": None,    ← line 636
                              "volume_24h_usd": None,   ← line 637
                              "holders": None,          ← line 639
                                     │
                                     ▼
                            factor_snapshot.market
                            (4 字段恒为 None)
                                     │
                                     ▼
                            _gates 对 NULL → continue (不阻断)
                                     │
                                     ▼
                            eligible_for_high_alert = True
                                     │
                                     ▼
                            pulse agent: "市场数据缺失但 score 99 → trade_candidate"
```

## 复线：沿 RKC 走完整链路（实证）

下表每一行都用真实查询验证过，时间 `2026-05-12 02:31 UTC`。

| 阶段 | 表 / 函数 | RKC 实际状态 | 应有状态 |
|---|---|---|---|
| ① 事件入库 | `events` | 25 events / 18 authors（01:29-02:29 UTC）/ 0 watched | ✅ 正常 |
| ② Cashtag→intent | `token_intents` | "RKC" 6h 内 73 intent / 5 个不同合约 | ⚠️ symbol 一对多 |
| ③ Resolution | `token_intent_resolutions.is_current=true` | `resolution_status='EXACT'`，target_id 直指 `7HgfX...pump` | ✅ resolver 工作 |
| ④ Anchor price | `price_observations` (provider=okx, kind=message_anchor) | 10+ 条，price_usd 完整 (0.0065 → 0.0078)，但 **mcap/liq/holders 全 NULL** | 应填全 |
| ⑤ Market baseline | `token_market_price_baselines` | event_price_usd 完整 (0.00725)，但**表本身无 mcap/liq/holders 列** | schema gap |
| ⑥ OKX 主动 search | `asset_identity_evidence` (provider=okx) | **RKC 此合约 0 条 OKX evidence**（全部 provider=twitter / lookup_mode=tweet_mention） | 应该被触发 |
| ⑦ Radar 源 SQL | `TokenRadarSourceQuery.source_rows()` | 只 LEFT JOIN baselines（无市场字段） | 应 JOIN evidence 或 observations |
| ⑧ `_market()` 投影 | `token_radar_projection.py:585-665` | `holders/liquidity_usd/market_cap_usd/volume_24h_usd` 硬编码 None | 应从源 row 读 |
| ⑨ `_gates` 检查 | `factor_snapshot.py:307-373` | NULL `continue` 不阻断；只记 `market_metadata_missing` 到 risk_reasons | NULL 应 block high_alert |
| ⑩ Cohort 归一化 | `token_radar_projection.py:271-286` | cohort 91 token 中 `timing_risk / semantic_catalyst` 全员中位 = 全员都坏 | 全员都坏时不该归一化 |
| ⑪ Pulse gate | `pulse_candidate_gate.py:88-103` | `score >= 72 + eligible_for_high_alert → trade_candidate` | 应被 ⑨ 阻断 |
| ⑫ Agent 调用 | `pulse_agent_runs.request_json` | 只存 `{"context_hash": sha256}`，不存真实 prompt | 审计盲区 |

## 实证：OKX 接口本身有数据

直接调用 OKX DEX API 验证 RKC 合约（脚本: `OkxDexClient` from `src/parallax/integrations/okx/dex_client.py:19`）：

```
search_tokens(query='7HgfXftRBBqsYtAEYcqjGLQrNJLL6Tww9ek4rE3Apump', chain=501)
  → 0 results            ← 按合约地址搜不到（pump.fun 接口 quirk）

token_prices([{chain:501, address:'7HgfX...pump'}])
  → 0 results            ← /dex/market/price 也搜不到

search_tokens(query='RKC', chain=501)
  → 37 results, 第一条:
    {
      "symbol": "RKC",
      "address": "7HgfXftRBBqsYtAEYcqjGLQrNJLL6Tww9ek4rE3Apump",
      "market_cap_usd": 6642697.10,
      "liquidity_usd": 697477.88,
      "holders": 9664
    }
```

**结论**：OKX 数据完整存在，但需要按 symbol 查；按地址查会失败。

进一步 DB 实证（DRIP / LAB / NICHEBABY 等已被 discovery worker 抓到的 pump.fun token），它们的 `asset_identity_evidence.raw_payload_json` 里**完整保留**了 marketCap / liquidity / holders / price 四个字段。例如：

```json
// NICHEBABY (8hgVn...pump) at 02:23:08 UTC
{
  "marketCap": "16691.889697774728516934",
  "liquidity": "7182.20567142298118282186331486015060452115497064",
  "holders": "134",
  "price": "0.00001669188969777472851693456282884657",
  ...
}
```

但下游的 `pulse_candidates.factor_snapshot_json.market.holders` = NULL。

## 5 个根因（按链路顺序）

### 根因 1：OKX `search_tokens(query=<address>)` 对 pump.fun 合约返回空

**位置**：`src/parallax/integrations/okx/dex_client.py:39-53`

**事实**：OKX `/api/v6/dex/market/token/search?search=<solana_pump_address>&chains=501` 对至少部分（待统计）pump.fun 合约直接返回 0 行。同样的合约用 `search=<symbol>` 能拿到全部市场数据。

**后果**：`TokenDiscoveryWorker._lookup_address()`（`token_discovery_worker.py:281`）调用走 `lookup_mode='exact_address'`，对这类 token 必然 0 candidate，记 `status='not_found'`、`next_refresh_at_ms = now + 5min`。但 5 分钟后 lookup_key 仍是同一个 address，仍然走 address 路径，**永久失败**。

**24h 实证**：24h 内 `asset_identity_evidence` 表 0 条 `lookup_mode='address_search'`（用 OKX provider），但有 1607 条 `lookup_mode='symbol_search'`。说明现网几乎所有 OKX 发现都是 symbol 路径触发的。

### 根因 2：Resolution 一旦 RESOLVED，discovery 不再 trigger

**位置**：`src/parallax/domains/asset_market/repositories/discovery_repository.py:39-44`

```sql
WHERE events.received_at_ms >= %s
  AND (
    current_resolution.resolution_id IS NULL
    OR current_resolution.resolution_status = 'NIL'
    OR current_resolution.resolution_status = 'AMBIGUOUS'
  )
```

**事实**：`due_lookup_keys` 只在 resolution 为 NIL/AMBIGUOUS 时才把 lookup_key 入队。RKC 的 resolution 是 `EXACT`（51 条）/ `UNIQUE_BY_CONTEXT`（40 条），永远不进队。

**后果**：tweet 里直接给了合约地址的 token (`Twitter Monitor Basic` 经常这样)，resolver 凭 address_hint 直接 EXACT 命中 → 永不 trigger OKX 主动查询 → 永远没有 `provider='okx'` 的 evidence。

**24h 实证**：24h 内 2043 个 token 处于 EXACT/UNIQUE_BY_CONTEXT 状态，其中 **1102 个（54%）没有任何 OKX evidence**。

### 根因 3：`token_market_price_baselines` schema 缺市场字段

**位置**：`platform/db/alembic/versions/` （schema 定义）

**事实**：`token_market_price_baselines` 表只有价格类列（first_price_usd, event_price_usd, before_event_price_usd 及各自 basis/quote/symbol/observed_at_ms），**没有** holders / liquidity_usd / market_cap_usd / volume_24h_usd 列。

**后果**：即使 `price_observations` 表本身有这 4 列（schema 验证：`market_cap_usd numeric, liquidity_usd numeric, volume_24h_usd numeric, holders bigint`），baselines 的 upsert 路径不复制它们，下游 `TokenRadarSourceQuery` 只 JOIN baselines，所以读不到。

### 根因 4：`_write_dex_observation` 硬编码市场字段为 None

**位置**：`src/parallax/domains/asset_market/services/anchor_price_observation.py:164-203`（参考 Explore agent 报告）

**事实**：anchor price worker 调 OKX `/dex/market/price` 拿到价格，写入 `price_observations` 时硬编码 `market_cap_usd=None, liquidity_usd=None, volume_24h_usd=None, holders=None`。

**24h 实证**：

| provider | observation_kind | n | n_with_mcap | n_with_holders |
|---|---|---|---|---|
| okx | message_anchor | 4104 | **0** | **0** |
| okx_cex | message_quote | 32 | 0 | 0 |
| okx_dex_price | message_quote | 31 | 0 | 0 |
| **okx_dex_search** | **refresh** | **25** | **25** | **24** |

只有 `okx_dex_search/refresh` 路径填了市场字段，但**24h 内只跑了 25 次、且全部集中在 11 小时前的同一时刻**（看起来是单次手动 / cron 触发，不是常态）。

### 根因 5：`_market()` 投影硬编码全 None

**位置**：`src/parallax/domains/token_intel/services/token_radar_projection.py:585-665`

```python
# line 624-664: 即使有 source row，也固定填 None
market: dict[str, Any] = {
    ...
    "market_cap_usd": None,    # ← line 635
    "liquidity_usd": None,     # ← line 636
    "volume_24h_usd": None,    # ← line 637
    "open_interest_usd": None, # ← line 638
    "holders": None,           # ← line 639
    ...
}
```

**事实**：`_market()` 即使把 anchor 价格和时间戳都从 source row 拷出来，**这 4 个字段从不读 row 任何字段**，无条件设为 None。

**后果**：哪怕未来根因 3 修了（baselines 加列）、根因 4 修了（observation 写真值）、SQL JOIN 也补了，`_market()` 这一层仍会把它们抹成 None。这是 v3 snapshot 合同的"漏接"。

### 根因 6（gate 端的放行）：`_gates` 对 NULL 不阻断

**位置**：`src/parallax/domains/token_intel/scoring/factor_snapshot.py:307-373`

```python
for key, reason in _DEX_FLOOR_REASONS.items():
    value = _optional_float(market.get(key))
    if value is None:
        metadata_missing = True
        continue                      # ← NULL 跳过，不 block
    if _is_below(value, key):
        blocked_reasons.append(reason)
if metadata_missing:
    risk_reasons.append("market_metadata_missing")  # 只进 risk，不进 blocked
```

**事实**：当上面 5 个根因把所有 DEX token 的 `holders/liquidity_usd/market_cap_usd` 都置 None 时，gate 一律 `continue` 不阻断。`market_metadata_missing` 只是个 risk reason 标签，不阻断 `eligible_for_high_alert`。

**后果**：DEX_HIGH_ALERT_FLOORS 字典定义存在但**对真实流量从未生效**——因为输入数据全 NULL。

## 第一性原理

1. **数据采集与数据消费是两条事**：OKX 能拿到的市场字段必须**结构化持久化**到下游消费表（不能只留在 `raw_payload_json` 里、不能只留在 in-memory cache 里）。
2. **fail-closed over fail-open for safety floors**：DEX_HIGH_ALERT_FLOORS 这种安全护栏，NULL 输入必须 **block**，不能 `continue`。"数据不可知" 和 "数据已知达标" 不应该有同样后果。
3. **provider-side quirk 必须在 integration 层吸收**：OKX `query=address` 失败、`query=symbol` 成功 这类 API 怪癖，必须在 `OkxDexClient` 或 `TokenDiscoveryWorker` 内部用 fallback 策略屏蔽，不能让下游误以为"OKX 没数据"。
4. **资源覆盖优先级跟随产品热度**：被 pulse_candidate / radar high_alert 命中的 token 是产品最关心的；它们的市场数据刷新优先级必须**最高**，而不是被排在 `due_lookup_keys` 队尾。
5. **schema 是合同**：`token_market_price_baselines` / `_market()` 的字段列表是 v3 snapshot 合同的具体形态，任何"应有"字段都必须能从 source query 一路传到 snapshot，不允许中间被 None 抹掉。

## 目标

### In Scope（按修复优先级）

**P0 — 让市场数据真的流到 factor_snapshot**

1. **Integration 层吸收 OKX address-search 失效**
   - `OkxDexClient.search_tokens` 或 `TokenDiscoveryWorker._lookup_address`：当 address-search 返回 0 结果时，自动 fallback 到 symbol-search 并按 address 二次过滤。
   - 期望验证：对至少 N 个已知"按地址查不到、按 symbol 能查到"的 pump.fun 合约，fallback 后能拿到 mcap/liq/holders。

2. **打开 RESOLVED token 的 discovery 刷新通道**
   - `discovery_repository.py:39-44`：在 `due_lookup_keys` 加一类条件——对 `resolution_status IN ('EXACT','UNIQUE_BY_CONTEXT')` 但**最新 OKX evidence 已陈旧 (>1h) 或缺失**的 token，按 hot window / recent radar 命中度排序入队。
   - 不放宽现在的 NIL/AMBIGUOUS 触发，只**新增**一类入队条件。

3. **持久化 OKX 市场字段到下游消费表**
   - 方案 A（轻量）：把 OKX search/price 返回的 mcap/liq/holders/vol24h **结构化写入 `price_observations` 表已有的对应列**（schema 已有，只是 `_write_dex_observation` 硬编码 None）。
   - 方案 B（彻底）：给 `token_market_price_baselines` 加 4 列，并在 baseline upsert 时从 latest okx_dex_search observation 复制。
   - 推荐先 A 再 B；A 立刻让数据可读，B 是合同对齐。

4. **`_market()` 真实读取市场字段**
   - `token_radar_projection.py:624-664`：把硬编码的 None 改成从 source row 读对应字段。
   - 配合 `TokenRadarSourceQuery.source_rows` 增加 `latest_okx_market` LATERAL JOIN（取最新 `provider IN ('okx_dex_search','okx_dex_price') AND market_cap_usd IS NOT NULL` 的 price_observation）。

**P1 — 让 gate 真的生效**

5. **`_gates` 对 NULL fail-closed**
   - `factor_snapshot.py:307-373`：把 `if value is None: continue` 改成 `blocked_reasons.append("market_metadata_unknown")` 或新增一档 `market_data_unverified` 状态阻断 high_alert。
   - 同时调整 `_market_health()` 让 NULL 的 health 直接归为 `missing`（而非 `partial`），让 cohort 归一化能感知到。

6. **`okx_dex_search` 触发器化**
   - 现在 24h 只跑了 25 次。要么改成定期 worker（如 5min 一次刷新 hot targets），要么 hook 到 pulse_candidate enqueue 上（trigger gate 命中时立刻刷新一次）。

### Out of Scope

- 不改 `LivePriceGateway` 的 in-memory 模型；WebSocket 持久化是另一条线（cost 大、本 spec 不解决）。
- 不动 `cex_route_sync` / CEX 路径，本 spec 只覆盖 DEX 资产。
- 不动 cohort 百分位归一化机制本身（这是 `2026-05-08` agent hard cut spec 的范围）。
- 不动 agent prompt 中是否把 `family_scores` 标注为 percentile（另一条修复线）。
- 不动 OKX WebSocket `LivePriceGateway` 持久化方案。
- 不引入新的 provider（DEX Screener / Jupiter / Birdeye）。

## 风险与权衡

- **OKX rate limit**：开"RESOLVED token 也定期刷新"会增加 OKX API 调用量。需要先量化：在 P95 hot-window cohort=91 / 5min 刷新一次的情况下，QPS 是 ~0.3，远低于 OKX DEX REST 的限流。但仍需 backoff + jitter。
- **fail-closed 的初始震荡**：根因 6 修了之后，**最近 1h 19/19 都是 trade_candidate** 会立即变成 **19/19 都是 blocked_low_information**（因为新的 OKX 数据还没补齐）。需要先跑根因 1-5 让数据补全后再上线根因 6。
- **方案 A vs 方案 B 的债务**：方案 A 让 `price_observations` 承担"市场快照"职责，但表名暗示"价格观测"。短期可接受，长期推荐方案 B 把市场快照拆出独立表（参考已废弃的 `asset_market_snapshots`）。
- **pump.fun 接口怪癖会变**：OKX 哪天可能修复 address-search → 我们 fallback 仍然 work（symbol-search 是 superset）。但要监控 fallback 比例，下降说明 OKX 修了。

## 验证标准

- **数据流验证**：在 P0 修完后，运行 `SELECT COUNT(*) FROM pulse_candidates WHERE updated_at_ms > NOW()-1h AND factor_snapshot_json->'market'->>'holders' IS NULL` 应 < 10% (现在是 100%)。
- **Gate 验证**：在 P1 修完后，运行同样的查询、改成 `WHERE pulse_status='trade_candidate' AND factor_snapshot_json->'market'->>'holders' IS NULL` 应为 0（fail-closed）。
- **覆盖率验证**：`SELECT COUNT(*) FILTER (WHERE EXISTS okx evidence) / COUNT(*) FROM (resolved tokens last 24h)` 应从现在的 46% 上升到 80%+。
- **回归验证**：先用最近 1h 的 19 个 candidate 做 backtest——它们在修复后的 gate 下应该有 ≥ 30% 被降级为 token_watch 或 blocked_low_information（说明 floor 真的起作用了）。

## 决策待定

- **方案 A vs 方案 B**：先 A 还是直接 B？方案 A 1 周可上线、方案 B 需要 schema 迁移 ~3 周。倾向先 A。
- **`okx_dex_search` 周期化的 interval**：5min（保守）还是 1min（紧跟 hot 信号）？取决于 OKX 限流和成本。
- **是否引入 DEX Screener fallback**：OKX 不覆盖的极冷门 pump.fun token 可能根本搜不到。但加 provider 是 KISS 之外的事，本 spec 不引入。

## 参考数据点（生成于 2026-05-12 02:30-02:48 UTC）

| 指标 | 真实值 |
|---|---|
| 最近 1h pulse_candidates 数 | 19 |
| 100% trade_candidate / high_conviction | 19/19 |
| 最近 1h factor_snapshot 中 market.holders=NULL | 19/19 (100%) |
| 最新一帧 `1h all` radar rows | 162 |
| 其中 `data_health.market='ready'` | 15 (9%) |
| 其中 `families.timing_risk.data_health` 非 `ready` | 162 (100%) |
| 24h price_observations 总数 | 4200 |
| 其中 mcap/liq/holders 非 NULL | 25 (0.6%) |
| 24h `asset_identity_evidence` (provider=okx) | 2013 |
| 其中 pump.fun (address 含 'pump') | 336 |
| 24h resolved (EXACT/UNIQUE_BY_CONTEXT) 的 token | 2043 |
| 其中**没有任何** OKX evidence | 1102 (54%) |
| OKX `search_tokens(query='RKC')` 返回的 RKC 候选 | 37 |
| OKX 给的 RKC mcap / liq / holders | 664 万 / 70 万 / 9664 |

## Open Questions

1. `okx_dex_search` 路径 24h 只跑了 25 次且全在 11 小时前——是不是已经被关掉了？需要看 ops 配置。
2. `market_provider_observations` 表迁移已经存在但 0 写入——是不是当时设计的"统一观测源"被绕过了？是否应该走这条路而不是新建/扩展现有表？
3. 是否真的需要 holders/liquidity 实时（每分钟）刷新，还是 hot window 内一次性快照即可？产品语义需要确认。
