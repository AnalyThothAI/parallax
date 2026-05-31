# Token Radar 评分闭环重构 Spec

Date: 2026-05-06

## 背景

当前 Token Radar 已经具备一条不错的确定性数据链路：

```text
GMGN public Twitter stream
-> normalized event
-> deterministic entity extraction
-> token identity / attribution
-> rolling token windows
-> social heat / quality / propagation / tradeability / timing
-> opportunity score
-> frozen token signal snapshot
-> 6h / 24h outcome settlement
-> score bucket evaluation
```

但这条链路目前更像一个“可解释 heuristic ledger”，还不是一个真正能自我校准的交易信号系统。最明显的症状是 `tradeability` 经常接近或等于 100。根因不是单个数据点异常，而是评分语义有偏：当前 `tradeability_v2` 奖励的是字段存在性和快照新鲜度，而不是真实可交易质量。

这份 spec 目标是把 Token Radar 从“热度排行榜”推进到“可闭环验证的注意力交易雷达”。

## 第一性原理

Token Radar 的核心问题不是“哪个 token 最热”，而是：

```text
一个可行动机会 =
  异常注意力
  x 有信息含量的证据
  x 独立扩散
  x 可交易市场条件
  x 时间优势
  - 操纵风险
  - 数据健康风险
```

五个组件必须回答五个互相独立的问题：

1. **Heat:** 当前讨论是否相对自身历史和当前 stream 异常升温？
2. **Quality:** 这些帖子是具体证据，还是重复口号、低信息刷屏或错误归因？
3. **Propagation:** 注意力是否从少数作者扩散到独立作者群，还是单点广播？
4. **Tradeability:** 这个 token 是否真的能以可接受成本进出，而不只是有 CA 和 market snapshot？
5. **Timing:** 社交信号是否领先价格，还是价格已经先动导致 chase risk？

重要边界：

- Score 是 deterministic ranking score，不是上涨概率。
- LLM 可以做 watched-account enrichment，但不进入 live token facts 的事实来源。
- `coverage=public_stream` 永远不是 Twitter/X firehose。
- 数据健康度必须和 score 分开表达。数据缺失不能被当成中性好分。
- 闭环评估必须能指出哪个组件有效或无效，而不只是看总分 bucket。

## 现状问题

### 1. Tradeability 饱和

`tradeability_v2` 当前逻辑是：

```text
+30 resolved_ca
+25 fresh_market
+20 market_cap_present
+15 liquidity_present
+10 pool_present
```

而 `RollingTokenFlow` 已经只返回 `token_id`、`chain`、`address` resolved 的 attribution rows。GMGN payload 又经常带 `market_cap`、`liquidity`、`pool`。因此很多 token 天然获得 100。

这造成两个问题：

- `tradeability` 对排序没有区分度。
- `opportunity` 被一个低信息量组件抬高。

### 2. Opportunity 权重漂移

已有中文计划里写的是：

```text
0.30 heat + 0.25 quality + 0.20 propagation + 0.15 tradeability + 0.10 timing
```

实现是：

```text
0.26 heat + 0.22 quality + 0.28 propagation + 0.18 tradeability + 0.06 timing
```

在 `tradeability` 饱和、`timing` 过弱的情况下，总分会更像“传播结构 + 可展示市场信息”，而不是“异常注意力 + 质量 + 是否早”。

### 3. Quality 没有真正聚合 post quality

`discussion_quality_v2` 暴露了 `avg_post_quality`，但没有在 aggregate 公式里计算或使用它。当前主要依赖：

- direct mention ratio；
- avg attribution confidence；
- text informative heuristic；
- watched source count；
- duplicate text share；
- market context term count。

其中 `informative` heuristic 偏宽，例如包含 `new`、`pump`、`breakout` 或字数足够就可能被算作 informative。它能做初筛，但不足以代表“交易员可用证据质量”。

### 4. Sparse baseline 的 heat 被奖励过多

当历史不足时，`new_burst_score` 会给 surprise points；但只要有 `new_burst_score`，`insufficient_baseline` cap 就不会生效。新 token 确实应该允许被发现，但 sparse baseline 需要显式降置信度，而不是近似当作强 z-score。

