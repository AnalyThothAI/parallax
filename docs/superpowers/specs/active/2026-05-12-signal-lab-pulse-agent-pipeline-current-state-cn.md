# Signal Lab Pulse Agent — 链路现状审计与缺口 Spec

**Status**: Draft, awaiting review
**Date**: 2026-05-12（晚于同日 02:31 那次 market-data-pipeline-gap 诊断）
**Owner**: Claude with Qinghuan
**Scope**: 仅审计 + 缺口定位 + 修复方向；implementation plan 另起一篇
**Related** (近 4 天已经合入的相关 hard cut):

- `docs/superpowers/specs/active/2026-05-12-market-data-pipeline-gap-cn.md`（上一次诊断，本 spec 是它的"现状再审"）
- `docs/superpowers/specs/active/2026-05-12-token-radar-hot-resolution-market-readiness-cn.md`（已实施 `0a3b9105`）
- `docs/superpowers/specs/active/2026-05-12-symbol-only-resolution-gap-cn.md`（已实施 `4f9f1bdc`）
- `docs/superpowers/specs/active/2026-05-11-token-radar-market-boundary-hard-cut-cn.md`（field-level 边界 spec，部分实施）
- `docs/superpowers/specs/active/2026-05-11-token-radar-anchor-live-worker-simplification-cn.md`（已实施，migration `20260511_0029`）
- `docs/superpowers/specs/active/2026-05-11-okx-dex-ws-market-stream-and-radar-recovery-cn.md`（runtime 已实施但 `dex_ws_enabled=false`）
- `docs/superpowers/specs/active/2026-05-11-token-factor-engineering-hard-cut-cn.md`（social factor 重写已实施）
- `docs/superpowers/specs/active/2026-05-08-signal-lab-pulse-agent-hard-cut-cn.md`（早期 hard cut）

## 一句话结论

近 4 天 main 完成了 6 项 hard cut（hot identity refresh、anchor/live 拆分、social factor 重写、pulse agent gate-key 暴露、symbol-only 解析、search v2），把 **数据采集端** 几乎所有问题修齐了。但 pulse agent 链路的 **最终症状没有改变**：最近 1h 仍是 27/27 token_target 100% `trade_candidate / high_conviction`，因为 4 处下游消费/聚合环节没被 hard cut 触及：`_market()` 仍硬编码市场字段为 None、`_gates()` 仍对 NULL `continue` 不阻断、cohort percentile 仍把"全员都坏"洗成 50、agent prompt 仍只存 `context_hash`。`LivePriceGateway` 设计正确但 `dex_ws_enabled=false` 默认关闭，导致 DEX 路径 0 updates。

## 1. 自上一次诊断（2026-05-12 02:31）以来的变化

| 上次诊断 6 个根因 | 现在状态 | 实施 commit / spec |
|---|---|---|
| 1. OKX `query=<address>` 对 pump.fun 失效，无 fallback | **部分修复** —— `resolution_refresh_worker` 引入 hot resolution，且 `symbol-only-resolution-gap` 已合入。但实际是用 RESOLVED 路径的反复刷新绕开了 address-search 失败，没有显式 address→symbol fallback。 | `4f9f1bdc`, `0a3b9105` |
| 2. RESOLVED token 永不再 trigger discovery | **已修复** —— `discovery_repository.py` 增加 hot RESOLVED 路径 + `resolution_refresh_worker` 替代 `token_discovery_worker` | `0a3b9105` |
| 3. `token_market_price_baselines` schema 缺市场字段 | **设计绕开** —— 选择不在 baselines 加市场字段，而是走 `LivePriceGateway` in-memory 模型 | `2026-05-11-anchor-live` spec |
| 4. `_write_dex_observation` 硬编码市场字段为 None | **设计转向** —— anchor path 故意只写价格（hard cut 后 `price_observations.observation_kind='message_anchor'` only）；market 字段由 LivePriceGateway 在内存提供 | `2026-05-11-anchor-live` spec, migration `20260511_0029` |
| 5. `_market()` 硬编码 mcap/liq/holders/volume=None | **未修复** —— `token_radar_projection.py:635-639` 仍写死 None | — |
| 6. `_gates` 对 NULL `continue` 不阻断 | **未修复** —— `factor_snapshot.py:328-336` 逻辑未动 | — |
| H. `pulse_agent_runs.request_json={"context_hash": ...}` 审计盲区 | **未修复** —— `pulse_candidate_worker.py:426` 仍只存 hash | — |

