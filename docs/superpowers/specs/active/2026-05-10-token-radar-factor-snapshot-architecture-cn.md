# Token Radar Factor Snapshot Architecture Spec

**Status**: Draft, awaiting review  
**Date**: 2026-05-10  
**Owner**: Codex with Qinghuan  
**Related**:

- `docs/superpowers/specs/active/2026-05-08-auditable-token-radar-design-cn.md`
- `docs/superpowers/specs/active/2026-05-09-standardized-social-factor-pipeline.md`
- `docs/superpowers/specs/active/2026-05-10-token-identity-evidence-hard-cut-spec-cn.md`
- `docs/superpowers/plans/active/2026-05-08-signal-lab-pulse-agent-concrete-cn.md`

## Background

Token Radar 已经不是早期的单公式热度榜。当前 `TokenRadarProjection` 从 `TokenRadarSourceQuery` 拉取 token intent、resolved target、account profile、LLM social extraction、identity current、price feed、latest price observation、market cap、liquidity、volume、open interest、holders 和 message-level price fields；这些输入在查询层已经存在，见 `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py:16` 到 `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py:99`。

投影层已经把 scoring 拆成 `heat / quality / propagation / tradeability / timing / opportunity`，并在 rebuild 中读取窗口、分组、投影、做 cohort rank，再写 `token_radar_rows`，见 `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:13` 到 `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:33` 和 `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:48` 到 `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:75`。

因子雏形也已经存在。`RadarFeatureSet` 显式承载 `attention / heat / quality / propagation / tradeability / timing`，见 `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py:16` 到 `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py:27`。窗口聚合已经计算 `mentions_5m / mentions_1h / mentions_4h / mentions_24h / unique_authors / watched_mentions / stream_share`，见 `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py:96` 到 `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py:113`。heat 层已有 `weighted_mentions` 和 baseline z，见 `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py:125` 到 `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py:163`。quality 和 propagation 已经计算 duplicate share、informative count、LLM hints、independent authors、effective authors、top author share、reproduction rate，见 `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py:185` 到 `src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py:255`。

atomic 层已有纯函数：`tweet_quality()` 用 GMGN 平台 followers、user tags 和 first-seen age 计算 per-mention author quality；`mention_confidence_from_status()` 把 resolver status 映射成 confidence，见 `src/gmgn_twitter_intel/domains/token_intel/services/atomic_mention.py:1` 到 `src/gmgn_twitter_intel/domains/token_intel/services/atomic_mention.py:72`。

normalization 也已有基础设施：`token_baseline_v2()` 计算 baseline status、EWMA z、robust z 和 sparse-history health，见 `src/gmgn_twitter_intel/domains/token_intel/scoring/baseline_scoring.py:10` 到 `src/gmgn_twitter_intel/domains/token_intel/scoring/baseline_scoring.py:84`；`rank_within_cohort()` 已能在 active cohort 中做 cross-sectional percentile rank，见 `src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py:1` 到 `src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py:33`。

当前缺口在于：这些能力仍以 `score_json` 为中心输出，factor 的 raw value、atomic source、window aggregate、normalization、confidence、freshness、hard gate 没有成为一个稳定的产品 contract。Pulse worker 现在把 `radar_score`、`market_context` 和 timeline context 传给 agent/gate，见 `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:242` 到 `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:275` 和 `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:435` 到 `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:442`。agent schema 仍是 thesis-first，字段集中在 `summary_zh / why_now_zh / bull_case_zh / bear_case_zh / confirmation_triggers_zh / top_risks`，见 `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_thesis.py:34` 到 `src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_thesis.py:55`；Agents SDK client 也没有工具，只基于输入 context 生成 typed output，见 `src/gmgn_twitter_intel/integrations/openai_agents/pulse_thesis_agent_client.py:127` 到 `src/gmgn_twitter_intel/integrations/openai_agents/pulse_thesis_agent_client.py:167`。

通知层进一步放大了这个问题。Signal Pulse 规则把 `token_watch` 固定映射为 high，把 `risk_rejected_high_info` 映射为 warning，见 `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py:19` 到 `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py:31`；候选读取只按 status/displayable 过滤，见 `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py:361` 到 `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py:427`；正文主要展示 thesis 风险和 confirmation，不展示 holders、liquidity、market cap、source quality 等事实，见 `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py:515` 到 `src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py:538`。

