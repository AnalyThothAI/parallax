# Token Radar Trader Signal Redesign Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign Token Radar from a generic social table into a trader-grade token opportunity board. The board should answer: what token is moving, what its market-cap/risk context is, whether attention is accelerating, who is driving it, how fresh the evidence is, and what action the trader should take.

**Core principle:** Do not show metrics whose meaning is weak without the data needed to interpret them. Liquidity pool size alone is out of scope because it is only meaningful with on-chain context such as wallet growth, net buy flow, holder distribution, smart-wallet activity, LP changes, and buy/sell imbalance.

**Current issue:** The existing table has columns like `dir`, `EV`, `narrative`, `accts`, and action-like tags, but their definitions are mismatched:

- `dir` falls back to `fresh/stale/missing`, which is market-data freshness, not price direction.
- `EV` is actually `confidence.score`, not expected value.
- `narrative` is `anomaly.reasons[0]`, not an actual narrative thesis.
- `accts` is raw unique author count, not source quality.
- `market_cap` is already returned by the backend but absent from the primary table.
- `Evidence` is not explicitly ranked by evidentiary strength.

## Architecture Audit Verdict

The plan is directionally correct, but two implementation details must be constrained by the current architecture:

1. `weighted_reach` is not a mature reach model. The current repository only has `author_followers` snapshots from GMGN events, so first implementation treats it as a weak secondary signal, not a primary ranking variable.
2. Price `Δ` must be computed from `token_market_snapshots` at the token-flow row's window boundaries. Using the latest token snapshot is a bug because it can leak future market data into an older social window.
3. Frontend decision fallback is a bug. `driver/watch/discard` must come from backend `signal.decision`; the frontend may only store explicit user overrides.
4. Current `token_windows` are fixed materialized buckets, not true rolling windows. This plan keeps that architecture for the first refactor and makes freshness explicit. A later rolling-window materializer can replace the bucket model if current-bucket sparsity becomes the dominant product issue.

---

## Design Thesis

### Trader Questions

Token Radar should optimize for the first 10 seconds of a trader's scan:

1. **Can I identify the exact tradable asset?**
   - Symbol alone is not enough. A symbol can map to multiple CAs.
   - Required: symbol, chain, CA, identity status.

2. **Is it in the market-cap zone I care about?**
   - Market cap is the first risk/return anchor for meme tokens.
   - Required: current market cap, missing/stale status.

3. **Is attention accelerating now?**
   - Raw mentions are not enough.
   - Required: current mention count, previous-window delta, baseline z-score when available, social dominance within our stream.

4. **Who is driving the attention?**
   - Multiple authors is common and not sufficient.
   - Required: watched author count, unique author count, top-author concentration, weighted reach, source quality tier.

5. **Is the evidence fresh and specific?**
   - A fresh CA mention is stronger than a stale symbol-only mention.
   - Required: first-seen age, latest-evidence age, market snapshot age, evidence specificity.

6. **What is the decision and why?**
   - The board should say `driver`, `watch`, or `discard` with explainable reasons.
   - Required: rule-based signal labels and risk reasons.

### Industry References

- Santiment's `Social Dominance` defines social attention as share of discussion, not absolute volume. This supports replacing raw mention count as the primary metric with normalized stream share and changes over time. Source: https://academy.santiment.net/metrics/social-dominance/
- The Tie emphasizes aggressive cleaning and source filtration before measuring conversation volume or sentiment. It also uses dispersion/unique-user concentration to detect manipulation. Source: https://www.thetie.io/insights/research/social-media-sentiment-data-deep-dive/
- LunarCrush combines market and social indicators in rankings like AltRank and Galaxy Score, and separately tracks contributors, interactions, mentions, social dominance, sentiment, and market data. Source: https://lunarcrush.ai/html/
- Nansen's Token God Mode frames token analysis around Smart Money movements, holder distribution, exchange flows, largest buyers/sellers, top transfers, and PnL. This supports treating pool/liquidity alone as insufficient until richer on-chain data exists. Source: https://academy.nansen.ai/articles/3874203-token-god-mode-101

