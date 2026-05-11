# Token Factor Engineering Hard Cut Spec

**Status**: Draft  
**Date**: 2026-05-11  
**Owner**: Codex with Qinghuan  
**Related**:

- `docs/superpowers/specs/active/2026-05-09-standardized-social-factor-pipeline.md`
- `docs/superpowers/specs/active/2026-05-10-token-radar-factor-snapshot-architecture-cn.md`
- `docs/superpowers/specs/active/2026-05-11-token-radar-market-boundary-hard-cut-cn.md`
- `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`

## Background

Token Radar already has the right high-level ownership boundary: ingestion and
token identity feed `domains/token_intel`, projection writes
`token_radar_rows.factor_snapshot_json`, and Signal Pulse consumes the snapshot
rather than old score/thesis JSON. The module architecture says the production
chain ends in `TokenRadarProjectionWorker`, `token_radar_rows.factor_snapshot_json`,
read models, Pulse, notifications, HTTP, WebSocket, CLI, and frontend
(`src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md:7-17`,
`src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md:39-43`).

The source query already joins the data this fix needs. It brings token intents,
current deterministic resolutions, events, account profile features from GMGN
directory, LLM social hints, asset identity, CEX feed metadata, first price,
event price, event-history price, and before-event price into one ordered stream
(`src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py:16-85`,
`src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py:87-204`).
This is enough to build a first solid factor layer without new providers,
new LLM calls, or a new research platform.

The current feature builder already computes useful primitives: rolling mention
counts, unique authors, watched mentions, weighted mentions from GMGN platform
followers and tags, duplicate text share, informative post count, LLM utility,
propagation, market-derived tradeability, and timing fields
(`src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py:29-85`,
`src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py:88-130`).
There is also a pure atomic mention helper that weights authors by GMGN platform
followers, tag tier, and first-seen age
(`src/gmgn_twitter_intel/domains/token_intel/services/atomic_mention.py:32-43`).

The current snapshot builder is structurally clean but semantically too blunt.
Identity factors are presence checks that score 100 when `target_id`,
`target_type`, or `symbol` exists
(`src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py:68-84`).
Timing includes a `social_signal_start_ms` presence score that is always 100
when a row exists
(`src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py:206-219`).
DEX market quality uses fixed floor multiples for holders, liquidity, and
market cap, so healthy DEX candidates saturate at 100 quickly
(`src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py:165-203`,
`src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py:370-385`).
The composite rank is a simple average of six family scores, then hard-gate
blocked snapshots are capped to 20
(`src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py:272-291`).

Projection applies a cross-sectional rank, but only after the composite has
already been computed, and the rank is attached as metadata rather than used as
the score contract
(`src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py:231-286`).
The normalizer itself ranks raw scores within an active cohort
(`src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py:8-33`).

Pulse correctly gates before agent execution and persists the same factor
snapshot, gate, and recommendation (`src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py:391-464`).
The Pulse gate reads `composite.rank_score`, hard-gate reasons, and factor risk
flags (`src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py:46-77`).
Therefore, fixing snapshot semantics fixes Pulse without adding agent authority.

The database already has an evaluation table for score-version bucket outcomes
(`src/gmgn_twitter_intel/platform/db/alembic/versions/20260506_0001_initial_postgresql.py:680-703`).
Older token signal snapshot/outcome tables were intentionally dropped during
the v3 intent migration
(`src/gmgn_twitter_intel/platform/db/alembic/versions/20260507_0007_token_radar_v3_intents.py:255-270`).
The current product snapshot store is `token_radar_rows`; reads already select
latest rows by max `computed_at_ms`
(`src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py:91-134`).
For evaluation, the current factor version needs enough retained point-in-time
rows to settle forward returns. This spec keeps `token_radar_rows` as the single
product snapshot store rather than recreating the dropped token signal snapshot
tables.

On 2026-05-11 around 10:15 Asia/Shanghai, a local production DB audit showed
the user-visible symptom:

- Recent `token-radar-v10-current-market` rows were not all 100 overall, but
  many child factors were saturated. In 245 rows computed in the prior hour,
  `timing.social_signal_start_ms` was 100 in 100% of rows,
  `identity.symbol` in 97.6%, `social_quality.duplicate_text_share` in 93.1%,
  and CEX `market_quality.native_market_id` in 100%.