### 5. 闭环只看总分桶

当前 `token_signal_evaluation_service` 按最终 `opportunity_score` 分桶，看 hit rate 和平均 outcome。这无法回答：

- Heat 高是否真的有 forward edge？
- Quality 高是否提高命中率或降低回撤？
- Tradeability 100 是否无区分度？
- Timing chase risk 是否真的降低后续收益？
- public-only、duplicate、thin baseline 等 risk caps 是否有效？

闭环架子已经有了，但诊断粒度不够。

## 目标

### Product Goals

- 让 radar row 的 `Heat / Quality / Propagation / Tradeability / Timing` 都有独立含义。
- 让 Tradeability 的分布从“几乎全 100”变成有区分度的交易可行性刻度。
- 让 Quality 真实反映证据质量，而不只是“有 CA + 有热词”。
- 让 Opportunity 能解释 driver/watch/discard，且不会被某个饱和组件污染。
- 让评分版本能通过 frozen snapshot 和 outcome report 迭代，而不是凭感觉改权重。

### Engineering Goals

- 保持 hot path deterministic。
- 所有 score 输出继续包含 reasons、risks、contributions、risk_caps、data_health。
- 所有评分版本显式 bump version。
- 新算法先 shadow 输出，再替换主排序。
- 评估服务能做 component-level bucket diagnostics。

## Non-Goals

- 不自动交易。
- 不把 score 表示成概率。
- 不要求短期接入完整 DEX trade tape。
- 不要求短期接入完整 Twitter graph。
- 不要求 LLM 给所有 public-stream 帖子打质量分。
- 不为了追求复杂度引入黑盒模型。

## 新评分模型

### Score Output Contract

所有组件必须返回：

```json
{
  "score": 0,
  "score_version": "component_vN",
  "reasons": [],
  "risks": [],
  "hard_risks": [],
  "contributions": [
    {"feature": "feature.name", "value": 0, "reason": "reason_key"}
  ],
  "risk_caps": [
    {"risk": "risk_key", "cap": 0}
  ],
  "data_health": {},
  "calibration": {
    "sample_size_status": "unknown | thin | adequate",
    "score_distribution_status": "unknown | saturated | healthy"
  }
}
```

`calibration` 可以先只在 component evaluation 里生成，不一定每个 live response 都有完整历史分布。

## Tradeability V3

### 语义

Tradeability 回答：

> 如果这个社交信号是对的，我能不能以可接受成本和风险交易这个 token？

它不是：

- 是否有 CA；
- 是否有 GMGN snapshot；
- 是否能打开 GMGN 链接；
- 是否 market cap 字段不为空。

### Inputs Now

来自现有 market snapshot：

- `market_status`
- `snapshot_age_ms`
- `market_cap`
- `liquidity`
- `pool_status`
- `holder_count`
- `volume_24h`
- `price_change_before_social_pct`
- `lookahead_risk`

### Future Inputs

后续可加入：

- DEX OHLCV candles；
- estimated slippage；
- buy/sell imbalance；
- LP age / LP change；
- top holder concentration；
- holder growth；
- smart wallet net flow。

### Hard Gates

这些不是加分项，而是 eligibility / cap：

```text
unresolved identity         -> hard risk, cap 20
lookahead risk              -> hard risk, cap 40
missing market snapshot     -> hard risk, cap 35
missing market cap          -> hard risk, cap 40
missing liquidity           -> cap 55
stale market > 30m          -> cap 70
pool missing                -> cap 75
```

### Score Formula

V3 使用连续特征，不再奖励简单存在性：

```text
tradeability_v3 =
  0.35 * liquidity_depth_score
  + 0.20 * market_cap_fit_score
  + 0.15 * volume_liquidity_score
  + 0.10 * holder_depth_score
  + 0.10 * market_freshness_score
  + 0.10 * pool_readiness_score
```

建议初始实现：