> **结论**：上游 6 个根因里 4 个已经被新 spec 处理（2 个修复 + 2 个设计绕开），但**下游消费链路的 3 个未触及**。所以症状不变。

## 2. 现状架构图

```
┌─ Stage ────────────────┬─ Code ────────────────────────────────────────────────┬─ Status ───────┐
│ Ingest                 │ IngestService（provider-free）                          │ ✅ stable      │
│ Identity & Intent      │ token_intents + token_intent_resolutions               │ ✅ stable      │
│ Hot Resolution Refresh │ ResolutionRefreshWorker (new)                          │ ✅ implemented │
│ Anchor Price           │ AnchorPriceWorker → price_observations(message_anchor) │ ✅ stable      │
│                        │                    → token_market_price_baselines      │                │
│ Live Market (NEW)      │ LivePriceGateway in-memory only                        │ ⚠️ DEX disabled│
│                        │   DEX WS: dex_ws_enabled=false → 0 updates             │                │
│                        │   CEX poll: 16 active targets                          │                │
│ Radar Source SQL       │ TokenRadarSourceQuery (anchor + identity + social)     │ ✅ stable      │
│ Factor Snapshot Build  │ build_token_factor_snapshot()                          │ ⚠️ NULL pass  │
│   _market()            │ 硬编码 holders/mcap/liq/volume=None ★                  │ ❌ unfixed     │
│   _gates()             │ NULL `continue` 不 block ★                              │ ❌ unfixed     │
│   _social_heat etc.    │ 4 family with new social factors                       │ ✅ rewritten   │
│ Cohort Percentile      │ token_radar_projection.py:271-286 ★                    │ ❌ unfixed     │
│   families[X].score    │ 被覆盖为 percentile×100，全员都坏 → 全员中位 50         │                │
│ Pulse Trigger Gate     │ _is_asset_trigger (decision/rank>=70/watched>0)        │ ⚠️ percentile  │
│ Pulse Candidate Gate   │ trade_candidate_min=72 / token_watch_min=45            │ ⚠️ 接受 NULL  │
│ Agent Input            │ pulse_recommendation_agent_input()                     │ ✅ schema 改善 │
│   prompt               │ 现在暴露 gate_result.* / gates.risk_reasons keys       │ ✅ NEW (e3b4)  │
│   factor_key validate  │ agent 输出 factor_key 必须 in available_factor_keys     │ ✅ NEW         │
│   execution filter     │ 自动剥离 / 拒绝执行指令性语言                            │ ✅ NEW         │
│ Agent Run Persist      │ request_json = {context_hash} ★                        │ ❌ unfixed     │
│ Pulse Persist          │ pulse_candidates (含 agent_recommendation_json)        │ ✅ stable      │
│ API Read               │ AssetFlowService._overlay_live_market                  │ ✅ NEW         │
│   factor_snapshot.market│ 仍 anchor-only，无 mcap/liq/holders                    │               │
│   row.live_market      │ gateway.snapshot() → status=missing（WS 关）            │ ⚠️ missing    │
└────────────────────────┴───────────────────────────────────────────────────────┴────────────────┘
```

★ = 未修复根因，本 spec 主要关注点

## 3. 复线：沿 RKC 走当前真实数据（2026-05-12 11:48 UTC）

> RKC 是这次抽样最显眼的 case：rank_score=92, cohort=150, score=100/100/49/50, agent verdict=trade_candidate。