- Current `1h/all` Pulse token-target candidates were more saturated. Among
  50 valid family snapshots, identity was 100 in 100%, market quality was 100
  in 62%, DEX holders and market cap were 100 in every valid DEX sample, and
  `cross_section_rank` was nearly always above 0.95 because only already-high
  candidates reached Pulse.
- `token_score_evaluations` had zero rows, so score versions were not yet tied
  to persistent bucket outcomes or IC diagnostics.

## Problem

Signal Lab token factors currently mix three different concepts: eligibility,
data health, and alpha. Presence of identity, freshness of market data, and
passing DEX floor checks are necessary to trust a candidate, but they are not
predictive alpha by themselves. Averaging those checks into the rank score makes
healthy tokens look high-conviction even when social evidence is thin, semantic
coverage is sparse, or forward returns are unproven. The result is a snapshot
that is auditable but not discriminative enough, and a Pulse agent that can
write persuasive explanations from saturated inputs.

## First Principles

1. **Eligibility is not alpha.** Identity, market freshness, minimum liquidity,
   holder floor, duplicate-text risk, and minimum independent social sources
   decide whether a token may be promoted. They must not increase the alpha
   rank score merely because they pass.
2. **A factor score measures relative predictive signal.** A 0-100 score means
   relative attractiveness inside a defined cohort and horizon, not "fact is
   present" or "data is not stale". Missing data lowers confidence or blocks a
   gate; it is not silently converted into an alpha zero unless zero is the
   measured value.
3. **Use existing facts before adding machinery.** Events, account profiles,
   LLM enrichment, deterministic resolutions, price observations, current
   market, and token radar rows are enough for this hard cut. No new provider,
   no new LLM path, no online learning, no PCA, no GBDT.
4. **Evaluation is part of the scoring contract.** A new factor version is not
   complete until its snapshots can settle against forward returns and produce
   score-version bucket diagnostics. IC on small samples is reported as
   diagnostic only; it cannot authorize weight changes until sample size is
   sufficient.
5. **Hard cut, no compatibility semantics.** Current runtime reads only the new
   factor version. Old `token_factor_snapshot_v1` rows and old score-centered
   semantics are historical data, not fallback inputs.

## Goals

- **G1 Separate gate and alpha.** No identity presence factor, market freshness
  pass, DEX holder/liquidity/market-cap floor pass, duplicate-text non-risk, or
  `social_signal_start_ms` presence check contributes positive alpha points.
  These remain visible as gate or data-health facts.
- **G2 Reduce saturation.** In a representative one-hour production window,
  no alpha factor used by the composite has more than 50% of non-missing
  observations at exactly 100, except a binary risk indicator that is explicitly
  excluded from the composite.
- **G3 Use existing normalization in the score, not as decoration.** The final
  rank score is derived from within-cohort normalized factor values, and the
  active cohort definition is visible in every snapshot.
- **G4 Make score versions evaluable.** The current factor version produces
  persistent bucket evaluation rows for configured horizons, including
  settlement coverage and forward-return direction metrics. IC and ICIR are
  available as diagnostics when enough settled observations exist.
- **G5 Keep Pulse subordinate to deterministic facts.** Pulse may explain the
  snapshot and choose a lower recommendation than the gate allows. It may not
  promote a candidate above the deterministic gate or use agent text as a
  factor input.
- **G6 Preserve KISS.** This hard cut reuses the current source query, feature
  builder, current-market read model, projection worker, `token_radar_rows`,
  Pulse gate, and `token_score_evaluations`. Any implementation plan that adds
  a new background worker, external data source, model training loop, or new
  agent tool is out of scope for this spec.

## Non-goals

- No full quant research platform.
- No new LLM calls or agent tools.
- No Twitter engagement ingestion, likes, replies, views, quote counts, or
  retweet graph.
- No holder concentration, LP-lock, tax, honeypot, transfer-flow, smart-money,
  or wallet-label factor family.
- No online weight tuning, reinforcement learning, Bayesian posterior, or
  probabilistic rank output.
- No live trading recommendation or execution instruction.
- No runtime compatibility with `token_factor_snapshot_v1`, legacy
  `score_json`, old Pulse thesis fields, or score-centered JSON fallbacks.

## Target Architecture

The target architecture keeps the existing pipeline but changes the meaning of
the snapshot contract.

```text
GMGN frame
  -> ingest + token intent + deterministic resolution
  -> account profile + LLM enrichment + price observations
  -> TokenRadarSourceQuery
  -> per-mention atomic facts
  -> window aggregates
  -> gate facts + alpha factors
  -> within-cohort normalization
  -> TokenFactorSnapshot current version
  -> deterministic gate / rank / Pulse agent explanation
  -> retained token_radar_rows snapshots for settlement
  -> token_score_evaluations after settlement
```