---

## Target Token Radar Columns

### Column 1: `Token`

**Purpose:** Identify the exact tradable object.

Display:

- `$SYMBOL`
- chain badge
- short CA
- identity status only when not `resolved_ca`

Rules:

- If `identity_status != resolved_ca`, visually downgrade.
- If symbol maps to multiple CAs, show each CA as a separate row.
- Do not merge rows by symbol.

Backend fields:

- `identity.symbol`
- `identity.chain`
- `identity.address`
- `identity.identity_status`
- `identity.token_id`

### Column 2: `MCap`

**Purpose:** Risk/return anchor.

Display:

- Compact market cap, e.g. `$15K`, `$6.3M`
- Status marker when missing/stale

Rules:

- `fresh` market cap: normal text.
- `stale` market cap: muted with age.
- `missing`: show `-` and add risk reason.

Backend fields:

- `market.market_cap`
- `market.market_status`
- `market.snapshot_age_ms`

Required backend change:

- Add canonical `market.market_cap_usd` alias or keep `market.market_cap` but document USD assumption.
- Keep `market_status` but do not use it as price direction.

### Column 3: `Δ`

**Purpose:** Price movement over the selected radar window.

Display:

- `+12%`, `-8%`, or `-`
- Green for positive, red for negative, muted when unavailable

Rules:

- Compute from our own `token_market_snapshots` history, not from GMGN `previous_price`.
- Use latest snapshot at or before window end and nearest snapshot at or before window start.
- If there is no comparable prior snapshot, return `null`.

Backend fields to add:

```text
market.price_change_window_pct
market.price_at_window_start
market.price_at_window_end
market.price_change_status = ready | insufficient_history | missing_market
```

### Column 4: `Flow`

**Purpose:** Attention velocity and acceleration.

Display:

- Primary: total mentions in window
- Secondary: previous-window delta, e.g. `21 +13`
- Optional compact z-score, e.g. `z2.1`

Rules:

- Raw mention count is only one component.
- Prefer `mention_delta` and `z_score` when available.
- If baseline is insufficient, show delta and mark baseline as `new`.

Backend fields to add:

```text
flow.mentions
flow.watched_mentions
flow.previous_mentions
flow.mention_delta
flow.mention_delta_pct
flow.z_score
flow.stream_dominance
flow.baseline_status
```

Mapping from current fields:

- `social.mention_count -> flow.mentions`
- `social.watched_mention_count -> flow.watched_mentions`
- `social.market_mindshare -> flow.stream_dominance`
- `baseline.z_score -> flow.z_score`
- `baseline.acceleration -> flow.mention_delta` only if it represents previous-window delta; otherwise recompute explicitly.

### Column 5: `Sources`

**Purpose:** Quality of the social source set.

Display:

- `W/A` format: watched sources / unique authors, e.g. `1/8`
- concentration tag when top author dominates, e.g. `conc 75%`
- optional top source handle in detail drawer

Rules:

- Raw `unique_author_count` alone is not enough.
- Stronger when multiple independent authors mention a resolved CA.
- Weaker when mentions are concentrated in one author or symbol-only.

Backend fields to add:

```text
sources.unique_authors
sources.watched_authors
sources.weighted_reach
sources.top_author_share
sources.top_authors
sources.source_quality_score
sources.source_quality_reasons
```

Source quality scoring:

```text
base = 0
+25 if watched_authors >= 1
+15 if unique_authors >= 3
+10 if unique_authors >= 8
+5 if reported follower reach is present
-20 if top_author_share >= 0.75 and mentions >= 3
-15 if identity_status is unresolved_symbol or ambiguous_symbol
-10 if repeated text cluster suspected
clamp 0..100
```

Do not treat follower reach as decisive until there is a source-quality model with known author tiers, bot filtering, and historical precision.

### Column 6: `Fresh`