```text
liquidity_depth_score:
  log score from 5k to 2m USD

market_cap_fit_score:
  0 below 20k
  ramps to 100 around 500k-50m
  fades above 200m for this social-attention product

volume_liquidity_score:
  volume_24h / liquidity
  too low means dead pool
  too high can mark churn/manipulation risk

holder_depth_score:
  log score from 50 to 50k holders

market_freshness_score:
  100 <= 5m
  80 <= 15m
  60 <= 30m
  stale cap after 30m

pool_readiness_score:
  100 if pool ready
  0 if missing
```

### Risk Caps

```text
liquidity < 5k        -> cap 35, risk "micro_liquidity"
liquidity < 25k       -> cap 50, risk "thin_liquidity"
market_cap < 20k      -> cap 40, risk "micro_cap_unstable"
holder_count < 50     -> cap 45, risk "thin_holders"
volume_24h missing    -> risk only initially, no hard cap
volume/liquidity > 20 -> cap 65, risk "churn_or_manipulation_risk"
```

### Acceptance

- A token with fresh market, resolved CA, liquidity 250k, mcap 2m, pool ready should score high but not automatically 100.
- A token with liquidity 800 and mcap 12k must not score above 40 even if all fields exist.
- A token with missing liquidity should never be `driver`.
- Distribution check on live/frozen snapshots: fewer than 20% of rows should be exactly 100 unless market data is genuinely exceptional.

## Discussion Quality V3

### 语义

Quality 回答：

> 这些社交证据是否足够具体、原始、独立、可信，能帮助交易员判断事件？

它不是 raw heat，也不是 watched account 一票否决/一票通过。

### Inputs

- aggregate `post_quality` from token posts；
- direct/payload/CA evidence mix；
- attribution confidence and selected-symbol margin；
- duplicate text share；
- informative text ratio；
- watched source count；
- independent author count from propagation；
- account quality when sample size is adequate；
- LLM semantic utility only as optional async label。

### Required Change

`TokenFlowService._discussion_quality_features` 必须计算当前 scoring window 的 post quality aggregate：

```text
post_quality_median
post_quality_top_quartile
post_quality_weighted_avg
low_quality_post_share
```

不要只把 `avg_post_quality` 作为空字段透出。

### Score Formula

```text
discussion_quality_v3 =
  0.25 * post_quality_aggregate
  + 0.20 * token_specificity_score
  + 0.15 * attribution_confidence_score
  + 0.15 * originality_score
  + 0.10 * independent_evidence_score
  + 0.10 * watched_or_account_quality_score
  + 0.05 * semantic_utility_score
```

### Token Specificity

```text
direct GMGN token payload / CA     high
CA in text                         high
selected symbol with strong margin medium
symbol-only selected               lower
unresolved symbol                  not in token-flow
```

### Informative Heuristic Tightening

`informative` 不应只因为字数够或出现宽泛词就成立。

V3 需要区分：

```text
strong informative:
  CA, pool, mcap/liquidity/volume number, launch/listing source, named catalyst, concrete risk, chart/price with numbers, URL source

weak informative:
  "new", "pump", "breakout", "send it", pure meme phrase

spam pattern:
  excessive cashtags, repeated slogans, identical fingerprint, no concrete claim
```

### Sample Size Caps

```text
mentions < 2:
  cap quality 45 unless direct watched CA evidence

mentions < 3 and no watched source:
  cap quality 60

duplicate_text_share >= 0.5:
  cap quality 45

low_quality_post_share >= 0.6:
  cap quality 55
```

### Acceptance

- Three duplicated CA spam posts must not get high quality merely because they include CA.
- One high-quality watched CA post can be `watch`, but should not become `driver` without heat/propagation confirmation.
- Token-level `avg_post_quality` must be computed from real current-window posts and visible in score ledger.

## Social Heat V3

### 语义

Heat 回答：

> 当前讨论是否异常升温？

Heat 不回答：

- 是否可以买；
- 是否帖子质量高；
- 是否会涨。

### Current Strengths

已有设计方向是对的：

- trailing windows；
- real multi-window counts；
- previous_mentions；
- EWMA / robust z；
- new_burst；
- stream share；
- watched share；
- risk caps。