最典型的链上/市场缺口在 `tradeability_score()`：DEX Asset 当前把 `market_cap_present` 和 `liquidity_present` 当作正向贡献，而不是按绝对质量、比例质量和 hard threshold 判断，见 `src/gmgn_twitter_intel/domains/token_intel/scoring/tradeability_scoring.py:27` 到 `src/gmgn_twitter_intel/domains/token_intel/scoring/tradeability_scoring.py:37` 和 `src/gmgn_twitter_intel/domains/token_intel/scoring/tradeability_scoring.py:91` 到 `src/gmgn_twitter_intel/domains/token_intel/scoring/tradeability_scoring.py:143`。因此低 holders、低 liquidity 的 token 仍可能在上层成为 high-priority watch。

## Problem

Token Radar 现在有 score，但缺少专业 factor snapshot。系统已经能算一批信号，却没有把每个信号分层表达为 raw、atomic、window、normalized factor、hard gate 和 provenance；Pulse agent 看到的是分数与上下文，不是可审计因子；通知最终展示的是模型 thesis，不是事实卡。因此当社交文本弱、holders 很低、流动性很薄或 market stale 时，系统仍可能生成看起来完整但实质空泛的 `token_watch` / confirmation / risks。

## First Principles

1. **因子必须四层分离**：raw data 负责清洗与对齐，atomic signal 负责单条事件语义，window aggregate 负责时间尺度，normalized factor 负责跨 token 可比。任何直接从 raw count 到 final score 的路径都会把 size、噪声、缺失数据混进结论。
2. **score 是派生结论，不是事实源**：`opportunity` 和推荐状态只能从 factor snapshot 派生；下游产品、Pulse gate、agent explanation 必须能回到具体 factor key、raw value、source refs 和 data health。
3. **hard gate 先于 agent 和通知**：身份未确定、market stale、DEX liquidity/holders 低于最低产品阈值、source quality 低的信息，不应被 agent 文案修饰成 high-priority alert。
4. **缺失不是安全**：没有 holder distribution、没有 tax/honeypot、没有 transfer flow 时，snapshot 必须显式标记为 `missing` 或 `unknown`，不能把缺失当成无风险。

## Goals

- **G1 Factor Snapshot Contract**：每个 resolved Token Radar row 都产出一个 `factor_snapshot`，至少覆盖 identity、social_attention、social_quality、social_semantics、market_quality、timing 六个 family；每个 family 内的关键 factor 都包含 raw/window value、normalized score 或缺失原因、confidence、freshness、source refs、risk flags 和 hard gate flags。
- **G2 Social Factor Professionalization**：社交因子按 `raw -> atomic -> window -> normalized factor` 输出，不新增实时 LLM 调用；优先消费现有 `account_profiles`、`social_event_extractions`、token intent resolution 和 timeline 数据。
- **G3 Token / On-Chain-Lite Factor Professionalization**：DEX Asset 不再只因 `market_cap/liquidity` 字段存在就获得高 tradeability；holders、liquidity、market cap、market freshness、pool readiness、price movement 都必须以质量因子和 hard gate 呈现。CEX token 使用 CEX volume/open interest/native market freshness，不套用 DEX holders/liquidity gate。
- **G4 Pulse Agent Repositioning**：Pulse agent 的输入事实源从 `radar_score + timeline_context + market_context` 转为 `factor_snapshot`；agent 只做 recommendation 和解释，不生成未由 factor 支撑的事实。
- **G5 Notification First-Screen Facts**：Signal Pulse 通知和 UI 详情页首先展示 factor snapshot 中的事实卡和 gate 结果，再展示 agent explanation。high/critical severity 必须由 deterministic factor gate 授权。
- **G6 Hard Cut Runtime**：实现阶段必须一次性切换当前生产投影、Pulse、notification 和 read models 到 factor snapshot contract；运行时代码不得保留从旧 `score_json`、`radar_score_json`、`market_context_json` 推回新 contract 的兼容 fallback。