| Stage | 真实值 |
|---|---|
| Resolution | `EXACT`, target=`asset:solana:token:7HgfX...rE3Apump`, refresh_worker 已确保 identity 新鲜 |
| Anchor Price | `price_observations.observation_kind='message_anchor'`, OKX, price_usd 完整, mcap/liq/holders=NULL（设计如此） |
| Live Gateway | `gateway.snapshot(Asset, asset:...rE3Apump)` → `status='missing'`, dex_ws_enabled=false |
| Cohort | size=150（之前 91，因 hot resolution 扩大），ranked, RKC 是顶部 |
| families.social_heat | score=**100** （percentile rank=1.0），raw_score 大概率 75-90 |
| families.social_propagation | score=**99** |
| families.semantic_catalyst | score=**49** ← cohort 全员 partial，并列中位 |
| families.timing_risk | score=**50** ← cohort 全员 anchor_only，并列中位 |
| composite.rank_score | **92** |
| factor_snapshot.market.holders/mcap/liq | **全 NULL** |
| gates.eligible_for_high_alert | **true**（NULL 不阻断） |
| gates.blocked_reasons | `[]` |
| gates.risk_reasons | `["market_metadata_missing"]` |
| pulse_status | `trade_candidate`（score 92 ≥ 72 + eligible_for_high_alert） |
| score_band | `high_conviction` |
| agent input | factor_snapshot + gate_result + selected_posts + available_factor_keys |
| agent output verdict | `trade_candidate` |
| agent output residual_risks | 现在能明确写 "market_metadata_missing"、"semantic_catalyst.data_health=missing" |
| agent run request_json | `{"context_hash": "sha256:..."}` —— 真实 prompt 未持久化 |

API 端验证：

```
GET /api/token-radar?window=1h&scope=all&limit=3
→ targets[].live_market = {
    status: 'missing',
    market_cap_usd: null,
    liquidity_usd: null,
    holders: null,
    ...
  }                                               ← gateway 设计存在但 0 数据
```

`/api/status.live_price_gateway`:

```json
{
  "configured": false,                            ← dex_ws_enabled=false
  "worker_running": true,
  "subscription_limit": 100,
  "last_result": {
    "targets_selected": 100,
    "dex_targets_selected": 84,
    "cex_targets_selected": 16,
    "updates_received": 0,                        ← DEX WS 0 updates
    "cex_quotes_received": 16,
    "live_market_updates_published": 16
  }
}
```

## 4. 现存缺口（按链路顺序）

### 缺口 G1 — DEX WebSocket 未启用 → live market 永远 missing

**位置**: 配置层（`providers.okx.dex_ws_enabled` 默认 false），见 `2026-05-11-okx-dex-ws-market-stream-and-radar-recovery-cn.md:113` 的 "default false until deployed and verified"。

**后果**:
- 最近 1h 100% pulse_candidate（27/27 token_target）都是 DEX 资产，全部走 DEX 路径
- `live_market_gateway.snapshot(Asset, ...)` 全部返回 `status='missing'`
- API 层 `row.live_market.{mcap,liq,holders}` 全部 NULL
- 即使前端 visible，没法显示 live 市场结构

**实证**: `dex_targets_selected=84, updates_received=0`，CEX 路径 16 个有效但 pump.fun token 都不在 CEX。

### 缺口 G2 — `_market()` 不消费 live gateway（even when populated）

**位置**: `src/parallax/domains/token_intel/services/token_radar_projection.py:624-664`

```python
market: dict[str, Any] = {
    ...
    "market_cap_usd": None,    # ← line 635
    "liquidity_usd": None,     # ← line 636
    "volume_24h_usd": None,    # ← line 637
    "holders": None,           # ← line 639
    ...
}
```

**事实**: projection 即使能拿到 anchor 价格的所有 row 字段，也不读 LivePriceGateway。所以 factor_snapshot.market.{mcap/liq/holders} 恒为 None。

**讽刺**: hot-resolution-spec 的 acceptance criteria 写了 "如果 live cache 还没有，anchor price ready 时前端应显示 anchored"（line 261-263），是给前端的；但 pulse agent 拿到的不是前端 row，而是 factor_snapshot —— 中间这一跳没有 live overlay。

### 缺口 G3 — `_gates` NULL `continue` 不 block（仍未修复）

**位置**: `src/parallax/domains/token_intel/scoring/factor_snapshot.py:328-336`