**Purpose:** Timeliness of market and social evidence.

Display:

- `2m` latest evidence age
- market snapshot status icon or age
- first-seen age in drawer, not primary cell unless new

Rules:

- Fresh evidence should mean latest relevant event age, not only window start.
- First seen should be promoted only when token is new to local evidence store.

Backend fields to add:

```text
fresh.latest_evidence_age_ms
fresh.first_seen_age_ms
fresh.market_snapshot_age_ms
fresh.is_new_token
fresh.is_first_seen_by_watched
```

### Column 7: `Signal`

**Purpose:** Explainable action state.

Display:

- `driver`, `watch`, or `discard`
- color tag using the existing single amber accent design constraints plus state colors

Decision rules:

`driver` when:

- identity is `resolved_ca`
- market cap is present and market data is fresh
- source quality is above threshold
- flow is accelerating or z-score is strong
- manipulation risk is not high

`watch` when:

- identity is resolved but flow/source quality is not yet decisive
- or market cap is present but evidence is early
- or watched author exists but social spread is limited

`discard` when:

- symbol-only / ambiguous / unresolved CA
- market data missing
- top-author concentration is high without independent confirmation
- stale market data and no recent evidence

Backend fields to add:

```text
signal.decision
signal.score
signal.reasons
signal.risks
signal.evidence_id
```

The frontend should not independently derive the default decision except for temporary user overrides.

### Detail Drawer: `Evidence`

**Purpose:** Show why the signal exists.

Evidence should not be a primary table column. It should be the right-drawer payload opened by row selection.

Strongest evidence definition:

```text
evidence_score =
  source_quality
  + token_specificity
  + novelty
  + independence
  + recency
  + market_confirmation
  - manipulation_risk
```

Evidence components:

```text
source_quality:
  watched author, historical source tier, follower/reach sanity

token_specificity:
  direct CA > GMGN payload token snapshot > cashtag with unique resolved alias > symbol-only

novelty:
  first local mention, first watched mention, first cross-source burst

independence:
  unique authors, different top authors, non-duplicate text

recency:
  latest event age

market_confirmation:
  fresh market snapshot, market cap present, price change calculable

manipulation_risk:
  top author concentration, repeated text, unresolved symbol, missing market, stale snapshot
```

Backend fields to add:

```text
evidence_best.event_id
evidence_best.score
evidence_best.handle
evidence_best.text
evidence_best.received_at_ms
evidence_best.url
evidence_best.reasons
```

---

## Data Model And API Contract

### Proposed `TokenFlowItem` Shape

Keep current fields during implementation only if directly used by other endpoints, but the UI should move to the new semantic blocks.

```json
{
  "identity": {
    "identity_key": "token:bsc:0x...",
    "identity_status": "resolved_ca",
    "token_id": "token:bsc:0x...",
    "chain": "bsc",
    "address": "0x...",
    "symbol": "TOKEN"
  },
  "market": {
    "market_status": "fresh",
    "market_cap": 15161.968,
    "price": 0.00001516,
    "price_change_window_pct": 0.12,
    "price_change_status": "ready",
    "snapshot_age_ms": 48000
  },
  "flow": {
    "window": "1h",
    "mentions": 6,
    "watched_mentions": 0,
    "previous_mentions": 3,
    "mention_delta": 3,
    "mention_delta_pct": 1.0,
    "z_score": null,
    "stream_dominance": 0.03,
    "baseline_status": "insufficient_history"
  },
  "sources": {
    "unique_authors": 5,
    "watched_authors": 0,
    "weighted_reach": 120000,
    "top_author_share": 0.33,
    "source_quality_score": 60,
    "source_quality_reasons": ["multi_author", "resolved_ca"]
  },
  "fresh": {
    "latest_evidence_age_ms": 120000,
    "first_seen_age_ms": 7200000,
    "market_snapshot_age_ms": 48000,
    "is_new_token": false,
    "is_first_seen_by_watched": false
  },
  "signal": {
    "decision": "watch",
    "score": 62,
    "reasons": ["resolved_ca", "fresh_market", "multi_author_flow"],
    "risks": ["no_watched_confirmation"],
    "evidence_id": "event-..."
  },
  "evidence_best": {
    "event_id": "event-...",
    "score": 74,
    "handle": "source",
    "text": "...",
    "received_at_ms": 1777789000000,
    "url": "https://...",
    "reasons": ["direct_ca", "recent", "independent_author"]
  },
  "evidence": []
}
```

