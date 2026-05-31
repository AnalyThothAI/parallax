# Token Radar Social Heat Research

Date: 2026-05-04

## Executive Summary

The current Token Radar already has the right spine for a trader product: store-first evidence, deterministic token attribution, rolling social windows, market snapshots, diffusion-health checks, full token-post pagination, and watched-account LLM enrichment. It can answer "which resolved token is being mentioned now?" better than a raw `$SYMBOL` search.

The gap is that it still mixes three different trader questions into one score:

- **Heat:** is discussion rising abnormally versus this token's own recent baseline and versus the stream?
- **Quality:** are the posts informative, token-specific, independent, and source-worthy, or are they repeated shill/noise?
- **Propagation:** who started it, who amplified it, how fast did independent authors appear, and did price move before or after social attention?

For trading, the product should not optimize for "most mentions." It should optimize for **unexpected, explainable, independently propagating attention before price fully reprices**.

## Product Thesis

Social heat is useful only when it creates an information imbalance:

```text
tradable opportunity =
  abnormal attention surprise
  x evidence specificity
  x independent propagation
  x source/account quality
  x tradeability
  x timing advantage versus price
  - manipulation and data-quality risk
```

This means Token Radar should become an attention triage board, not a popularity board. The top row should tell a trader:

- exact token identity: chain, CA, symbol, attribution confidence;
- heat: 5m/1h mentions, surprise, acceleration, stream share;
- quality: evidence type, post quality, source credibility, repeated-text risk;
- propagation: independent authors, top-author share, timeline and author lanes;
- market context: market cap, liquidity/pool if available, price change across the selected window;
- decision: driver/watch/discard with a visible contribution ledger and risk caps.

## Current Architecture Review

The data path is strong and mostly deterministic:

1. `collector/direct_ws.py` consumes GMGN anonymous public Twitter WebSocket frames.
2. `collector/normalizer.py` turns frames into stable `TwitterEvent` records.
3. `collector/service.py` applies the `cp=0/cp=1` snapshot gate, watched-handle matching, and store-first publish.
4. `pipeline/ingest_service.py` persists evidence, entities, token mentions, attributions, token alerts, and watched-account enrichment jobs transactionally.
5. `pipeline/entity_extractor.py` extracts CA, cashtag, hashtag, mention, URL, and domain entities deterministically.
6. `pipeline/token_identity_resolver.py` resolves GMGN token payloads, CAs, and symbol-only mentions into raw `event_token_mentions`.
7. `pipeline/token_attribution.py` materializes `event_token_attributions`, selecting symbol candidates only when market/social evidence clears confidence and margin thresholds.
8. `retrieval/rolling_token_flow.py` computes trailing windows from attribution rows, not from raw symbols.
9. `retrieval/token_flow_service.py` builds identity, market, flow, baseline, diffusion, freshness, watch, attribution, signal, and evidence-highlight blocks.
10. `retrieval/token_posts_service.py` serves full distinct token-attributed posts with keyset pagination.
11. `pipeline/enrichment_worker.py` runs LLM enrichment only for watched events.
12. `pipeline/narrative_seed_builder.py` and `pipeline/narrative_token_linker.py` connect watched-handle narrative seeds to later public-stream token mentions.
13. `api/http.py` exposes `/api/token-flow`, `/api/token-posts`, `/api/narrative-flow`, `/api/attention-frontier`, and related routes.
14. `web/src/App.tsx` renders the cockpit, token radar, focus drawer, all-posts tab, signal-explain tab, and narrative panels.

The most important existing invariant is good:

```text
LLM is enrichment, not the hot-path source of token facts.
```

Token facts come from stored events, deterministic extraction, token resolution, attribution, and market snapshots.

## Current Data Availability

### Stored Now

`events`

- tweet/event IDs, canonical URL, timestamps, author handle/name/avatar/followers/tags;
- clean/search text, URLs, cashtags, hashtags, mentions, media, reference event JSON;
- watched status, matched handles, raw JSON, normalized event JSON;
- FTS index for retrieval.

`event_entities`

- deterministic CA, symbol, hashtag, mention, URL/domain-like entities;
- confidence, chain, watched status, received time, author.

`tokens`, `token_aliases`

- chain/address/symbol/name/icon identity;
- alias mapping from symbols to resolved tokens.

`token_market_snapshots`

- `price`, `previous_price`, `market_cap`, source channel, raw JSON, received time;
- snapshots come from GMGN token payloads and OpenAPI token-info enrichment paths;
- raw JSON may contain liquidity, pool, holders, volume if GMGN provided those keys.