```python
for key, reason in _DEX_FLOOR_REASONS.items():
    value = _optional_float(market.get(key))
    if value is None:
        metadata_missing = True
        continue                              # ← NULL 跳过，不 block
    if _is_below(value, key):
        blocked_reasons.append(reason)
if metadata_missing:
    risk_reasons.append("market_metadata_missing")   # 只进 risk
```

**事实**: 因 G1+G2，所有 token 的 mcap/liq/holders 都是 NULL → 整个 `_DEX_FLOOR_REASONS` 循环对所有 token 都走 `continue` → `DEX_HIGH_ALERT_FLOORS` 字典定义存在但**对真实流量从未生效**。

**注**: 这一条跟 `2026-05-11-token-factor-engineering-hard-cut-cn.md` 的 G1（eligibility != alpha）冲突——spec 说"market freshness pass 不增加 alpha 点数"，但实施时是"NULL 也不阻断高级别"。两件事不完全等价；spec 没明确"市场信息缺失时应不应该 fail closed"。

### 缺口 G4 — Cohort percentile 把"全员都坏"洗成 50

**位置**: `src/parallax/domains/token_intel/services/token_radar_projection.py:271-286`

```python
factor_ranks_by_id = rank_factors_within_cohort(factor_scores=factor_scores, cohort=cohort)
for family in TOKEN_RADAR_FACTOR_FAMILIES:
    rank = factor_ranks.get(family)
    if rank is not None and isinstance(families.get(family), dict):
        families[family]["score"] = round(float(rank) * 100.0)
```

**事实**:
- cohort_size 已经从 91 涨到 150（hot resolution 后扩大）
- 最近 1h 所有 27 个 trade_candidate 的 `timing_risk=50, semantic_catalyst=49`（全员中位）
- 因为 cohort 全员的 timing_risk raw_score 都是 0（anchor_only 短路），cohort 全员的 semantic_catalyst raw_score 都是 0（LLM 标注覆盖率低）
- percentile 把全员并列推到 0.50/0.49 → ×100 = 50/49
- agent 收到 50/49 当成"中等"读，实际是"全员都坏"

**注**: `2026-05-11-token-factor-engineering-hard-cut-cn.md` 的 G3 要求"normalization 显示 cohort 上下文，让 snapshot 可解释"，已经做到（normalization.cohort 字段是有的）。但 prompt 没告诉 LLM "如果 cohort 全员都坏，中位也是 50"。

### 缺口 G5 — `pulse_agent_runs.request_json` 仍只存 hash

**位置**: `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:426`

```python
request_json={"context_hash": _stable_hash(agent_context)},
```

**事实**: agent 真实 prompt 没持久化。事后无法回溯 LLM 收到什么输入、prompt drift 多严重、不同 token 之间 prompt diff 是什么。

**讽刺**: `e3b4082b fix: expose pulse gate keys to recommendation agent` 让 agent 看到更多上下文，但 audit 端反而看不到这些上下文实际生效情况。

### 缺口 G6 — Agent 仍不知道 family_scores 是 percentile

**位置**: `src/parallax/domains/pulse_lab/types/pulse_recommendation.py:133-149 pulse_recommendation_agent_instructions()`

**事实**: prompt 写 "You receive deterministic TokenFactorSnapshot and gate_result. Do not invent facts. Every primary reason... must cite a factor_key present in available_factor_keys"。

但 prompt **没有说明 `composite.family_scores.{social_heat,...}` 是 cohort 内 percentile rank × 100，不是绝对热度**。LLM 默认会把 50/49 读成"中性"，把 99/100 读成"极强"。

实际 agent 输出印证：

> "社交热度因子得分高达93分，表明市场关注度和话题性极强，是驱动当前价格行动的主要动力。"

但底层 raw_score 大概率只有 75-80（来自 new_burst fallback），93 是 cohort 排第二的位置。

### 缺口 G7 — Trigger gate 仍然在 cohort percentile 上做决策

**位置**: `pulse_candidate_worker.py:511 _is_asset_trigger`

```python
return decision in {"high_alert", "watch"} or score >= resolved_thresholds.min_rank_score or watched_mentions > 0
```

