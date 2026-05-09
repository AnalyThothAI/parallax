# Token Radar Social Heat Product Spec

Date: 2026-05-04

## Goal

Redesign Token Radar into a trader-grade social heat and propagation system.

The product should detect when a token's social discussion accelerates abnormally in `5m` or `1h`, grade the quality of that discussion, show the full social propagation timeline, and explain whether the setup is a tradeable opportunity, a watch item, or noise.

## Non-Goals

- No automated trading.
- No claim of full Twitter/X coverage.
- No LLM in the live token-fact path.
- No opaque "AI score" without feature contributions and risk caps.
- No market claim from sparse social data alone.
- No treating symbol-only mentions as tradeable tokens unless attribution selects a resolved CA.

## User Stories

1. As a trader, I want to see which tokens have abnormal `5m` or `1h` social heat so I can catch early attention moves.
2. As a trader, I want to know whether the posts are high quality or coordinated spam before I trust the signal.
3. As a trader, I want to open one token and see every related post, author timeline, and propagation phases.
4. As a trader, I want readable Chinese narrative flow, not raw snake_case labels.
5. As a researcher, I want to learn which accounts repeatedly discover high-quality moves early.
6. As an operator, I want every score to be reproducible from stored evidence.
7. As a trader, I want the realtime signal tape to stay visible so I can see the global live/replay/enrichment pulse while scanning token opportunities.

## Target Product Model

### Token Radar Table

Replace the current single `Signal`-heavy scan with these semantic columns:

- `Token`: symbol, chain, short CA, identity/attribution status.
- `Heat`: opportunity heat score, `5m/1h` mentions, delta, z-score/new-burst.
- `Quality`: discussion quality score and top reason/risk.
- `Propagation`: independent authors, top-author share, reproduction trend.
- `Market`: market cap, liquidity/pool if available, sparse price delta.
- `Timing`: social-leads-price / confirms / chase-risk / insufficient data.
- `Decision`: driver/watch/discard from backend.

### Token Detail Drawer

Tabs:

- `Timeline`: bucketed heat, author lanes, seed/amplifier markers, price overlay.
- `Posts`: full attributed posts with pagination, score, reasons, risks.
- `Score`: score contribution ledger and risk caps.
- `Narratives`: watched-account seeds and seed-token links.
- `Accounts`: top authors, role, future watchlist candidate signals.

### Realtime Signal Tape

Keep the cockpit's realtime signal tape as a first-class global component, not as a token-detail tab and not as a replacement for the token timeline.

Purpose:

- show what just happened across live WebSocket events, replay rows, enrichment completions, and narrative-token links;
- preserve trader situational awareness while Token Radar ranks tradeable opportunities;
- let users jump from a live event to the related token, narrative seed, or source event without changing the radar sort mode.

Display:

- compact row format: `@handle -> $TOKEN`, `@handle -> narrative`, or watched event title;
- event kind: `watched`, `token`, `narrative`, `enrichment`, or `risk`;
- age, reason, and optional score such as post quality or opportunity score;
- selected row highlight synced to the focused event/token.

Layout:

- bottom deck of the main radar column, side by side with the Chinese narrative flow panel;
- minimum visible height of 140px before scrolling;
- never hidden inside the drawer, because it represents global market pulse rather than one token's propagation.

## Backend Data Contracts

### Extend Token Flow Item

`/api/token-flow` should keep existing blocks and add:

```json
{
  "social_heat": {
    "score": 0,
    "score_version": "social_heat_v1",
    "mentions_5m": 0,
    "mentions_1h": 0,
    "mentions_24h": 0,
    "weighted_mentions": 0.0,
    "stream_share": 0.0,
    "watched_share": 0.0,
    "previous_mentions": 0,
    "mention_delta": 0,
    "mention_delta_pct": null,
    "z_score": null,
    "new_burst_score": null,
    "status": "cold | rising | burst | new_burst | insufficient_history",
    "reasons": [],
    "risks": [],
    "contributions": [],
    "risk_caps": []
  },
  "discussion_quality": {
    "score": 0,
    "score_version": "discussion_quality_v1",
    "evidence_specificity": 0,
    "avg_post_quality": 0,
    "avg_attribution_confidence": 0.0,
    "duplicate_text_share": 0.0,
    "informative_post_count": 0,
    "watched_source_count": 0,
    "reasons": [],
    "risks": [],
    "contributions": [],
    "risk_caps": []
  },
  "propagation": {
    "score": 0,
    "score_version": "propagation_v1",
    "independent_authors": 0,
    "effective_authors": 0,
    "new_authors": 0,
    "top_author_share": 0.0,
    "author_entropy": 0.0,
    "reproduction_rate": null,
    "phase": "seed | ignition | expansion | concentration | fade",
    "top_authors": [],
    "reasons": [],
    "risks": [],
    "contributions": [],
    "risk_caps": []
  },
  "timing": {
    "status": "social_leads_price | social_confirms_price | price_leads_social | social_fades | insufficient_data",
    "social_start_ms": null,
    "first_price_move_ms": null,
    "price_change_window_pct": null,
    "chase_risk": false,
    "reasons": [],
    "risks": []
  },
  "opportunity": {
    "score": 0,
    "score_version": "social_opportunity_v1",
    "decision": "driver | watch | discard",
    "components": {
      "heat": 0,
      "quality": 0,
      "propagation": 0,
      "tradeability": 0,
      "timing": 0
    },
    "reasons": [],
    "risks": [],
    "contributions": [],
    "risk_caps": []
  }
}
```

This is a breaking API redesign. `/api/token-flow` should remove the old `signal`, `evidence_highlights`, and `evidence_highlight_best` blocks when this spec is implemented. The runtime does not migrate old token-radar data; incompatible app tables are reset and rebuilt from fresh collection.

### Realtime Signal Tape Contract

The tape should be built in the frontend from existing live/replay data plus new narrative/enrichment surfaces. It does not need a dedicated V1 endpoint.

Sources:

- WebSocket live payloads from `/ws`;
- `/api/recent` replay rows;
- enrichment updates attached to live payloads;
- narrative frontier rows that link watched-account seeds to tokens.

Frontend item model:

```ts
type LiveSignalTapeItem =
  | { kind: "event"; payload: LivePayload; score?: number | null; reason: string }
  | { kind: "token"; token: TokenFlowItem; event?: LivePayload | null; score?: number | null; reason: string }
  | { kind: "narrative"; item: AttentionFrontierItem; score?: number | null; reason: string }
  | { kind: "enrichment"; payload: LivePayload; score?: number | null; reason: string };
```

Rules:

- merge and dedupe live and replay events by event ID;
- keep latest rows first;
- clicking a token row selects the token but does not change `radarSortMode`;
- clicking a narrative row opens the `Narratives` tab and focuses the seed/link;
- clicking a watched event opens event focus without pretending the event is a token opportunity.

### New Timeline Endpoint

Add:

```text
GET /api/token-social-timeline?token_id=...&window=1h&scope=all&limit=200&cursor=...
GET /api/token-social-timeline?chain=...&address=...&window=1h&scope=all&limit=200&cursor=...
```

The service derives the bucket from the observation window: `5m -> 30s`, `1h -> 5m`, `4h -> 15m`, `24h -> 1h`.

Response:

```json
{
  "ok": true,
  "data": {
    "query": {
      "token_id": "token:base:0x...",
      "window": "1h",
      "bucket": "5m",
      "scope": "all"
    },
    "summary": {
      "posts": 42,
      "authors": 18,
      "effective_authors": 11,
      "first_seen_ms": 1777770000000,
      "latest_seen_ms": 1777773600000,
      "phase": "expansion",
      "top_author_share": 0.26,
      "duplicate_text_share": 0.08
    },
    "buckets": [
      {
        "start_ms": 1777770000000,
        "end_ms": 1777770060000,
        "posts": 2,
        "new_authors": 2,
        "watched_posts": 0,
        "duplicate_text_share": 0.0,
        "price": null,
        "price_change_from_start_pct": null
      }
    ],
    "authors": [
      {
        "handle": "source",
        "first_seen_ms": 1777770010000,
        "latest_seen_ms": 1777770900000,
        "posts": 3,
        "followers": 120000,
        "role": "seed | early_amplifier | amplifier | repeater | watched",
        "quality_score": null
      }
    ],
    "posts": [
      {
        "event_id": "event-...",
        "handle": "source",
        "received_at_ms": 1777770010000,
        "bucket_start_ms": 1777770000000,
        "text": "...",
        "url": "https://x.com/...",
        "attribution_status": "direct",
        "post_quality": {
          "score": 81,
          "reasons": ["resolved_ca", "informative_text", "recent"],
          "risks": []
        }
      }
    ],
    "has_more": true,
    "next_cursor": "opaque"
  }
}
```

V1 can compute this read-time from `event_token_attributions` plus `events`, using the same pagination pattern as `TokenPostsService`.

### New Score Modules

Create dedicated modules:

```text
src/gmgn_twitter_intel/retrieval/social_heat_scoring.py
src/gmgn_twitter_intel/retrieval/discussion_quality_scoring.py
src/gmgn_twitter_intel/retrieval/propagation_scoring.py
src/gmgn_twitter_intel/retrieval/opportunity_scoring.py
src/gmgn_twitter_intel/retrieval/token_social_timeline_service.py
```

Rules:

- Score modules are pure functions.
- Services fetch rows, group data, and call scoring functions.
- Repositories do not contain scoring logic.
- Every scoring output includes version, reasons, risks, contributions, and risk caps.

## Scoring Definitions

### Social Heat V1

Inputs:

- current attributed mentions;
- weighted attributed mentions;
- previous equal-window mentions;
- EWMA baseline z-score;
- new-burst score;
- stream share;
- watched share;
- first local evidence and first watched evidence flags.

Suggested components:

```text
+ up to 25: log-scaled current mentions
+ up to 25: z-score or new-burst surprise
+ up to 15: positive mention delta
+ up to 10: stream share above local median
+ up to 10: watched share or watched first-seen
+ up to 10: first local evidence inside window
+ up to 5: high attribution-weighted mentions
```

Risks:

- `insufficient_baseline`
- `thin_mentions`
- `public_stream_coverage`

### Discussion Quality V1

Inputs:

- post scores from existing `post_score`;
- direct/payload/CA/cashtag attribution mix;
- attribution confidence/weight;
- duplicate text share;
- watched source count;
- informative text heuristics.

Deterministic informative text heuristic:

- contains CA, symbol plus concrete verb/catalyst, price/market/volume/liquidity term, named product/person, or link/domain;
- penalize very short texts, repeated slogans, excessive cashtags, same fingerprint cluster.

Suggested components:

```text
+ up to 20: resolved/direct token evidence
+ up to 20: average attribution confidence
+ up to 15: informative text ratio
+ up to 15: watched or known source presence
+ up to 15: non-duplicate originality
+ up to 15: market context present in evidence
```

Risks:

- `symbol_only_no_market_identity`
- `duplicate_text_cluster`
- `attribution_confidence_low`
- `low_information_posts`

### Propagation V1

Inputs:

- independent authors;
- effective authors from author entropy;
- new authors by bucket;
- top-author share;
- repeated cluster count;
- watched author presence;
- seed lag if linked to narrative seed.

Suggested components:

```text
+ up to 25: independent author count
+ up to 20: effective author count
+ up to 15: new-author growth across buckets
+ up to 15: low top-author concentration
+ up to 10: watched author or narrative seed link
+ up to 10: fast seed-to-token lag
+ up to 5: repeated text remains low
```