### Ownership

| Component | Owner | Responsibility |
|-----------|-------|----------------|
| Identity facts | `asset_market` and token resolver | Decide what token was mentioned and whether it is resolved. |
| Market facts | `asset_market` | Provide current market status and point-in-time price observations. |
| Atomic social facts | `token_intel` | Convert each mention into quality, confidence, author weight, semantic labels, and text fingerprints. |
| Window aggregation | `token_intel` | Aggregate atomic facts over 5m, 1h, 4h, and 24h windows. |
| Gate facts | `token_intel` | Decide max product surface and blocking reasons. |
| Alpha factors | `token_intel` | Score only predictive, normalized, non-presence signals. |
| Pulse recommendation | `pulse_lab` | Explain the deterministic snapshot and gate. |
| Evaluation | `token_intel` | Settle factor versions against future price observations and write bucket diagnostics. |

### Snapshot Semantics

The current version of `TokenFactorSnapshot` has three top-level meanings:

- **`subject`**: identity and display facts. These are facts, not alpha.
- **`gates` / `data_health`**: whether the token may be displayed, watched, or
  promoted. These are blockers or confidence constraints, not positive alpha.
- **`alpha` / `composite`**: normalized factor signals that can be compared
  across tokens in the same cohort and window.

The composite uses only alpha families. Gate facts can cap or block product
surfaces, but they do not add points.

The conceptual formula is:

```text
eligible_surface = gate(subject, market_health, social_health, risk_flags)
alpha_score = weighted_mean(normalized_alpha_factors, by_family)
rank_score = percentile(alpha_score, active_cohort)
decision = surface_gate(eligible_surface, rank_score, confidence)
```

## Factor Families

### Gate and Data-Health Families

These families are visible in the snapshot but excluded from alpha scoring.

- **Identity gate**: resolved target type/id, deterministic resolution status,
  asset identity confidence, conflict count, chain/address or CEX token id.
- **Market health gate**: freshness status, provider status, observation age,
  price basis compatibility, current-market field readiness.
- **DEX floor gate**: minimum liquidity, market cap, holders, and pool/feed
  readiness. Passing the floor means "tradable enough to consider", not
  "higher expected return".
- **Social health gate**: minimum independent sources, duplicate text cluster,
  author concentration, watched confirmation where applicable.
- **Timing risk gate**: extreme pre-social move and missing social-start price
  limit promotion severity.

### Alpha Families

These are the only families eligible for the composite rank score.

| Family | Existing data used | Signal intent |
|--------|--------------------|---------------|
| Attention surprise | mention counts, weighted mentions, prior slots | Is this token getting unusual attention relative to its own recent baseline? |
| Independent attention | unique authors, effective authors, author concentration | Is attention distributed across independent sources rather than one repeated voice? |
| Trader-weighted attention | GMGN platform followers, GMGN user tags, watched mentions | Are trader-relevant accounts participating? |
| Discussion quality | informative post count, post text features, duplicate text share | Is the discussion specific enough to be useful? |
| Semantic catalyst | LLM direction, impact, novelty, confidence | Is there a credible catalyst or narrative, with enough coverage to trust it? |
| Timing response | price before social, price since social, adverse chase risk | Did price action leave room, or is the signal late and crowded? |

### Shrinkage Rules

KISS shrinkage is deterministic and explainable:

- A semantic score from one LLM-labeled post cannot reach 100 by itself.
- A no-duplicate condition does not award 100 alpha points; it only avoids a
  duplicate-risk gate.
- A high market cap, high holder count, or high liquidity value can pass gates
  and inform sizing/risk text, but it cannot raise alpha rank by itself.
- Missing LLM coverage lowers semantic confidence. It does not punish unrelated
  non-semantic factors.
- Stablecoins and obvious broad-market CEX tickers remain excluded or separated
  by cohort rules so size factors do not masquerade as alpha.

## Conceptual Data Flow

The existing collector, ingest, identity, market, and Pulse ownership remains.
The changed arrows are inside token-intel scoring:

```text
TokenRadarSourceQuery
  -> atomic mention facts
  -> window factor aggregates
  -> gate/data-health facts
  -> normalized alpha factors
  -> current token_radar_rows.factor_snapshot_json
  -> latest read models / Pulse / notifications
  -> settlement from price_observations
  -> token_score_evaluations
```