## Non-Goals

- 不构建完整量化研究平台，不在本 spec 中引入 rolling IC/ICIR 权重、PCA、GBDT、在线学习或回测优化。
- 不引入 Twitter API v2 engagement、view count、retweet graph、Louvain community detection 或 DistilBERT 蒸馏。
- 不实现完整 holder distribution、top holder concentration、transfer flow、CEX netflow、smart-money labels；当前仅设计基于现有 market observations 的 on-chain-lite / market proxy 因子。
- 不新增 Pulse 多 agent handoff，不让 agent 直接访问数据库或外部网络。
- 不提供旧 `score_json` / thesis-first Pulse 的运行时兼容层；历史数据可以留在数据库里，但当前投影和当前读路径必须只读 factor snapshot contract。

## Target Architecture

Token Radar 升级为 factor-first architecture。现有 `TokenRadarProjection` 仍是生产投影入口，但其内部职责从“构造特征并直接打分”调整为：

```text
TokenRadarSourceQuery
  -> Atomic Signal Builders
  -> Window Factor Aggregators
  -> Normalizers
  -> TokenFactorSnapshot
  -> Score / Gate / Rank
  -> Token Radar row, Pulse candidate, API, notification
```

### Component Ownership

- **Raw source layer**：继续由 `events`、`token_intents`、`token_intent_resolutions`、`account_profiles`、`social_event_extractions`、`price_observations`、identity current 和 price feeds 提供。
- **Atomic signal layer**：按事件和市场快照生成不可聚合前丢失的信息，例如 mention confidence、author quality、text informativeness、duplicate fingerprint、semantic direction、impact、novelty、market snapshot age。
- **Window factor layer**：按 target/window/scope 聚合 atomic signals，窗口至少覆盖 1h、4h、24h；5m 可作为 attention/timing 子窗口，不必成为独立 Pulse eligibility 窗口。
- **Normalization layer**：每个可比较 factor 同时给出 time-series baseline signal 和 cross-sectional percentile/rank；数据不足时必须返回 sparse/unknown health，而不是硬填 0 或 50。
- **Factor snapshot layer**：作为 Token Radar、Pulse gate、agent explanation、notification 和 UI 的共同事实源。
- **Score/gate layer**：从 factor snapshot 派生 product score、status、severity eligibility 和 risk caps。score 不再直接读取 raw rows。
- **Agent explanation layer**：只消费 factor snapshot 和 gate result。输出推荐、解释、升级条件、无效条件；任何事实声明都必须引用 factor key 或 source ref。

### Hard Cut Contract

The implementation is a hard cut, not a compatibility migration.

- The current projection version must move past `token-radar-v8-identity-evidence`, whose constant currently identifies the active runtime contract in `src/gmgn_twitter_intel/domains/token_intel/_constants.py:6` to `src/gmgn_twitter_intel/domains/token_intel/_constants.py:17`.
- Current `token_radar_rows` writes are centered on `attention_json / market_json / price_json / score_json / data_health_json`, as shown by `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py:56` to `src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py:69`. The hard cut replaces the runtime contract with factor snapshot output; it must not dual-write old score payloads as a compatibility surface.
- Pulse currently persists `radar_score_json` and `market_context_json` beside thesis output, as shown by `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:454` to `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:478`. The hard cut removes these as agent/gate inputs for current candidates; Pulse must receive factor snapshot and gate result instead.
- Signal Pulse read models currently expose `radar_score_json` and `market_context_json`, as shown by `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py:110` to `src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py:147`. After the cut, UI and notification read models must expose factor snapshot facts and agent recommendation; they must not reconstruct missing facts from old thesis or score fields.
- Missing factor snapshot in the current projection is fail-closed: skip candidate creation, skip high-severity notification, and expose data-health failure rather than falling back to old fields.

## Conceptual Data Flow

```text
GMGN WS events
  -> event normalization / token intent / identity resolution / market observation
  -> token radar raw source rows
  -> per-event atomic mention signals
  -> per-target window factor aggregates
  -> per-token baseline + per-window cross-section normalization
  -> TokenFactorSnapshot
  -> deterministic score/gate/rank
  -> Pulse candidate context
  -> agent recommendation/explanation
  -> notification + API + frontend
```