### Compatibility Policy

No adapter layer. This intentionally changes the product surface:

- Do not keep old `EV` semantics.
- Do not keep `narrative` as anomaly reason.
- Do not keep frontend fallback decision logic except local user override.
- Do not add hidden aliases for old API names unless tests show another current endpoint still needs them.

---

## Implementation Tasks

### Task 1: Add Failing Backend Contract Tests

**Files:**

- `tests/test_token_conviction_flow.py`
- `tests/test_sqlite_repositories.py`
- `tests/test_api_http.py`

- [x] Add tests that `/api/token-flow` returns `market`, `flow`, `sources`, `fresh`, `signal`, and `evidence_best`.
- [x] Add tests that `market.price_change_window_pct` is computed from stored snapshots across the requested window.
- [x] Add tests that missing market cap produces `signal.decision = discard` or a risk reason, not a high-confidence signal.
- [x] Add tests that source concentration penalizes the signal when one author dominates.
- [ ] Add tests that a resolved CA with fresh market and independent authors can become `watch` or `driver`.
- [x] Run `uv run pytest tests/test_token_conviction_flow.py tests/test_sqlite_repositories.py tests/test_api_http.py -q`.
- [x] Expected before implementation: failures for missing semantic blocks.

### Task 2: Refactor Token Flow Service Into Semantic Blocks

**Files:**

- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
- `src/gmgn_twitter_intel/storage/signal_repository.py`
- `src/gmgn_twitter_intel/storage/token_repository.py`

- [x] Split `_conviction_item` into `_identity_block`, `_market_block`, `_flow_block`, `_sources_block`, `_fresh_block`, `_signal_block`, and `_evidence_best_block`.
- [x] Add token market snapshot history lookup for window-start and window-end price.
- [x] Add previous-window token row lookup for `previous_mentions`, `mention_delta`, and `mention_delta_pct`.
- [x] Add source concentration calculation as `top_author_share`.
- [x] Add watched-author count derived from event token mentions.
- [x] Add latest evidence age and first-seen age using token window evidence and token first seen fields.
- [x] Make signal decision a backend field with reasons and risks.

### Task 3: Define Signal Rules Explicitly

**Files:**

- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
- `tests/test_token_conviction_flow.py`

- [x] Implement `driver/watch/discard` as deterministic rule output.
- [x] Use `driver` only when identity, market, flow, and source quality all pass minimum thresholds.
- [x] Use `watch` for valid but incomplete setups.
- [x] Use `discard` for unresolved/ambiguous identity, missing market, stale market with no recent evidence, or high manipulation risk.
- [x] Expose `signal.score` as a composite opportunity score, not generic confidence.
- [x] Remove `confidence` from the token-flow frontend surface.

### Task 4: Update Frontend Types And Table Columns

**Files:**

- `web/src/api/types.ts`
- `web/src/App.tsx`
- `web/src/lib/format.ts`
- `web/src/App.test.tsx`
- `web/src/lib/format.test.ts`

- [x] Replace table headers with `Token`, `MCap`, `Δ`, `Flow`, `Sources`, `Fresh`, `Signal`.
- [x] Remove primary table columns `EV`, `narrative`, and raw `accts`.
- [x] Render market cap with compact USD formatting.
- [x] Render `Δ` only from `market.price_change_window_pct`; show `-` when insufficient.
- [x] Render `Flow` as `mentions +delta`.
- [x] Render `Sources` as watched/unique plus concentration marker.
- [x] Render `Fresh` as latest evidence age and market snapshot status.
- [x] Render `Signal` from backend `signal.decision`, with local override stored separately.
- [x] Move best evidence into the detail drawer, not the table.