Answer to "do we record price?": **yes, but as sparse snapshots, not continuous OHLCV candles.** Current window price change is computed from stored snapshots at or before window start/end. If no distinct start snapshot exists, `price_change_status = insufficient_history`.

Runtime note: during this review, the default host data directory `/Users/qinghuan/.parallax/data` did not contain a live SQLite database, so this audit is based on code, schema, tests, and product surfaces rather than a live sample distribution.

`event_token_mentions`

- immutable raw mention facts: payload token, CA, symbol-only, unresolved chain CA;
- event, identity key, token ID if known, chain, address, symbol, source, author, followers.

`event_token_attributions`

- derived attribution rows: `direct`, `selected`, `rejected`, `ambiguous`, `weak_candidate`, `unresolved`;
- confidence, attribution weight, rank, candidate count, feature/reason/risk JSON.

`account_token_alerts`

- first global/by-author watched-account token mention alerts.

`event_enrichments`, `event_token_candidates`, `event_narratives`

- watched-account LLM summaries, token candidates, and narrative items.

`narrative_windows`, `narrative_seeds`, `narrative_token_links`

- narrative activity buckets, watched-account seeds, and deterministic seed-to-token links.

### Not Stored Yet

These absences matter for product claims:

- Twitter/X engagement metrics: likes, reposts, replies, views, bookmarks.
- Full retweet/reply graph. There is reference JSON, but not a complete cascade graph.
- Full Twitter firehose coverage. The system explicitly has `coverage=public_stream`.
- Continuous token price candles, DEX trades, buy/sell imbalance, holder growth, wallet cohorts, or smart-money flow.
- Historical account precision/recall: no account-quality table yet.
- LLM or embedding-based post quality labels for all posts.
- Narrative clusters across all public-stream posts; current LLM runs only watched events.
- Backtest labels tying social bursts to future returns, drawdown, and liquidity.

## Current Token Radar Mechanics

`RollingTokenFlow` reads `event_token_attributions` where:

- `token_id IS NOT NULL`;
- attribution is `direct` or `selected`;
- attribution weight is positive;
- chain/address are tradeable, not `unknown`, `evm`, or `evm_unknown`.

It builds trailing `5m`, `1h`, `4h`, and `24h` observation windows, then adds:

- mention counts and watched mention counts;
- direct versus selected symbol mentions;
- unique authors, watched authors, weighted reach from follower counts;
- top events and top authors;
- market mindshare and watched mindshare within the stored stream;
- EWMA baseline sample counts and `z_score`/`new_burst_score`;
- first/latest evidence bounds.

`TokenFlowService` then adds:

- market status and sparse window price change;
- diffusion health from independent authors, repeated text clusters, top-author concentration, shill-pattern checks;
- watched confirmation or watched seed link;
- attribution confidence and reasons/risks;
- deterministic `signal_block` with score contributions and risk caps;
- top evidence highlights;
- `posts_query` and `evidence_total_count`.

The current score is explainable but still heuristic. It is an accounting ledger, not a statistically calibrated probability.

## Current Frontend Evidence Issue

The backend now has `/api/token-posts`, and the frontend fetches selected-token posts with TanStack `useInfiniteQuery`, 24 posts per page. The focus drawer defaults selected tokens to the `全部帖子` tab and has a load-more button.

What can still feel missing:

- `/api/token-flow` only carries `evidence_highlights`, capped by `top_events` and sorted as explanation samples. That is not full evidence.
- The all-posts view exists only after selecting a token row.
- The UI does not yet show a true **social propagation timeline**. It shows a list of posts, not author lanes, buckets, phases, seed/amplifier roles, or price-over-social overlay.
- Narrative-linked evidence is summarized as seed-token links, but there is no "show every post in this narrative-driven cascade" product surface.

So the fix is not only "increase the highlight limit." The product needs a dedicated token social timeline.

## Current LLM Narrative Readability Issue

The LLM prompt requires JSON with `summary`, `token_candidates`, `narratives`, `stance`, `intent`, and `confidence`. Narrative labels are normalized to snake case by `_label()`. The frontend displays `narrative_label` directly, so labels such as `ai_agent_grok` or noisy labels are not readable as trader copy.

Chinese is the right product surface for this cockpit if the primary trader is Chinese-speaking. The stable machine key can stay snake_case, but the model should also output:

- `display_name_zh`: short readable label, e.g. `Grok AI Agent`;
- `headline_zh`: one-line Chinese trader headline;
- `summary_zh`: 1-2 Chinese sentences;
- `why_it_matters_zh`: Chinese market interpretation;
- `evidence_quote`: exact substring from the post;
- `confidence` and `risks`.