`min_rank_score=70`. 但 `score` 实际是 `composite.rank_score = _raw_alpha_score(families)` —— 用的是 weighted average of family.score（已经被 percentile 覆盖）。所以 trigger 实际是"cohort 前 30% 必然 enqueue"。

cohort=150 → 前 30% = 45 个候选 → 5min cooldown 后稳定流出 ~25-30 个/小时 → 跟实测 27 个一致。

### 缺口 G8 — `_factor_sum` 对负向因子的处理（残留病灶）

**位置**: `factor_snapshot.py:431-436`

```python
def _factor_sum(factors: list[dict[str, Any]]) -> int:
    scores = [_finite_score(factor.get("score")) for factor in factors]
    positive_scores = [score for score in scores if score > 0]
    penalty = sum(score for score in scores if score < 0)
    positive_score = sum(positive_scores) / len(positive_scores) if positive_scores else 0.0
    return clamp_score(positive_score + penalty)
```

逻辑未变：positive 因子取均值（0 分被丢），negative 因子加总作为 penalty。`log_points(value <= 0) → 0`，所以负向 `attention_acceleration` 仍然被截成 0 而不是负值。

**注**: 这是上一次 spec 的根因 C/E，本次 main 没动。

## 5. 第一性原理

1. **fail-closed for safety gates**: DEX_HIGH_ALERT_FLOORS 是安全护栏，"数据不可知" 必须 block 而不是 `continue`。
2. **percentile 不等于绝对强度**: 任何把 percentile rank 暴露给消费者的合同，必须显式区分两层语义。否则 LLM/agent/UI 默认把 50 当中性。
3. **审计是合同的一部分**: agent 真实输入必须可重放，否则 prompt 改动无法 backtest。
4. **live market is a contract, not a feed**: LivePriceGateway 已经是 in-memory 设计；它的 status='missing' 应该让下游消费者明确 fail，而不是让 factor_snapshot 假装一切正常。
5. **配置默认 = 生产实际**: `dex_ws_enabled=false` 意味着 DEX 流量永远没有 live market。任何依赖"等 WS 启用就好了"的修复都属于半完成。

## 6. 目标

### G1 (P0) — `_market()` 消费 LivePriceGateway snapshot

`_market()` 在投影时按 `(target_type, target_id)` 查 LivePriceGateway。命中且未 stale → 把 mcap/liq/holders/volume 写入 market dict 并标 `live_observed_at_ms`。未命中 → 保留 None 但显式标 `market_data_source='anchor_only'`。

**验收**: 当 dex_ws_enabled=true 且 RKC 在 hot 84 个里时，`pulse_candidates.factor_snapshot_json.market.holders` 不为 NULL。

### G2 (P0) — `_gates` 对市场字段 fail-closed

对 DEX target 的 `holders / liquidity_usd / market_cap_usd`，NULL 输入必须 `blocked_reasons.append("market_data_unverified")` 而不是 `continue`。

**验收**: 当 G1 部署但 live gateway 实际返回 missing 时，pulse_candidates 大部分应该是 `blocked_low_information` 或 `risk_rejected_high_info`，不再是 `trade_candidate`。

### G3 (P0) — Agent prompt 明确 family_scores 是 percentile

`pulse_recommendation_agent_instructions()` 加一段：

> "composite.family_scores.* 是 cohort 内的百分位排名 × 100（cohort_size=normalization.cohort.size）。50 意味着 cohort 中位数，不是绝对中等强度。如果 cohort 大多数 token 的某家族 data_health 都是 'partial'/'missing'，那么该家族的 50 应当被解读为'全员都坏，无信号'，而不是'中性'。请同时引用 normalization.cohort.size 和家族 data_health 判断。"

**验收**: 让 agent 看到 NICHEBABY (cohort=150, semantic_catalyst=49, data_health=partial) 时，agent summary 不能写 "语义催化剂得分尚可"，而应该写 "cohort 全员语义信号缺失"。

### G4 (P0) — `request_json` 持久化真实 prompt（脱敏后）

`pulse_candidate_worker.py:426` 改成存完整 `agent_context`（factor_snapshot + gate_result + selected_posts + available_factor_keys）或至少存 factor_keys + gate_keys diff。