Risks:

- `author_concentration_high`
- `thin_author_set`
- `repeated_text_cluster`
- `single_source_broadcast`

### Timing V1

Inputs:

- social first-seen and burst time;
- price snapshots at/around social start and window end;
- price change before social start when available;
- current window price change.

States:

- `social_leads_price`: social heat high, price change small or unavailable before burst.
- `social_confirms_price`: social and price both rise in the same window.
- `price_leads_social`: price moved materially before social expansion.
- `social_fades`: current heat below previous after a price move.
- `insufficient_data`: missing snapshots.

Risk:

- `chase_risk` when price change is already large and social is late.

## Narrative Flow Readability

### LLM Output Contract

Extend watched-event enrichment schema:

```json
{
  "summary_zh": "一段简洁的中文事件摘要。",
  "narratives": [
    {
      "label": "ai_agent_grok",
      "display_name_zh": "Grok AI Agent",
      "headline_zh": "Grok 相关发言重新点燃 AI Agent 代币注意力",
      "description_zh": "面向交易员的中文解释。",
      "seed_family": "ai_agent",
      "trigger_terms": ["grok", "ai agent"],
      "market_interpretation_zh": "交易员可能会关注 Grok、xAI 或 AI Agent 主题 token 是否出现独立扩散。",
      "evidence": "exact substring",
      "confidence": 0.86,
      "risks": []
    }
  ]
}
```

Validation:

- `evidence` and every `trigger_term` must be grounded in event text.
- Chinese display fields are required for UI.
- `label` remains the stable machine key.
- If display fields are missing, treat the row as a contract error and show `narrative_display_missing`; do not repair it from old summaries or machine labels in runtime.

### Storage

Add nullable columns first:

```sql
ALTER TABLE event_enrichments ADD COLUMN summary_zh TEXT;
ALTER TABLE event_narratives ADD COLUMN display_name_zh TEXT;
ALTER TABLE event_narratives ADD COLUMN headline_zh TEXT;
ALTER TABLE event_narratives ADD COLUMN description_zh TEXT;
ALTER TABLE event_narratives ADD COLUMN market_interpretation_zh TEXT;
ALTER TABLE narrative_seeds ADD COLUMN display_name_zh TEXT;
ALTER TABLE narrative_seeds ADD COLUMN headline_zh TEXT;
ALTER TABLE narrative_seeds ADD COLUMN market_interpretation_zh TEXT;
```

If SQLite migration simplicity is preferred, create schema v8 with idempotent `PRAGMA table_info` checks instead of raw unconditional `ALTER TABLE`.

## Account Quality Learning

V1 should not pretend account quality exists. Add the foundation:

```text
account_profiles
  handle
  first_seen_ms
  latest_seen_ms
  follower_max
  watched_status

account_token_call_stats
  handle
  token_id
  first_mention_ms
  mention_count
  was_early_author
  price_change_5m_pct
  price_change_1h_pct
  price_change_24h_pct
  max_drawdown_1h_pct
  outcome_status

account_quality_snapshots
  handle
  window
  precision_score
  early_call_score
  spam_risk_score
  avg_realized_return
  sample_size
  updated_at_ms
```

Do not use these scores in live ranking until sample size and calibration are visible.

## Agent Boundary

Add agents only as async enrichment workers:

- `narrative_readability`: converts evidence-bound narratives into Chinese display copy.
- `post_quality`: labels top posts and selected high-heat token posts.
- `account_quality`: updates account-quality snapshots from realized outcomes.
- `signal_critic`: writes a short evidence-bound note for high-scoring candidates.
- `calibration`: offline job proposing threshold changes from backtests.

Hard rules:

- agent outputs are versioned;
- agent outputs reference event IDs;
- deterministic scores can cite agent labels only when label version and confidence are present;
- no agent can invent token identity, price, or market fields.