The prompt must continue requiring evidence-bound substrings. Chinese readability should not relax grounding.

## External Research Synthesis

### Attention Predicts Activity, But It Is Not Causality

Investor attention research in traditional markets shows that attention proxies can affect buying pressure and short-horizon behavior, but attention also attracts noise and reversals. Da, Engelberg, and Gao's search-attention work is a canonical reference for abnormal attention as a market signal rather than simple volume counting.

Crypto-specific work similarly studies social-media attention, sentiment, returns, and volume. Recent papers on Twitter/social-media attention in cryptocurrency markets support the idea that abnormal attention can be associated with returns, volume, liquidity, or short-term price movement, while also showing that results depend heavily on source selection, sentiment method, and market context. The useful conclusion for this product is conservative: social attention is a **candidate event trigger**, not a standalone buy signal. It must be paired with identity, price/liquidity, diffusion, and manipulation checks.

### Bursts Should Be Relative To Baselines

Kleinberg's burst detection frames bursts as state changes in event streams, not raw counts. For Token Radar, this supports:

- per-token baselines instead of global thresholds;
- multi-window detection: 5m for ignition, 1h for confirmation, 24h for regime;
- surprise metrics such as EWMA z-score, robust z-score, and new-burst score.

### Diffusion Quality Matters

Social contagion and cascade research warns that total volume hides structure. A burst from one author, repeated text, or a coordinated cluster is not the same as independent adoption. Token Radar's current diffusion checks are directionally right: independent authors, top-author share, repeated text share, and watched confirmation should be first-class.

Better future metrics:

- effective authors using entropy or Herfindahl-Hirschman concentration;
- reproduction proxy: new independent authors in bucket `t+1` divided by active authors in bucket `t`;
- cascade depth/structural virality when reply/repost/reference edges become reliable;
- Hawkes-style self-excitation estimate once event history is dense enough.

### Industry Social Metrics Support Normalization

Crypto analytics products often distinguish raw social volume from social dominance, engagement, contributor count, and sentiment. The product lesson is useful even if implementations differ:

- show share of stream, not only mentions;
- separate contributors/authors from posts;
- expose concentration and spam/manipulation risk;
- combine social metrics with market data instead of treating social alone as tradeability.

## First-Principles Metric Design

### 1. Social Heat

Social heat should measure abnormal attention, not popularity.

Inputs:

- `mentions_5m`, `mentions_1h`, `mentions_24h`;
- `weighted_mentions` from attribution weights;
- `stream_share = token_mentions / all_token_mentions`;
- `watched_share = watched_token_mentions / watched_token_mentions_total`;
- `previous_mentions`, `mention_delta`, `mention_delta_pct`;
- EWMA or robust baseline `z_score`;
- `new_burst_score` when baseline is sparse;
- first-seen and first-watched flags.

Recommended display:

```text
Heat 86
5m 12 +9 z3.1
1h 31 +24
share 4.2%
new watched
```

### 2. Discussion Quality

Discussion quality should answer: "Are these posts useful evidence, or just noise?"

Inputs:

- token specificity: GMGN token payload/CA/direct attribution/cashtag selected/symbol-only;
- attribution confidence and margin;
- text originality: duplicate fingerprint share;
- information density: contains CA, chart/price/market cap, reason/catalyst, named product/person/event, or concrete risk;
- source credibility: watched account, follower sanity, later account score;
- independent corroboration: non-duplicate authors;
- recency;
- market confirmation availability.

V1 can be deterministic. LLM can later label post utility asynchronously, but it should not be in the live ranking path.

### 3. Propagation

Propagation should answer: "How did attention move through authors over time?"

Inputs:

- author lanes: seed, first public token mention, top amplifiers, watched authors;
- per-bucket posts, unique authors, new authors;
- top-author share and effective author count;
- repeated-text clusters;
- lag from watched narrative seed to first token mention;
- lag from first token mention to price move;
- reproduction proxy across buckets.

Recommended product surface:

```text
Timeline
T0  @watched seed: "..."
+2m @author1 CA post
+4m 3 new authors, 2 duplicate-free
+8m price +12%, social still expanding
+15m top author share down to 32%
```

### 4. Tradeability

Tradeability should not be inferred from social data.

Inputs now:

- market cap;
- price snapshot and window price change;
- liquidity/pool/holders/volume only when present in raw GMGN snapshot;
- market snapshot age.

Inputs needed later:

- continuous DEX candles;
- liquidity depth and slippage;
- holder growth;
- buy/sell imbalance;
- smart-wallet net flow;
- top-holder concentration;
- dev/LP changes.

### 5. Timing Read

The trader question is not simply "hot?" It is "am I early or late?"