为避免 storage 膨胀，可以：
- 全量存最近 N 天，老的归档到 cold storage
- 只对 verdict=trade_candidate / score_band=high_conviction 全量存
- 其他存 `{context_hash, gate_result, score, recommendation}`

**验收**: 取任意最近 7 天的 pulse_agent_runs.run_id，能精确重放 LLM 当时的输入。

### G5 (P1) — `dex_ws_enabled=true` 部署

`okx-dex-ws-market-stream-and-radar-recovery-cn.md` 的 acceptance criteria 已经存在；目前只是"未启用"。需要：
- 完整 smoke test：检查 OKX 配额、subscription 上限、reconnect 行为
- 监控 `live_market_updates_published / updates_received` 比例
- 配置审核：`dex_ws_subscription_limit / dex_ws_hot_target_ttl_seconds`

### G6 (P1) — `_factor_sum` 修复负向因子和 0 分丢弃

参考上一次 spec 的根因 C/E：
- `attention_acceleration` 负值应贡献负分而非 0
- positive scores 取均值时应包含 0 分（否则一个高分主导整族）

### G7 (P1) — Trigger / cohort 解耦

`min_rank_score=70` 用的是 percentile score，注定让 cohort 前 30% 永远进 pulse。要么：
- 改 trigger 用 raw_alpha_score（绝对值）阈值
- 改 cohort 入选门槛（factor_cohort_v2 当前是"≥2 高置信 OR ≥1 KOL OR 24h 首次出现"，过松）
- 加 "cohort 全员某家族都坏时不归一化"的逃生通道

## 7. Non Goals

- 不改 LivePriceGateway 内存模型（持久化是别的 spec 的范围）
- 不引入新 provider（DEX Screener / Jupiter / Birdeye 等）
- 不动 cohort 归一化算法本身（rank_within_cohort 数学是对的，只是消费侧 misuse）
- 不动 social factor families 内部公式（hard cut 后产生的形态先保留观察）
- 不实现具体代码（本 spec 只定义 why/what；plan 批准后再写 how）

## 8. 风险与权衡

| 风险 | 严重度 | 缓解 |
|---|---|---|
| G2 fail-closed 后，trade_candidate 数量从 27/小时骤降到接近 0（因为 G1 在等 G5 启用 WS） | 高 | G2 必须晚于 G1 + G5 上线，否则会"清零"pulse 输出。或者引入一周 staging window 让 product owner 看到对比数据后再切。 |
| G3 改 prompt 后，agent 输出风格变保守，但仍受 gate 阈值约束 | 中 | 配合 G2 一起，让 gate 端先把过分慷慨切掉，prompt 只是补充语义解读 |
| G4 持久化 prompt 增加 DB 存储 | 中 | 用 verdict 分层 + 时间归档；预估 7 天全量 ~50MB（每条 ~10KB × 27/h × 24h × 7d） |
| G5 OKX WS 配额耗尽 | 高 | 已经设计了 `dex_ws_subscription_limit=100`、TTL 退订冷 target；上线前在 staging 跑 24h 验证 |
| G6 改 `_factor_sum` 让分数广泛下降，trigger gate 命中率降低 | 中 | 跟 G7 一起做：trigger 阈值同时调整 |
| 已经发出去的 27/小时 trade_candidate 历史数据，被下游 notification / outcome 视为信号 | 中 | 加 schema_version bump，下游可识别本次 hard cut 前的数据 |

## 9. 验证标准（端到端）

部署 G1+G2+G3+G4 后，应满足：