The important arrow change is between `window factor aggregates` and `deterministic score/gate/rank`: this becomes a stable `TokenFactorSnapshot` contract instead of transient dicts consumed directly by scoring functions.

## Core Models

### FactorPoint

A `FactorPoint` is the smallest explainable factor unit. It represents one semantic measurement such as `social_attention.weighted_mentions_1h`, `market_quality.liquidity_usd`, or `timing.price_change_before_social_pct`.

Required semantics:

- `family` and `key` identify the factor.
- `raw_value` preserves the observed value when available.
- `window` identifies the aggregation horizon when applicable.
- `transformed_value` captures log/scaled/clipped value when used.
- `baseline` captures per-token historical comparison status and value.
- `cross_section` captures cohort percentile/rank when available.
- `score` is the product-facing 0-100 or -1..1 value derived from normalized data.
- `confidence` expresses attribution/data confidence, not model confidence.
- `freshness_ms` and `data_health` state point-in-time usability.
- `source_refs` point to event ids, price observation ids, identity evidence, or feed ids.
- `risk_flags` and `hard_gate` express deterministic restrictions.

### AtomicMentionSignal

An `AtomicMentionSignal` is generated once per event-target mention before window aggregation. It includes:

- target identity binding and resolver confidence.
- author quality from GMGN platform followers, tags, watched status, and profile first-seen age.
- text quality from informativeness, market context, duplicate fingerprint, and directness.
- semantic hints from existing social enrichment: direction, impact, novelty, confidence.
- source quality flags such as low information, public-only, duplicate, watched source, thin attribution.

### AtomicMarketSignal

An `AtomicMarketSignal` captures the point-in-time market state used by a target/window:

- target type and trade venue family: DEX Asset or CEX token.
- market freshness and provider.
- DEX proxy fields: market cap, liquidity, holders, pool/feed readiness, price, volume when available.
- CEX proxy fields: volume, open interest, native market id, feed freshness.
- price sequence fields: social-start price, price before social, current/reference price, first snapshot price.
- explicit `unknown` status for security fields not available in current data.

### TokenFactorSnapshot

A `TokenFactorSnapshot` is the single fact object emitted for a target/window/scope. It contains:

- subject identity: target type, target id, symbol, chain/address or CEX identifier, identity confidence and conflict flags.
- factor families: identity, social_attention, social_quality, social_semantics, market_quality, timing.
- hard gates: product eligibility restrictions, with explicit reason codes.
- composite scores: family scores and final product rank score.
- provenance: source event ids, selected post ids, price observation refs, projection version, factor version, computed_at.

### AgentRecommendation

Agent output is downstream of `TokenFactorSnapshot`. It is not a source of factor truth. Its semantic fields are:

- recommendation: ignore, watch, research, alert, trade_candidate.
- summary and explanation in Chinese.
- primary reasons, each linked to factor keys.
- upgrade conditions and invalidation conditions, each linked to measurable factor thresholds.
- residual risks, each linked to existing risk flags or explicit missing data.

## Factor Families

### Identity

Identity factors answer whether the system knows what object is being discussed.

Required factors:

- resolver status and mention confidence.
- target type: Asset, CexToken, or unresolved source seed.
- identity confidence from current identity evidence when target is Asset.
- symbol collision / conflict count when available.
- direct CA or exact CEX feed binding.

High-priority alerts require resolved target identity. `source_seed` without resolved target may remain visible in low-priority research surfaces, but must not become high/critical notification material.

### Social Attention

Social attention captures whether discussion volume is abnormal.

Required factors:

- mention count for 1h/4h/24h.
- weighted mention count: sum of mention confidence times author quality.
- unique author count.
- watched mention count and watched share.
- baseline surprise: robust z / EWMA z / sparse-history new burst status.
- stream share/noise ratio.

Attention is not sufficient for alerting. It can nominate a candidate for deeper evaluation, but market quality and social quality gates still decide severity.

### Social Quality

Social quality captures whether discussion is broad, independent, and informative.

Required factors:

- independent authors and effective authors.
- top author share and author concentration risk.
- duplicate text share.
- informative post ratio and market-context ratio.
- watched source count.
- public-only/thin-author flags.
- low-information text flags.

Single-author copy-pasta, bot-like templates, or mostly empty meme replies must score lower than a small set of independent organic posts even when raw mention count is similar.

### Social Semantics

Social semantics uses existing enrichment outputs but does not add new live LLM calls.

Required factors:

- direction/sentiment distribution from `direction_hint`.
- impact from `impact_hint`.
- novelty from `semantic_novelty_hint`.
- semantic confidence from enrichment confidence.
- disagreement or mixed-signal flag when bullish/bearish hints conflict.

Sentiment must be volume-gated: a very positive single low-confidence mention cannot become a strong bullish factor.

### Market Quality / On-Chain-Lite

Market quality captures whether a token is structurally worth surfacing. Because current data does not include holder distribution or transfer flow, this family is explicitly on-chain-lite.

For DEX Asset, required factors:

- market freshness and provider readiness.
- market cap absolute quality.
- liquidity absolute quality.
- liquidity-to-market-cap sanity band when both fields are present.
- holders proxy quality.
- pool/feed readiness.
- volume when available.
- security-data availability status, explicitly `unknown` when honeypot/tax/owner/LP-lock data is missing.

For CEX token, required factors:

- pricefeed/native market readiness.
- volume 24h quality.
- open interest availability and quality when present.
- market freshness.

DEX high-priority eligibility requires minimum market quality. A candidate with very low holders, very low liquidity, stale market, missing identity, or missing pool/feed readiness must be blocked or downgraded before agent execution can promote it.

### Timing

Timing captures sequence quality.

Required factors:

- social signal start timestamp.
- price change before social start.
- price change since social start.
- price change since first snapshot.
- chase-risk flag when price moved materially before social signal.
- stale/missing point-in-time price flag when comparison is not trustworthy.

Timing should distinguish early discovery from post-pump commentary.

## Hard Gate Semantics

Hard gates are deterministic and must be evaluated before notification severity and before agent recommendation can upgrade a candidate.

Minimum high-alert gates:

- target identity is resolved and point-in-time valid.
- market data is fresh for the target type.
- DEX Asset has sufficient liquidity, holder proxy, and market cap quality for the configured universe.
- social quality is not thin public-only, single-author dominant, or copy-pasta dominant.
- timing does not show severe chase risk.
- security fields that are unavailable are shown as unknown risk; absence of security data cannot be converted into a positive reason.

Initial DEX high-alert floors are part of the product contract and may become configuration in the plan:

- holders below 100 block high/critical severity.
- liquidity below 25,000 USD blocks high/critical severity.
- market cap below 50,000 USD blocks high/critical severity.
- fresh market status is required for high/critical severity.
- fewer than 3 unique authors with no watched source blocks high/critical severity.
- duplicate text share at or above 0.50 blocks high/critical severity.

These floors intentionally do not hide candidates. They only prevent weak or structurally unsafe candidates from being presented as high-priority alerts.

## Interface Contracts

### Token Radar API / WebSocket

After the hard cut, Token Radar API and WebSocket consumers read factor snapshot as the authoritative row explanation. Existing identity, market, price, attention, and score concepts remain only as factor families or derived fields inside that contract. Consumers should be able to render:

- family-level scores and gates.
- raw market facts: holders, liquidity, market cap, freshness, price movement.
- social facts: mentions, authors, watched sources, duplicate/informative ratios.
- source refs for evidence drilldown.
- score provenance and factor version.

There is no runtime response fallback that rehydrates factor data from legacy `score_json`, `attention_json`, `market_json`, or thesis fields. If a current row lacks factor snapshot, it is not a valid current Token Radar row.

### Signal Lab Pulse

Pulse candidates are created from factor snapshots. Pulse agent input includes factor snapshot and gate result. Agent output cannot change deterministic gates; it can only explain the recommendation and list measurable upgrade/invalidation conditions.

`source_seed` candidates without resolved target identity must be separated from token-target candidates and must not use the same high-priority notification path.

### Notifications

Signal Pulse notification body is fact-first:

1. target and identity confidence.
2. market/on-chain-lite facts.
3. social facts.
4. deterministic gate/status.
5. agent explanation.

Severity is derived from gate + factor scores, not from thesis verdict alone.

### CLI / Generated Docs

CLI/help snapshots should describe factor snapshot as the source of Token Radar explanations once implementation lands. Generated docs should not claim agent thesis is the source of truth.

## Acceptance Criteria

- **AC1**. WHEN a DEX Asset has holders below 100, liquidity below 25,000 USD, or market cap below 50,000 USD while social attention is nonzero, THEN the system SHALL mark high-alert eligibility as blocked or downgraded with explicit `market_quality` gate reasons.
- **AC2**. WHEN a CEX token has no holders or liquidity fields, THEN the system SHALL not apply DEX holder/liquidity gates and SHALL evaluate CEX market quality from feed freshness, volume, open interest, and native market readiness.
- **AC3**. WHEN a Signal Pulse candidate is created for a resolved token target, THEN its agent input SHALL include a factor snapshot with identity, social, market, and timing families.
- **AC4**. WHEN a Signal Pulse source seed has no resolved target identity, THEN it SHALL not produce a high/critical token notification.
- **AC5**. WHEN a notification is rendered, THEN the first screen SHALL include market cap, liquidity, holders or CEX volume, market freshness, mention count, unique authors, watched source count, and deterministic gate status when those fields are available.
- **AC6**. WHEN agent output states a risk, confirmation, upgrade condition, or invalidation condition, THEN it SHALL link to factor keys or source refs present in the input snapshot.
- **AC7**. WHEN a factor cannot be computed because data is missing, THEN the snapshot SHALL expose `missing` or `unknown` data health rather than silently treating the value as safe.
- **AC8**. WHEN score/rank is returned, THEN it SHALL be traceable to factor family scores and factor points, not only to a final opportunity score.
- **AC9**. WHEN current runtime code reads Token Radar or Pulse candidates, THEN it SHALL require factor snapshot and SHALL NOT fallback to legacy score/thesis fields to synthesize the new contract.

## Expected Optimization Effects

This design changes product behavior in several concrete ways.

| Current failure mode | Current code path | Expected effect after factor snapshot hard cut |
|---|---|---|
| Low-holder / low-liquidity DEX assets become high `token_watch` because market fields are merely present. | `tradeability_score()` gives positive contribution for `market_cap_present` and `liquidity_present` rather than quality floors. | DEX assets below high-alert floors are blocked or downgraded before Pulse agent and notification severity. A token with holders 46, liquidity 6,553 USD, and market cap 12,087 USD cannot become high severity. |
| Thin social text produces fluent but generic confirmation/risk prose. | Pulse agent receives radar score and timeline context, then writes thesis fields such as `confirmation_triggers_zh` and `top_risks`. | Agent reasons must cite factor keys. Low-information, duplicate, public-only, or single-author social factors become explicit downgrade reasons instead of prose being used to hide weak evidence. |
| Source-seed events without resolved target identity enter the same product surface as token candidates. | Pulse scans both token radar rows and harness social events; source context can produce displayable candidates. | Unresolved source seeds cannot use high/critical token notification path. They may remain research items only when the product explicitly supports that surface. |
| Notification first screen hides the most important facts. | `_pulse_body()` renders status, score band, thesis why-now, risks, and confirmation before raw market/social facts. | Notification first screen shows identity, market cap/liquidity/holders or CEX volume, market freshness, mention count, unique authors, watched source count, and hard gate status. |
| UI/API users see stale or mismatched current candidate state versus notification body. | Pulse persists mutable thesis, radar score, and market context separately from notification rendering. | Factor snapshot becomes the point-in-time fact contract for both candidate and notification. Current detail views can show the same snapshot facts that authorized the notification. |

Expected measurable impact:

- **High-severity precision should improve immediately** because structurally weak DEX assets are blocked by deterministic floors before agent prose. On the recent noisy sample that motivated this spec, the BOV-style case is deterministically removed from high severity by all three market floors.
- **High-severity volume should drop**. Estimated reduction for noisy windows is 30-60 percent, depending on how many candidates fail social-quality and market-quality gates. This is an estimate; implementation verification must measure before/after counts on the same DB window.
- **Agent output usefulness should increase** because every explanation must point to factor keys and measurable upgrade conditions. The expected qualitative change is fewer interchangeable `confirmation` / `risk` paragraphs and more statements like "liquidity below high-alert floor" or "unique authors below threshold".
- **Debuggability should improve** because each alert decision can be traced to factor points rather than searching across `score_json`, `market_context_json`, thesis fields, and notification body.
- **Recall for early weak tokens will intentionally decrease in push alerts** but not necessarily disappear from research views. This is a product trade: Pulse high severity should optimize for actionable signal quality, not maximal discovery of every micro-cap mention.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Factor snapshot becomes too large for API/UI payloads | Medium | Keep selected factor points in the public response and allow deeper detail in target detail views; preserve source refs instead of embedding all raw rows. |
| Hard gates block too many early meme opportunities | Medium | Separate high-alert eligibility from research/watch visibility; low liquidity can remain visible but not high severity. |
| CEX and DEX scoring get mixed again | High | Keep target-type-specific market family semantics; CEX never inherits DEX holder/liquidity gates. |
| Existing score consumers break at cutover | High | Migrate all known runtime consumers in the same implementation plan and fail closed when factor snapshot is absent; do not add fallback adapters. |
| Agent continues to write unsupported prose | High | Agent output contract requires factor-key-backed reasons and guardrail rejection/repair when claims lack backing. |
| Missing security data creates false confidence | High | Represent security fields as unknown risk, not as a passing score. |

## Evolution Path

After this spec lands and v1 factor snapshots are stable, the next expansions are:

- holder distribution factors from holder snapshot data: meaningful holders, top holder concentration, churn, retention, cohort growth.
- transfer/flow factors from labeled addresses: CEX inflow/outflow, bridge flow, whale pressure, smart-money proxy.
- factor evaluation using realized forward returns: IC/ICIR, decay curves, bucket returns, score-version isolation.
- learned or IC-weighted family composition only after enough historical factor snapshots and outcomes exist.

The v1 design must not foreclose those expansions: factor keys, versions, data health, and source refs should be stable enough that later holder/flow families can join the same snapshot contract without changing agent/notification semantics.

## Alternatives Considered

- **Keep current `score_json` and improve prompts** — rejected because prompts cannot repair missing factor provenance. This leaves agent responsible for converting weak context into useful analysis, which is exactly the current failure mode.
- **Build a full quant factor research platform now** — rejected because current data does not yet support holder distribution, transfer flow, address labels, or large-sample IC weighting. The KISS path is to professionalize the available social and market/on-chain-lite factors first.
- **Create separate pipelines for Pulse and Token Radar** — rejected because it would duplicate identity, social, market, and timing logic. Token Radar should own factor snapshots; Pulse should consume them.
- **Use agent tools to query missing facts at runtime** — rejected for v1 because deterministic factor generation should be replayable, testable, and point-in-time. Agent tools can be reconsidered only for read-only explanation support after factor snapshots are authoritative.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Factor snapshot is the source of truth for Token Radar explanation, Pulse gate, notification facts, and agent recommendation context. |
| Always | Social factors use existing resolved mentions, account profiles, watched flags, text quality, and social enrichment hints before any model explanation. |
| Always | DEX market quality treats low holders, low liquidity, stale market, and missing pool/feed readiness as deterministic restrictions. |
| Always | Current runtime readers fail closed when factor snapshot is missing; they do not synthesize it from old score, market, or thesis fields. |
| Always | The implementation plan may remove or stop emitting old score-centered runtime fields as part of the hard cut. |
| Ask first | Introducing new persisted factor tables rather than deriving/writing factor snapshot through the existing projection lifecycle. |
| Ask first | Adding new LLM calls, Twitter API ingestion, holder snapshot ingestion, transfer-flow indexing, or learned factor weights. |
| Never | Agent prose may not override hard gates or invent facts missing from the factor snapshot. |
| Never | Missing chain/security data may not be interpreted as safe. |
| Never | Runtime compatibility adapters such as `factor_snapshot or score_json` fallback exist in current production paths. |