### Required Change

Sparse baseline 必须进入 data health 和 score cap：

```text
baseline_status != ready:
  risk "sparse_baseline"
  cap heat 75 by default

mentions < 3 and baseline_status != ready:
  cap heat 60 unless watched_first_seen

new_burst_score:
  can add attention discovery points
  cannot pretend to be calibrated surprise
```

### Score Split

V3 建议拆成两个内部字段：

```text
attention_score:
  raw current-window attention strength

surprise_confidence:
  how reliable the baseline surprise estimate is
```

Live response 可以仍返回一个 `score`，但 ledger 必须显示：

```text
current_mentions
baseline_surprise
new_burst_discovery
baseline_confidence_cap
```

### Acceptance

- 历史 sparse 的 1 条 public-only mention 仍然低分。
- 历史 sparse 的 5 条 independent mentions 可以 high watch，但不能因 sparse baseline 自动 driver。
- baseline_ready、baseline_status、sample_count、nonzero_sample_count、zero_slot_count 必须在 score/data_health 可见。

## Propagation V3

### 语义

Propagation 回答：

> 注意力是否正在独立扩散？

当前 v2 已经比原先好：有 bucket、新作者、effective authors、top share、duplicate share、reproduction proxy。

### Required Change

Propagation 需要更清楚地区分：

- seed；
- ignition；
- expansion；
- concentration；
- fade。

V3 风险上限建议：

```text
phase seed             -> cap propagation 55
phase concentration    -> cap propagation 60
phase fade             -> cap propagation 50 unless heat still rising in 5m
top_author_share > .75 -> cap 50
duplicate_share > .50  -> cap 55
```

### Acceptance

- 高作者数但高度重复文本，不能 expansion。
- 多作者但 top author share 高，不能 driver。
- `fade` phase 必须影响 opportunity decision，不只是显示文案。

## Timing V5

### 语义

Timing 回答：

> 这个社交信号相对价格是早、同步、还是晚？

当前 `timing_v4` 基本只有 neutral / pending / unavailable / chase_risk，且权重只有 6%。这让 radar 不够交易化。

### States

```text
social_leads_price:
  heat high, price_change_before small, price_change_since_social small or not yet moved

social_confirms_price:
  heat high and price moved after social start

price_leads_social:
  price moved materially before social start

chase_risk:
  price_change_before_social_pct >= threshold

market_pending:
  observation pending/running

market_unavailable:
  provider missing/error/dead
```

### Score

```text
social_leads_price      75-85
social_confirms_price   60-75
neutral                 50
market_pending          45
market_unavailable      35
chase_risk              25-40
```

Thresholds should be volatility-aware later. V5 can start with fixed thresholds:

```text
price_change_before_social_pct >= 15% -> chase_risk
price_change_since_social_pct <= 5% with high heat -> social_leads_price
price_change_since_social_pct > 5% and before_social < 10% -> social_confirms_price
```

### Acceptance

- A token where price moved 35% before social start must not be `driver`.
- A high heat token with price not moved yet should receive timing advantage.
- `market_pending` should keep the item visible but prevent overconfident driver unless other components are exceptional and caps allow it.

## Opportunity V4

### Weighting

Return to the documented thesis:

```text
opportunity_v4 =
  0.30 * heat
  + 0.25 * quality
  + 0.20 * propagation
  + 0.15 * tradeability
  + 0.10 * timing
```

The exact weights can later be changed, but only after component-level evaluation shows evidence.

### Decision Gates

Driver requires:

```text
score >= 72
heat >= 68
quality >= 62
propagation >= 62
tradeability >= 65
timing >= 50
phase in expansion | ignition
no hard_risks
no public_only_unconfirmed cap
no sparse_baseline cap below final score
no chase_risk
```

Watch requires:

```text
score >= 45
tradeability >= 45
and at least one:
  heat >= 55
  propagation >= 45
  watched confirmation
  timing social_leads_price
```

Discard if:

```text
hard_risks present
duplicate/repeated cluster hard cap triggered
tradeability < 35
identity/market missing
```

### Risk Caps