```sql
-- 1. 大部分 pulse_candidates 拿到 live market 字段
SELECT
  COUNT(*) FILTER (WHERE factor_snapshot_json->'market'->>'holders' IS NOT NULL) * 1.0 / COUNT(*) AS holders_fill_rate
FROM pulse_candidates
WHERE updated_at_ms > NOW() - interval '1 hour';
-- 期望: >= 0.50（DEX WS 启用后，hot 84 + CEX 16 覆盖一大半）

-- 2. trade_candidate 不再 100%
SELECT pulse_status, COUNT(*)
FROM pulse_candidates WHERE updated_at_ms > NOW() - interval '1 hour'
GROUP BY pulse_status;
-- 期望: trade_candidate < 50%, token_watch + blocked + risk_rejected_high_info > 50%

-- 3. agent run request_json 已持久化
SELECT 
  COUNT(*) FILTER (WHERE jsonb_typeof(request_json->'factor_snapshot') = 'object') AS with_full_snapshot,
  COUNT(*) FILTER (WHERE request_json = '{}'::jsonb OR request_json ? 'context_hash' AND NOT request_json ? 'factor_snapshot') AS hash_only
FROM pulse_agent_runs WHERE started_at_ms > (EXTRACT(EPOCH FROM NOW()) - 3600)*1000;
-- 期望: with_full_snapshot > 0, hash_only = 0 (或仅对低 score 的 candidate)

-- 4. agent summary 引用 cohort 上下文
SELECT 
  COUNT(*) FILTER (WHERE agent_recommendation_json::text ILIKE '%cohort%') AS cohort_aware
FROM pulse_candidates WHERE updated_at_ms > NOW() - interval '1 hour';
-- 期望: cohort_aware > 0
```

## 10. Open Questions

1. **G1 数据合并**: `_market()` 同时拿 anchor (DB) + live (in-memory gateway)。需要决定：
   - 是 `_market()` 直接调 `live_market_gateway.snapshot()`（projection 引入跨域依赖）
   - 还是 projection runtime 提前把 live snapshot 注入 row（`_hydrate_live_market`）后传给 build
   - 推荐后者，保持 projection 对 platform/db 的 purity
2. **G2 严苛度**: DEX 资产 NULL → block 是直接 `discard` 还是降级到 `watch` 上限？建议降级到 `watch`，让 token 还能被 UI 看到、但不能被 pulse 当成 trade_candidate。
3. **G3 prompt 长度**: 加 cohort 解读后 system prompt 会增长 200-300 token。结合 model context 评估对延迟和成本的影响。
4. **G4 retention**: full prompt 保留多久？建议 30 天热 + 90 天冷归档（HEAD 这个值待 ops 确认）。
5. **G7 cohort 改造**: 这是更深层的设计决策（cohort 是 alpha 的定义边界）。是否要先单独写一个"cohort definition v3"的 spec？

## 11. 参考数据点（2026-05-12 11:48 UTC）

| 指标 | 真实值 | 上次（02:31）|
|---|---|---|
| 最近 1h pulse_candidates 数 | 33（27 token_target + 6 source_seed） | 24（19+5） |
| token_target 中 trade_candidate 比例 | 27/27 = 100% | 19/19 = 100% |
| factor_snapshot.market.holders / mcap / liq 填充率 | 0/115 = 0%（6h 内） | 0/19 = 0%（1h） |
| cohort_size (median) | 150 | 91 |
| families.timing_risk score 分布 | 全部 = 50 | 全部 = 51 |
| families.semantic_catalyst score 分布 | 全部 = 49 | 全部 = 51 |
| families.social_heat score 顶部 | 100 | 99 |
| pulse_agent_runs.request_json 内容 | `{context_hash}` only | `{context_hash}` only |
| API row.live_market.status | `missing` (100% of returned rows) | (字段当时不存在) |
| LivePriceGateway dex_ws_enabled | false (configured=false) | (gateway 当时不存在) |
| LivePriceGateway updates_received | 0 (DEX) + 16 (CEX) | — |
| ResolutionRefreshWorker 状态 | 运行中, 替代旧 token_discovery_worker | (尚未引入) |
| 24h resolved tokens | (待统计，hot resolution 后估计 >2500) | 2043 |
| 24h resolved without OKX evidence 比例 | 待复测 | 54% |

## 12. 一句话给下个 spec writer

> 上次 spec 修了 OKX 采集层（"数据从哪儿来"），这次 spec 必须修消费层（"数据如何被 factor_snapshot / gate / agent / API 消费"），重点在 `_market()` 和 `_gates()` 这两个硬编码点。同时把 `dex_ws_enabled` 从默认 false 推到 production。