No new provider arrow appears. No agent-to-database or agent-to-market-data
arrow appears. Evaluation reads persisted snapshots and price observations; it
does not call external APIs.

## Core Models

### AtomicMentionFact

One mention-level record derived from existing source rows.

Fields:

- event id, target id, received time, author handle.
- mention confidence from deterministic resolution.
- author weight from GMGN platform followers, GMGN tags, watched status, and
  first-seen age.
- text fingerprint and informative-post features.
- optional semantic direction, impact, novelty, and confidence.
- optional point-in-time event price and before-event price.

Invariant: atomic mention facts are pure derived facts. They do not read
providers, call agents, or persist by themselves.

### WindowFactorAggregate

One target/window/scope aggregate built from atomic mention facts.

Fields:

- raw counts: mentions, weighted mentions, unique authors, effective authors,
  watched mentions.
- quality facts: duplicate share, top-author share, informative count.
- semantic facts: labeled count, coverage, weighted direction, impact, novelty,
  confidence.
- timing facts: social start price, current/reference price, pre-social move,
  post-social move.
- baseline facts: own-token prior slot counts and baseline readiness.

Invariant: raw aggregates are not final scores until normalized within a cohort.

### FactorPoint

One explainable alpha measurement.

Fields:

- family and key.
- raw value and window.
- transformed value where relevant.
- baseline state for time-series surprise.
- cohort percentile for cross-section comparability.
- score, confidence, data health, source references, and risk flags.

Invariant: if a factor can be exactly 100 for most candidates because a condition
is merely present or healthy, it is not an alpha factor.

### GateResult

A deterministic decision envelope.

Fields:

- allowed surfaces.
- max recommendation level.
- blocked reasons.
- downgrade reasons.
- missing-data reasons.
- measurable upgrade conditions.

Invariant: gate result can reduce product severity but cannot add alpha points.

### TokenFactorSnapshot

The product contract for one target/window/scope/projection version.

Fields:

- subject facts.
- gate result and data health.
- alpha families and factor points.
- composite rank score.
- normalization cohort metadata.
- provenance: source events, price observations, factor version, projection
  version, computation time.

Invariant: current runtime treats one factor version as authoritative. Legacy
snapshot versions are filtered out, not adapted.

### RetainedRadarSnapshot

A point-in-time `token_radar_rows` record kept long enough for configured
forward-return horizons to settle.

Fields:

- target identity, window, scope, rank, decision time, and source event ids.
- current factor snapshot version and composite score.
- entry market facts from the same decision time.
- enough provenance to locate future price observations for settlement.

Invariant: latest read models still select the most recent projection run, but
settlement can read older rows from the same table. There is one product
snapshot store, not a parallel compatibility store.

### FactorEvaluation

The settled score-version diagnostic.

Fields:

- factor version, horizon, window, scope, cohort.
- bucket counts and settlement coverage.
- average actual and abnormal returns.
- directional hit rate and confidence interval.
- Spearman IC and ICIR when settled sample size is large enough.
- evidence-quality flag for small samples.

Invariant: IC values below sample-size threshold are displayed as diagnostics,
not as authorization to change weights.

## Interface Contracts

### Token Radar API and WebSocket Rows

Rows expose the current `factor_snapshot` version only. If a row has no current
snapshot version, it is not eligible for current ranking surfaces. The row still
exposes current-market facts through the existing current-market contract.

The displayed score is the composite rank score from alpha factors. Gate facts
and data-health facts are displayed separately from alpha contribution.

### Signal Pulse

Pulse receives the current snapshot and gate. Agent recommendation may cite only
factor keys that exist in the snapshot. Agent text may not introduce new market,
identity, social, or price facts. If the gate blocks high alert, Pulse cannot
show a trade-candidate recommendation even if the agent text is optimistic.

### Notifications

Notifications use gate severity and current alpha rank. Notification body leads
with factor facts and gate status before agent prose. Stale market, unresolved
identity, insufficient independent sources, and duplicate clusters fail closed.

### CLI / Ops Diagnostics

The operational surface can report factor health for the current version:

- factor distribution: count, missing rate, exact-zero share, exact-100 share,
  unique values, and standard deviation.
- score-version evaluation by horizon and bucket.
- IC/ICIR only when sample size is sufficient.

This is diagnostic output, not a new public trading API.

## Acceptance Criteria

- **AC1.** WHEN a token is fully resolved with fresh market data THEN identity
  and freshness SHALL pass gates but SHALL NOT add positive alpha points.