Useful states:

- `social_leads_price`: social z-score is high, price window change still small.
- `social_confirms_price`: both social and price are moving.
- `price_leads_social`: price already moved before social burst; chase risk.
- `social_fades`: social heat decelerates after price move.
- `data_insufficient`: sparse snapshots or too few posts.

## Proposed Score System

Use layered scores, not one opaque number.

```text
opportunity_score =
  0.30 * social_heat_score
  + 0.25 * discussion_quality_score
  + 0.20 * propagation_score
  + 0.15 * tradeability_score
  + 0.10 * timing_score
```

Apply hard gates and risk caps after additive scoring:

- unresolved/ambiguous token identity cannot be `driver`;
- missing market snapshot or market cap cannot be `driver`;
- repeated-text cluster caps opportunity at 45;
- author concentration caps opportunity at 65 until independent confirmation;
- stale market caps opportunity at 70;
- public-only with no watched or historical-quality source confirmation caps opportunity at 85;
- price already moved too far before social confirmation adds chase-risk cap.

Every score should return:

```json
{
  "score": 82,
  "score_version": "social_opportunity_v1",
  "components": {
    "heat": 90,
    "quality": 77,
    "propagation": 68,
    "tradeability": 80,
    "timing": 72
  },
  "contributions": [
    {"feature": "heat.z_score_5m", "value": 22, "reason": "z_score_above_3"},
    {"feature": "quality.identity", "value": 15, "reason": "resolved_ca"}
  ],
  "risk_caps": [
    {"risk": "author_concentration_high", "cap": 65}
  ],
  "decision": "watch"
}
```

## Agent Design Recommendation

Do not put an agent in the live ranking path yet.

The live path should remain deterministic and fast:

```text
event -> entity extraction -> token attribution -> social windows -> scores -> API/UI
```

Use asynchronous, bounded agents where they add judgment without corrupting facts:

- **Narrative Readability Agent:** rewrites watched-event narrative output into Chinese trader copy, evidence-bound.
- **Post Quality Agent:** labels high-signal posts with information type: catalyst, CA drop, chart, endorsement, joke/meme, spam, copy-paste.
- **Account Quality Agent:** periodically scores authors from historical behavior: early calls, false positives, spam rate, independent confirmations, realized token performance after mentions.
- **Signal Critic Agent:** reviews only high-scoring candidates and writes a short "why now / why not" note, with citations to stored event IDs.
- **Calibration Agent:** runs offline backtests and proposes weight/threshold changes from realized outcomes.

Agent outputs must be stored as versioned enrichment with model, prompt version, evidence IDs, confidence, and risks. They should never overwrite deterministic facts.

## Product Direction

The next product surface should be a token-centered social propagation view:

- Token Radar top table: Heat, Quality, Propagation, Market, Timing, Decision.
- Token detail drawer:
  - `Timeline`: bucketed social heat and author lanes;
  - `Posts`: all posts with pagination;
  - `Score`: contribution ledger and risk caps;
  - `Narratives`: watched seeds and seed-token links;
  - `Accounts`: author quality and future watchlist candidates.

This gives traders a way to answer:

- what changed in the last 5m/1h?
- who caused it?
- is it independent or coordinated?
- is the token exact and tradeable?
- did price already move?
- which authors should be promoted into the watched list over time?

## References

- Da, Engelberg, and Gao, "In Search of Attention": https://academic.oup.com/jf/article-abstract/66/5/1461/2190067
- "Social media-based attention and the cross-section of cryptocurrency returns": https://www.sciencedirect.com/science/article/abs/pii/S0378426625001384
- "Bitcoin price change and trend prediction through twitter sentiment and data volume": https://link.springer.com/article/10.1186/s40854-022-00352-7
- "Does Twitter predict Bitcoin?": https://centaur.reading.ac.uk/80420/1/Twitter.Bitcoin.pdf
- Kleinberg, "Bursty and Hierarchical Structure in Streams": https://ecommons.cornell.edu/items/04b75865-7103-4954-a660-ee6c38e5e9a5
- Watts, "A simple model of global cascades on random networks": https://www.pnas.org/doi/10.1073/pnas.082090499
- Goel, Anderson, Hofman, and Watts, "The Structural Virality of Online Diffusion": https://pubsonline.informs.org/doi/10.1287/mnsc.2015.2158
- Bacry, Mastromatteo, and Muzy, "Hawkes Processes in Finance": https://doi.org/10.1142/S2382626615000057
- Santiment social dominance metric: https://academy.santiment.net/metrics/social-dominance/
- LunarCrush metric examples: https://lunarcrush.com/