### Task 5: Redesign Detail Drawer Around Evidence

**Files:**

- `web/src/App.tsx`
- `web/src/styles.css`

- [x] Make selected token drawer start with `Signal`, `MCap`, `Δ`, `Flow`, `Sources`, `Fresh`, and `Risk`.
- [x] Show `evidence_best` first with its scoring reasons.
- [x] Show remaining evidence sorted by evidence score or recency.
- [x] Show risk tags separately from signal reasons.
- [x] Preserve decision controls, but make manual decisions clearly override backend signal.

### Task 6: Keep Visual Style Consistent With Current Direction

**Files:**

- `web/src/styles.css`

- [x] Preserve Inter + JetBrains Mono.
- [x] Preserve single amber accent.
- [x] Use green/red only for price direction.
- [x] Use decision labels for `driver/watch/discard`.
- [x] Keep Linear-like density and restrained table styling.
- [x] Ensure columns fit at current desktop width without text overlap.

### Task 7: Add Data Quality And Manipulation Guardrails

**Files:**

- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
- `tests/test_token_conviction_flow.py`

- [x] Penalize symbol-only and ambiguous symbols.
- [x] Penalize missing market cap.
- [x] Penalize high top-author concentration.
- [x] Penalize stale market snapshots.
- [ ] Penalize repeated text clusters if enough evidence text exists to detect simple duplicates.
- [x] Add explicit `signal.risks` instead of hiding risk inside confidence reasons.

### Task 8: Verify API, Frontend, And Runtime

**Files:**

- All touched files.

- [x] Run `uv run pytest`.
- [x] Run `uv run ruff check .`.
- [x] Run `uv run python -m compileall src tests`.
- [x] Run `cd web && npm test -- --run`.
- [x] Run `cd web && npm run build`.
- [x] Run `docker compose up -d --build`.
- [x] Verify `/readyz`.
- [x] Verify `/api/token-flow?window=1h&scope=all` includes semantic blocks.
- [x] Verify browser at `http://127.0.0.1:8765/` shows `Token / MCap / Δ / Flow / Sources / Fresh / Signal`.
- [ ] Click known examples:
  - `0x5f03ddcb6c7d9ed83f21346bb9c97d9e51a84444` should show `蛋猫 / bsc / fresh / mcap`.
  - `HdnLJtbdcqRx2bnqFmBLLo5ELsETtFpgzfymQ1zMpump` should show `ROCK / solana / fresh / mcap`.

---

## Future On-Chain Extension

Do not add standalone liquidity as a core signal. Add an on-chain block only when at least some of these fields are available:

```text
onchain.holder_count
onchain.holder_growth_window
onchain.new_wallets_window
onchain.net_buy_usd
onchain.buy_sell_imbalance
onchain.smart_wallet_netflow_usd
onchain.top_holder_share
onchain.top_10_holder_share
onchain.dev_wallet_activity
onchain.lp_change_pct
```

Only then can liquidity be interpreted as:

- executable size,
- slippage risk,
- manipulation surface,
- flow confirmation,
- exit risk.

---

## Acceptance Criteria

- Token Radar primary columns are `Token`, `MCap`, `Δ`, `Flow`, `Sources`, `Fresh`, `Signal`.
- Market cap appears in the primary table.
- Price direction never shows `fresh/stale/missing`.
- `EV` is removed unless a real expected-value model exists.
- `narrative` is removed from the token table unless backed by actual narrative enrichment.
- `Signal` comes from backend rule output and includes reasons/risks.
- `Evidence` strongest item is explicitly scored and shown in the detail drawer.
- Symbol-only and ambiguous token rows are visibly downgraded.
- No old table adapter preserves the previous table semantics.
- Tests cover the new backend contract and frontend rendering.