Opportunity must apply the minimum cap from all component caps.

Recommended cross-component caps:

```text
hard_risk                         cap 40
public_only_unconfirmed           cap 68
duplicate/repeated_text_cluster   cap 50
author_concentration_high         cap 60
chase_risk                        cap 50
sparse_baseline_public_only       cap 62
missing_liquidity                 cap 55
thin_mentions                     cap 45
```

## Closed Loop V2

### Current State

已有：

- `ops freeze-token-signals`
- `ops settle-token-signals`
- `token-signal-evaluations`
- `token_signal_snapshots`
- `token_signal_outcomes`
- `token_score_evaluations`

但这些主要评价 final opportunity bucket。

### Required Reports

新增 component-level evaluation：

```text
component_score_evaluations
```

或在现有 `token_score_evaluations` 扩展字段：

```text
component_key:
  opportunity | heat | quality | propagation | tradeability | timing

bucket_label:
  component score bucket

filters:
  window, scope, horizon, score_version, decision, risk_key
```

每个 report 至少输出：

```text
snapshot_count
settled_count
settlement_coverage
avg_actual_return
avg_abnormal_return
avg_normalized_outcome
median_normalized_outcome
directional_hit_rate
wilson_low
wilson_high
```

### Interaction Reports

必须能看这些组合：

```text
high_heat + high_quality
high_heat + low_quality
high_heat + low_tradeability
high_heat + chase_risk
high_heat + social_leads_price
public_only vs watched_confirmed
duplicate_text_cluster vs clean_original
sparse_baseline vs baseline_ready
tradeability_deciles
```

### Calibration Dashboard Acceptance

一个评分版本能升级为主排序，至少需要：

- 每个主要 window 有足够 settled samples；
- settlement coverage 可见；
- opportunity score bucket 的 avg normalized outcome 大体单调；
- high quality bucket 优于 low quality bucket；
- tradeability 高分不再全挤在 100；
- chase_risk bucket 显著弱于 non-chase；
- public-only unconfirmed 不应高于 watched-confirmed；
- 风险 cap 触发样本的 forward return 不应系统性优于未 cap 样本，否则 cap 逻辑需要复审。

## API / CLI Changes

### API

新增或扩展：

```text
GET /api/token-signal-evaluations?component=opportunity|heat|quality|propagation|tradeability|timing
GET /api/token-signal-interaction-evaluations?kind=high_heat_low_quality
```

如果不新增 endpoint，也可以在现有 `/api/token-signal-evaluations` 加 query params：

```text
component=
risk=
decision=
refresh=
```

### CLI

新增：

```bash
uv run parallax token-signal-evaluations --horizon 6h --window 5m --scope all --component heat
uv run parallax token-signal-evaluations --horizon 6h --window 5m --scope all --component tradeability
uv run parallax token-signal-interactions --horizon 6h --window 5m --kind high_heat_low_quality
```

Ops workflow:

```bash
uv run parallax ops freeze-token-signals --window 5m --limit 200
uv run parallax ops settle-token-signals --horizon 6h --limit 500
uv run parallax token-signal-evaluations --horizon 6h --window 5m --scope all --component opportunity
uv run parallax token-signal-evaluations --horizon 6h --window 5m --scope all --component tradeability
```

## Rollout Plan

### Phase 1: Shadow Scoring

- Add `tradeability_v3`, `discussion_quality_v3`, `social_heat_v3`, `timing_v5`, `social_opportunity_v4`.
- Keep current live sorting on `social_opportunity_v3`.
- Include shadow payload under:

```json
{
  "shadow_scores": {
    "tradeability_v3": {},
    "discussion_quality_v3": {},
    "social_heat_v3": {},
    "timing_v5": {},
    "opportunity_v4": {}
  }
}
```

or run through freeze snapshots only if live payload size is a concern.

### Phase 2: Evaluation

- Freeze both current and shadow versions.
- Settle 6h and 24h.
- Generate component-level and interaction reports.
- Check distribution saturation, monotonicity, and risk cap sanity.

### Phase 3: UI Exposure