## Implementation Plan

### Phase 1: Deterministic Social Heat And Timeline

Files:

- `src/gmgn_twitter_intel/retrieval/social_heat_scoring.py`
- `src/gmgn_twitter_intel/retrieval/discussion_quality_scoring.py`
- `src/gmgn_twitter_intel/retrieval/propagation_scoring.py`
- `src/gmgn_twitter_intel/retrieval/opportunity_scoring.py`
- `src/gmgn_twitter_intel/retrieval/token_social_timeline_service.py`
- `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
- `src/gmgn_twitter_intel/api/http.py`
- `web/src/api/types.ts`
- `web/src/components/LiveSignalTape.tsx`
- `web/src/App.tsx`

Tasks:

- Add pure score modules and tests.
- Add read-time timeline service with bucket aggregation and author roles.
- Add `/api/token-social-timeline`.
- Extend `/api/token-flow` with social heat, quality, propagation, timing, opportunity.
- Update radar columns and detail drawer tabs.
- Keep the realtime signal tape in the main bottom deck and populate it from live/replay/enrichment/narrative-link rows.
- Keep `/api/token-posts` as the full post feed.

### Phase 2: Chinese Narrative Flow

Files:

- `src/gmgn_twitter_intel/pipeline/llm_enrichment.py`
- `src/gmgn_twitter_intel/storage/enrichment_repository.py`
- `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- `src/gmgn_twitter_intel/retrieval/narrative_service.py`
- `web/src/api/types.ts`
- `web/src/App.tsx`

Tasks:

- Extend prompt and parser for Chinese display fields.
- Add migration columns.
- Store readable fields in event narratives and narrative seeds.
- Update narrative flow UI to display `display_name_zh`, `headline_zh`, and `market_interpretation_zh`.
- Keep snake_case labels as machine keys only.

### Phase 3: Account Quality Foundation

Files:

- `src/gmgn_twitter_intel/storage/sqlite_schema.py`
- `src/gmgn_twitter_intel/storage/account_quality_repository.py`
- `src/gmgn_twitter_intel/pipeline/account_quality_worker.py`
- `src/gmgn_twitter_intel/retrieval/account_quality_service.py`
- `src/gmgn_twitter_intel/api/http.py`

Tasks:

- Add account profile/stat tables.
- Backfill first mentions per token/author from `event_token_attributions`.
- Join sparse market snapshots to calculate provisional outcomes.
- Expose account quality read API for research, not live ranking.

### Phase 4: Agentic Enrichment

Files:

- `src/gmgn_twitter_intel/pipeline/agent_jobs.py`
- `src/gmgn_twitter_intel/storage/agent_repository.py`
- `src/gmgn_twitter_intel/pipeline/post_quality_agent.py`
- `src/gmgn_twitter_intel/pipeline/signal_critic_agent.py`

Tasks:

- Add versioned agent job table.
- Add post-quality labels for high-heat tokens only.
- Add evidence-bound signal critic notes.
- Keep deterministic fallback when LLM/agent is disabled.

## Acceptance Criteria

- A token with a fast `5m` or `1h` rise shows heat score, baseline surprise, and acceleration separately.
- A token row displays discussion quality separately from raw heat.
- A selected token shows all posts, bucketed timeline, top authors, and author roles.
- Timeline distinguishes one-author broadcasts from independent expansion.
- Realtime signal tape remains visible as a global live pulse and is not replaced by token Timeline.
- Narrative flow displays readable Chinese copy while preserving machine labels.
- Score output includes component scores, reasons, risks, contributions, and risk caps.
- `driver` cannot be assigned to unresolved tokens, missing market context, repeated text clusters, or highly concentrated author sets.
- Agent outputs are optional and never required for live token radar.

## Verification Commands

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
cd web && npm test -- --run
cd web && npm run build
```