- **AC2.** WHEN a DEX token has holders, liquidity, and market cap far above
  minimum floors THEN those facts SHALL pass tradability gates but SHALL NOT
  make the composite rank higher unless alpha factors are also strong.
- **AC3.** WHEN duplicate text share is zero THEN the snapshot SHALL show no
  duplicate-risk blocker, but SHALL NOT award a 100-point alpha factor for
  "not duplicate".
- **AC4.** WHEN semantic coverage is one labeled post out of many mentions THEN
  semantic catalyst score SHALL be confidence-shrunk and SHALL NOT reach 100
  from the single bullish label alone.
- **AC5.** WHEN a single author posts repeated or near-identical text THEN the
  social health gate SHALL score worse than a smaller set of independent
  organic mentions.
- **AC6.** WHEN projection writes the current factor version THEN latest Token
  Radar reads SHALL ignore older factor versions and SHALL NOT fall back to
  legacy score JSON.
- **AC7.** WHEN factor diagnostics run on a one-hour production-like window
  THEN every composite alpha factor SHALL report distribution health and no
  included alpha factor SHALL have more than 50% exact-100 values.
- **AC8.** WHEN forward horizons settle THEN `token_score_evaluations` SHALL
  contain rows for the current score version, horizon, window, scope, and score
  bucket with non-zero settlement coverage.
- **AC9.** WHEN settled sample size is below the configured evidence threshold
  THEN IC SHALL be labeled diagnostic/low-evidence and SHALL NOT be used to
  change factor weights.
- **AC10.** WHEN Pulse renders a candidate THEN the visible explanation SHALL
  separate gate facts, alpha factors, and agent recommendation.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Removing presence scores lowers many visible ranks at once. | High | Hard cut by factor version; old versions are ignored for current runtime, and diagnostics prove distribution before promotion. |
| Existing high-quality market candidates look less exciting because market floors no longer add alpha. | Medium | Market facts remain visible as tradability and sizing context; alpha score reflects social/timing signal only. |
| Evaluation remains sparse for long horizons. | Medium | Report evidence quality and settlement coverage; do not infer IC from small samples. |
| Cross-section cohort too broad mixes BTC, CEX majors, and tiny DEX memes. | High | Use explicit cohort metadata and exclude stablecoins; separate target-market type and size buckets where existing data supports it. |
| Agent explanations continue to overstate thin social evidence. | Medium | Agent may cite only snapshot factor keys, and recommendation cannot exceed deterministic gate. |
| Appending projection history grows storage. | Medium | Keep latest read path unchanged; retention is an ops policy, not a scoring concept. |

## Evolution Path

After this hard cut, the next expansion should be deliberately boring:

1. Accumulate enough settled observations for the current factor version.
2. Review distribution health and bucket monotonicity weekly.
3. Promote only factors with stable sign and sufficient coverage.
4. Add one new existing-data factor at a time, behind a factor-version bump.

The design should not foreclose future holder-distribution, flow, smart-money,
or Twitter engagement factors. Those families must arrive as new data contracts,
not as hidden weights inside the current social factor layer.

## Alternatives Considered

- **Keep current snapshot and only tune thresholds.** Rejected because the
  core error is semantic: presence and eligibility are being averaged into
  alpha. Lowering or raising thresholds does not fix saturation.
- **Add a quant research platform now.** Rejected because current source data
  and evaluation plumbing are not yet solid. KISS requires fixing the existing
  snapshot, normalization, and bucket evaluation first.
- **Ask the Pulse agent to be more skeptical.** Rejected because agent prose is
  downstream of deterministic facts. The input contract must be corrected before
  prompt tone matters.
- **Use old `score_json` or `token_factor_snapshot_v1` as fallback.** Rejected
  because compatibility preserves the broken semantics and makes evaluation mix
  populations.
- **Create a parallel token signal snapshot system.** Rejected for now because
  `token_radar_rows` is already the product snapshot store and latest reads
  already key off `computed_at_ms`. Reusing it keeps one source of truth.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Keep deterministic gate before agent; expose factor breakdown; bump factor/score version on scoring semantics change; filter runtime to current version. |
| Ask first | Add new data providers, add new persistent tables, change public API field names, or introduce model-trained weights. |
| Never | Use legacy score/thesis JSON as runtime fallback; let agent override gates; count healthy identity or market presence as alpha; infer IC from small samples as if it were conclusive. |