- Score tab shows both active and shadow if enabled.
- Tradeability card displays actual liquidity/mcap/volume/holders contributions, not field presence.
- Quality card displays post quality aggregate.
- Heat card displays baseline confidence and sparse baseline cap.
- Timing card displays social-leads/confirm/chase state.

### Phase 4: Promote

Only promote `opportunity_v4` to default ranking after:

- all critical tests pass；
- shadow evaluation is not worse than v3；
- Tradeability no longer saturates；
- manual spot checks on top driver/watch rows make trader sense。

## Test Plan

### Unit Tests

Add tests:

- `tests/test_tradeability_scoring.py`
  - low liquidity field-present token scores low；
  - high liquidity token scores high but not necessarily 100；
  - missing liquidity caps driver eligibility；
  - stale market cap applies。

- `tests/test_discussion_quality_scoring.py`
  - repeated CA posts cap quality；
  - aggregate post_quality affects token quality；
  - weak informative terms do not over-score；
  - thin sample cap applies。

- `tests/test_social_heat_scoring.py`
  - sparse baseline adds cap even with new_burst；
  - baseline_ready high z still scores high；
  - public-only thin mention remains low。

- `tests/test_timing_scoring.py`
  - social_leads_price；
  - social_confirms_price；
  - chase_risk；
  - market_pending/unavailable。

- `tests/test_opportunity_scoring.py`
  - v4 weights match spec；
  - chase_risk prevents driver；
  - sparse public-only prevents driver；
  - high heat low quality remains watch/discard。

- `tests/test_token_signal_evaluation_service.py`
  - component buckets evaluate correctly；
  - interaction reports compute settled_count and coverage correctly。

### Contract Tests

- `/api/token-flow` includes new score versions and data_health fields.
- `/api/token-signal-evaluations?component=tradeability` returns component bucket report.
- Existing clients remain compatible while shadow scoring is hidden or optional.

### Data QA

On a real frozen sample:

```text
distribution(tradeability_v3.score)
distribution(quality_v3.score)
distribution(heat_v3.score)
top 20 opportunity_v4 rows manual review
bottom 20 rejected rows manual review
```

Required manual checks:

- no obvious micro-liquidity token marked driver；
- no repeated spam cluster marked high quality；
- no stale/missing market token marked driver；
- high heat rows show actual posts and timeline evidence。

## Acceptance Criteria

This project is done when:

1. Tradeability is no longer mostly 100 on live/frozen samples.
2. Tradeability ledger shows numeric liquidity/mcap/volume/holder contributions.
3. Discussion Quality uses real post-quality aggregate.
4. Sparse baseline is visible and capped.
5. Timing can distinguish `social_leads_price`, `social_confirms_price`, and `chase_risk`.
6. Opportunity v4 uses documented weights or explicitly documents any evidence-backed deviation.
7. Component-level evaluation exists for all five score components.
8. Interaction evaluation can compare high-heat/low-quality and high-heat/high-quality cohorts.
9. Score tab surfaces hard risks, risk caps, component contributions, and data health before decorative explanation.
10. README or architecture docs state that score is deterministic ranking, not probability.

## Open Questions

1. Tradeability mcap fit should be tuned for which target universe: microcap meme discovery, midcap momentum, or both?
2. Should `volume_24h / liquidity` high values be treated as healthy activity or churn risk by default?
3. How many settled samples are enough before account quality can enter live ranking?
4. Should public-only unconfirmed cap be stricter for 5m than 1h/4h?
5. Should `driver` require at least one of watched confirmation, account-quality confirmation, or strong clean independent propagation?

## Implementation Notes

Recommended order:

1. Implement `tradeability_v3` first, because it explains the current obvious 100 saturation.
2. Implement `discussion_quality_v3` post-quality aggregation.
3. Add `social_heat_v3` sparse baseline caps.
4. Add `timing_v5` states and restore timing weight.
5. Add `opportunity_v4` with stricter gates.
6. Add component-level evaluation reports.
7. Shadow-run before promoting.

Do not combine all changes into one opaque score rewrite. Each component should be independently testable and independently evaluable.
