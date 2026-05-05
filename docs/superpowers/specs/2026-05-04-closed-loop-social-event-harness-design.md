# Closed Loop Social Event Harness Design Spec

Date: 2026-05-04

## Executive Summary

This project should stop treating LLM enrichment as a narrative display feature and turn it into a closed-loop social-event harness.

The new production primitive is not a "narrative label". It is:

```text
high-value watched account event
  -> evidence-bound social event extraction
  -> attention seed
  -> deterministic token / phrase / CA uptake validation
  -> frozen shadow snapshot
  -> outcome settlement
  -> multi-event credit attribution
  -> slow explainable weight update
  -> config evaluation before promotion
```

The LLM does not decide trades. It only converts one watched-account text event into a structured, evidence-bound social event. The harness owns every decision-like operation: scoring, freezing state, assigning shadow/paper decisions, settling future returns, attributing credit, updating weights, and evaluating whether a config version improves.

V1 does not add external news sources. GMGN/X remains the only runtime source. This is intentional: the fastest route to a real closed loop is to build it on the source we already store and can replay.

This is a breaking redesign. The implementation should not preserve compatibility code for the old narrative-first LLM contract. Old narrative endpoints, old enrichment parser shapes, old UI assumptions, and old fallback fields should be removed or rewritten against the new harness model.

## Detailed Summary And Decision

### Decision

Replace the current narrative enrichment contract with a closed-loop social-event harness.

The old system answers:

```text
What narrative label did the LLM assign to this watched event?
```

The new system answers:

```text
What attention event did this watched account create?
Can that event be expressed through deterministic token evidence?
Was there post-seed uptake?
Was price already moved?
Did the frozen snapshot predict future abnormal return?
How should source/event/horizon weights change after settlement?
```

### What Changes Fundamentally

The core object changes:

```text
old: event_narrative / narrative_window
new: social_event_extraction / attention_seed / event_cluster / harness_snapshot
```

The LLM contract changes:

```text
old: summary + token_candidates + narratives + stance + intent
new: strict social-event-v1 extraction with anchor terms, attention mechanism, semantic risk, and token candidates
```

The product question changes:

```text
old: show me what topics are flowing
new: show me which attention seeds became tradeable hypotheses and whether they worked
```

The evaluation target changes:

```text
old: no reliable target, mostly narrative readability
new: future normalized abnormal return by frozen snapshot and horizon
```

### What Does Not Change

These are not compatibility layers; they are still valid infrastructure:

- GMGN/X remains the only V1 source.
- Full-stream ingest stays deterministic and independent of LLM.
- Evidence storage, entity extraction, token identity resolution, token mentions, token market snapshots, and token-flow facts remain the factual substrate.
- LLM remains asynchronous and watched-account-only.
- No live trading is introduced.

### What Is Removed

Remove or rewrite:

- old `NarrativeItem` as the primary LLM output contract;
- parser acceptance for old narrative-only shapes;
- compatibility derivation from `SocialEventExtraction` back into fake `narratives`;
- narrative display fallback fields that hide missing new harness data;
- API/UI assumptions that `narrative_label` is a trader-facing product surface;
- any fallback path that says "if harness field missing, use legacy narrative field".

### What Replaces It

The replacement product surface is:

```text
Social Events
Attention Seeds
Attention Frontier
Harness Snapshots
Shadow Decisions
Outcomes
Credits
Weights
Score Buckets
```

`narrative-flow` can be removed, renamed, or rebuilt as a thin read model over social events. It should not continue as a separate legacy semantic system.

## Why The Current Narrative Flow Fails

The current narrative flow is hard to trade because it answers a weak question:

```text
What topic did the watched account mention?
```

Trading needs stronger questions:

```text
What changed in market attention?
Who caused the change?
What exact words or objects can spread?
Which token identities can express it?
Was uptake observed after the seed?
Was price already moved before the seed?
Did similar events historically predict abnormal return?
```

The current chain stores `event_narratives`, `account_narrative_alerts`, `narrative_windows`, `narrative_seeds`, and `narrative_token_links`. This is useful evidence infrastructure, but the LLM output still speaks the language of "story". It does not produce a hypothesis that can be frozen, settled, and scored against future abnormal return.

This spec replaces the LLM contract and adds the missing harness loop.

## First Principles

### 1. Meme/news trading is attention trading first

For accounts like CZ, Elon Musk, and He Yi, the valuable signal is often not a direct investment statement. It is the creation or amplification of an attention coordinate:

```text
new phrase
new object
new reply target
new product mention
new exchange/listing hint
new meme-able association
new negative risk focus
```

Examples:

- CZ says a short, repeatable phrase around BNB.
- Musk mentions a product, animal, robot, AI, or cultural object that can become a token-mapping target.
- He Yi discusses listing standards, Binance Alpha, BNB Chain activity, or meme market structure.

The tradeable object appears only if the attention coordinate maps to deterministic token evidence and public-stream uptake.

### 2. LLM cognition must be bounded

The LLM is useful for semantic compression:

```text
raw post -> social event object
```

It is not allowed to:

- decide buy/sell;
- size a position;
- assign `driver/watch/discard`;
- invent hidden tickers;
- decide source weights;
- update event-type weights;
- claim causal PnL attribution;
- rewrite history after settlement.

### 3. Harness owns causality discipline

The harness must enforce:

- only pre-decision information is used;
- every snapshot is immutable once recorded;
- every score has a version;
- every outcome is abnormal return, not raw return;
- every credit assignment is multi-event and probabilistic, not causal certainty;
- every weight update is slow and shrinkage-protected.

### 4. Shadow comes before live

The first useful product is not automatic trading. It is an auditable shadow loop that can answer:

```text
Do higher scores lead to better future abnormal return buckets?
Which sources and event types have positive credit?
Which horizons work?
Which signals fail because price already moved?
```

Until this is true, UI polish and live execution are distractions.

## External Practice Review

The design follows current agent harness practice:

- Martin Fowler's harness engineering framing: production agent quality comes from the model's surrounding control system: context, tools, feedback, constraints, and iteration. Reference: https://martinfowler.com/articles/harness-engineering.html
- Anthropic's agent guidance: use simpler workflows when the task can be decomposed into clear deterministic steps; reserve open-ended agency for cases that require it. Reference: https://www.anthropic.com/engineering/building-effective-agents
- OpenAI Structured Outputs: model responses should be constrained by JSON Schema when downstream code depends on exact fields. Reference: https://platform.openai.com/docs/guides/structured-outputs
- LangGraph durable execution: durable state/checkpointing matters when workflow progress must be recoverable and auditable. V1 uses SQLite directly instead of adding LangGraph because the repository already has a durable SQLite evidence store. Reference: https://docs.langchain.com/oss/python/langgraph/durable-execution

The implication for this repository:

```text
Do not build a clever autonomous trading agent.
Build a deterministic harness around one structured LLM extraction node.
```

## Current System Fit

The current architecture already has the right foundation:

- `collector/direct_ws.py` receives GMGN public Twitter frames.
- `collector/normalizer.py` creates stable event objects.
- `pipeline/ingest_service.py` transactionally stores evidence/entities/token mentions and queues watched-account enrichment.
- `pipeline/entity_extractor.py` deterministically extracts CA, cashtag, hashtags, mentions, URLs, and domains.
- `pipeline/token_identity_resolver.py` resolves CA/symbol identity.
- `pipeline/signal_builder.py` writes token mentions, alerts, and rolling windows.
- `pipeline/enrichment_worker.py` runs the watched-account LLM path asynchronously.
- `storage/enrichment_repository.py` stores current LLM enrichment and narrative objects.
- `pipeline/narrative_token_linker.py` already validates seed-token uptake with deterministic token evidence.
- `retrieval/token_flow_service.py` already exposes trader-oriented token flow blocks.

The important invariant remains:

```text
Full public stream is deterministic ingest.
Only configured watched handles enter the LLM path.
```

This spec preserves that invariant.

## Non-Goals

V1 explicitly does not:

- ingest RSS/news APIs;
- ingest SEC, exchange announcements, or other external feeds;
- run LLM over the full public stream;
- trade live;
- execute broker/exchange orders;
- fine-tune models;
- add LangGraph/MLflow as required dependencies;
- claim full Twitter/X firehose coverage;
- turn unresolved symbols into tradable token identities.

## Breaking Change Policy

This project should use a deliberate breaking-change policy.

### No Compatibility Code

Do not add:

- legacy parser branches for old `narratives` payloads;
- dual-write compatibility layers that maintain both old narrative and new harness products;
- API fallbacks from new response fields to old `narrative_label` / `summary` fields;
- UI fallback rendering that silently treats missing harness state as old narrative data;
- migration glue that tries to reinterpret historical narrative rows as if they were social-event extractions.

The old records can remain in historical SQLite databases, but new runtime code should not depend on them for product behavior.

### Allowed Reuse

Allowed reuse is limited to factual infrastructure:

- existing `events`;
- `event_entities`;
- `event_token_mentions`;
- `event_token_attributions`;
- `tokens`;
- `token_market_snapshots`;
- low-level SQLite connection/migration helpers;
- deterministic token-linking primitives where they can be renamed or refit cleanly.

This reuse does not count as compatibility code because these tables store facts, not old product semantics.

### Data Migration Position

For local/dev/runtime stores, the preferred migration is:

```text
schema version bump
-> app table rebuild or explicit destructive migration
-> new harness tables start empty
-> future events populate the closed loop
```

Historical old narrative rows should not be backfilled into `social_event_extractions` unless a separate offline replay job re-runs the new extractor from original event text and records new prompt/schema/model versions.

### API Position

Breaking API changes are acceptable for:

- `narrative-flow`;
- `account-narratives`;
- enrichment payload shape;
- cockpit narrative panels.

The stable facts APIs can remain if they are still semantically correct:

- recent events;
- search;
- token-flow facts;
- token posts;
- token social timeline.

If an old endpoint survives, it must serve new harness semantics directly. It must not be a legacy compatibility endpoint.

## Domain Vocabulary

### Raw Event

One normalized GMGN/X event stored in `events`.

### Social Event Extraction

LLM output from one watched event. It is a structured interpretation of attention mechanics, not a trade recommendation.

### Attention Seed

A durable seed created from a watched account event when the extraction identifies a possible market attention change.

### Event Cluster

One or more attention seeds or related extracted events that represent the same fact/attention coordinate. In V1, clustering can start with one event per cluster and later merge by `asset_hint + event_type + anchor_terms + time`.

### Snapshot

An immutable decision-time record containing the current market state, active event clusters, scores, policy/shadow decisions, and all config versions.

### Decision

A recorded policy or shadow action. V1 records shadow and paper decisions only. Live execution is out of scope.

### Outcome

Forward result for a snapshot after its horizon expires, measured as abnormal return.

### Credit

Fractional predictive credit assigned to event clusters in a snapshot. This is not a causal claim.

### Weight

Slowly updated explainable multiplier for source, event type, horizon, or source-event pair.

## New LLM Output Contract

### Contract Name

```text
social-event-v1
```

### Allowed Event Types

Initial enum:

```text
non_signal
meme_phrase_seed
token_direct_mention
product_or_ai_update
exchange_or_listing_hint
ecosystem_growth_claim
founder_reply_or_quote
policy_or_regulatory_comment
risk_warning
market_structure_comment
```

This is intentionally crypto-social, not generic news. It fits the current GMGN/X source and accounts like CZ/Musk/He Yi.

### Allowed Attention Mechanisms

```text
none
new_phrase
token_mention
product_association
exchange_attention
founder_amplification
controversy_or_risk
ecosystem_callout
reply_target_attention
```

### Direction Hint

```text
attention_positive
attention_negative
neutral
```

This is not price direction. It describes likely attention direction.

### Anchor Term Roles

```text
meme_phrase
token_symbol
project_name
person
product
ecosystem
exchange
risk_term
hashtag
url_domain
```

### JSON Shape

```json
{
  "schema_version": "social-event-v1",
  "is_signal_event": true,
  "event_type": "meme_phrase_seed",
  "source_action": "post",
  "subject": "CZ introduces a short repeatable BNB phrase",
  "direction_hint": "attention_positive",
  "attention_mechanism": "new_phrase",
  "impact_hint": 0.72,
  "semantic_novelty_hint": 0.68,
  "confidence": 0.86,
  "anchor_terms": [
    {
      "term": "exact substring",
      "role": "meme_phrase",
      "memeability_hint": 0.8,
      "evidence": "exact substring"
    }
  ],
  "token_candidates": [
    {
      "symbol": "BNB",
      "project_name": "BNB Chain",
      "chain": null,
      "address": null,
      "evidence": "$BNB",
      "confidence": 0.9
    }
  ],
  "semantic_risks": ["sarcasm_or_joke"],
  "summary_zh": "CZ 提到可传播的 BNB 短语，可能形成新的注意力种子。"
}
```

### Validation Rules

The parser must enforce:

- `schema_version` is stored as `social-event-v1`; invalid versions are rejected or downgraded to `non_signal`.
- `event_type`, `attention_mechanism`, `direction_hint`, `source_action`, anchor roles, and risk terms are enum-bound.
- `impact_hint`, `semantic_novelty_hint`, `confidence`, and `memeability_hint` are clamped to `[0, 1]`.
- every anchor `evidence` must be an exact substring of event text after whitespace normalization;
- every token candidate `evidence` must be an exact substring;
- token candidate without symbol/project/address is rejected;
- signal event with no valid anchor terms is downgraded to `non_signal`;
- LLM token candidates remain candidates, not tradable facts.

### Structured Output Mode

Use strict JSON schema response format for OpenAI calls where supported:

```python
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "social_event_extraction",
        "strict": True,
        "schema": {...}
    },
}
```

V1 should require strict schema support because downstream harness state depends on exact fields. If a configured provider cannot support this contract, the enrichment worker should fail that job explicitly instead of falling back to old JSON mode or accepting loose narrative payloads.

## Harness State Machine

The target state machine:

```text
RAW_EVENT_STORED
  -> WATCHED_EVENT_ENQUEUED
  -> SOCIAL_EVENT_EXTRACTED
  -> ATTENTION_SEED_CREATED
  -> EVENT_CLUSTERED
  -> SNAPSHOT_BUILT
  -> SIGNAL_SCORED
  -> DECISION_RECORDED
  -> OUTCOME_PENDING
  -> OUTCOME_SETTLED
  -> CREDIT_ATTRIBUTED
  -> WEIGHTS_UPDATED
  -> CONFIG_EVALUATED
```

Every transition writes SQLite state. Re-running a stage should be idempotent.

## Data Model

### `social_event_extractions`

Stores one LLM extraction per watched event.

```sql
CREATE TABLE IF NOT EXISTS social_event_extractions (
  extraction_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  run_id TEXT NOT NULL REFERENCES model_runs(run_id) ON DELETE CASCADE,
  schema_version TEXT NOT NULL,
  event_type TEXT NOT NULL,
  source_action TEXT NOT NULL,
  subject TEXT NOT NULL,
  direction_hint TEXT NOT NULL,
  attention_mechanism TEXT NOT NULL,
  impact_hint REAL NOT NULL,
  semantic_novelty_hint REAL NOT NULL,
  confidence REAL NOT NULL,
  is_signal_event INTEGER NOT NULL,
  anchor_terms_json TEXT NOT NULL DEFAULT '[]',
  token_candidates_json TEXT NOT NULL DEFAULT '[]',
  semantic_risks_json TEXT NOT NULL DEFAULT '[]',
  summary_zh TEXT NOT NULL DEFAULT '',
  raw_response_json TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL,
  author_handle TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);
```

Indexes:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_social_event_extractions_event
  ON social_event_extractions(event_id);
CREATE INDEX IF NOT EXISTS idx_social_event_extractions_type_received
  ON social_event_extractions(event_type, received_at_ms);
CREATE INDEX IF NOT EXISTS idx_social_event_extractions_author_received
  ON social_event_extractions(author_handle, received_at_ms);
```

### `event_clusters`

V1 can start as one extraction equals one cluster. The schema should support later clustering.

```sql
CREATE TABLE IF NOT EXISTS event_clusters (
  cluster_id TEXT PRIMARY KEY,
  asset TEXT NOT NULL,
  event_type TEXT NOT NULL,
  direction INTEGER NOT NULL,
  first_seen_at_ms INTEGER NOT NULL,
  last_seen_at_ms INTEGER NOT NULL,
  impact REAL NOT NULL,
  confidence REAL NOT NULL,
  novelty REAL NOT NULL,
  pricedness REAL NOT NULL,
  base_score REAL NOT NULL,
  event_score REAL NOT NULL,
  source_list_json TEXT NOT NULL DEFAULT '[]',
  extraction_ids_json TEXT NOT NULL DEFAULT '[]',
  anchor_terms_json TEXT NOT NULL DEFAULT '[]',
  representative_text TEXT NOT NULL DEFAULT '',
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);
```

Asset can be:

- resolved token ID;
- chain/address token identity;
- major asset like `BTC`, `ETH`, `BNB`, `SOL`;
- `UNKNOWN` if no deterministic expression exists yet.

Clusters with `UNKNOWN` can be tracked but cannot produce tradable driver decisions.

### `harness_snapshots`

Immutable decision-time record.

```sql
CREATE TABLE IF NOT EXISTS harness_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  asset TEXT NOT NULL,
  decision_time_ms INTEGER NOT NULL,
  horizon TEXT NOT NULL,
  combined_score REAL NOT NULL,
  policy_signal TEXT NOT NULL,
  shadow_signal TEXT NOT NULL,
  market_state_json TEXT NOT NULL DEFAULT '{}',
  event_clusters_json TEXT NOT NULL DEFAULT '[]',
  config_version TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  scoring_version TEXT NOT NULL,
  weight_version TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  risk_version TEXT NOT NULL,
  baseline_version TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);
```

### `harness_decisions`

Records shadow/paper/live decision attempts.

```sql
CREATE TABLE IF NOT EXISTS harness_decisions (
  decision_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL REFERENCES harness_snapshots(snapshot_id) ON DELETE CASCADE,
  asset TEXT NOT NULL,
  decision_time_ms INTEGER NOT NULL,
  execution_mode TEXT NOT NULL,
  signal TEXT NOT NULL,
  side TEXT NOT NULL,
  size REAL NOT NULL,
  entry_price REAL,
  risk_reject_reason TEXT,
  order_id TEXT,
  created_at_ms INTEGER NOT NULL
);
```

V1 uses `shadow` and optionally `paper`. Live stays disabled.

### `harness_outcomes`

Settlement result.

```sql
CREATE TABLE IF NOT EXISTS harness_outcomes (
  snapshot_id TEXT PRIMARY KEY REFERENCES harness_snapshots(snapshot_id) ON DELETE CASCADE,
  settled_at_ms INTEGER NOT NULL,
  actual_return REAL NOT NULL,
  expected_return REAL NOT NULL,
  abnormal_return REAL NOT NULL,
  realized_vol REAL NOT NULL,
  normalized_outcome REAL NOT NULL,
  fees REAL NOT NULL DEFAULT 0,
  slippage REAL NOT NULL DEFAULT 0,
  baseline_version TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);
```

### `harness_credits`

Multi-event credit rows.

```sql
CREATE TABLE IF NOT EXISTS harness_credits (
  credit_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL REFERENCES harness_snapshots(snapshot_id) ON DELETE CASCADE,
  cluster_id TEXT NOT NULL,
  asset TEXT NOT NULL,
  event_type TEXT NOT NULL,
  source TEXT NOT NULL,
  horizon TEXT NOT NULL,
  event_score REAL NOT NULL,
  responsibility REAL NOT NULL,
  credit REAL NOT NULL,
  created_at_ms INTEGER NOT NULL
);
```

### `harness_weights`

Slow explainable weights.

```sql
CREATE TABLE IF NOT EXISTS harness_weights (
  weight_key TEXT PRIMARY KEY,
  weight_type TEXT NOT NULL,
  asset TEXT,
  horizon TEXT NOT NULL,
  n INTEGER NOT NULL,
  mean_credit REAL NOT NULL,
  weight REAL NOT NULL,
  updated_at_ms INTEGER NOT NULL
);
```

Weight types:

```text
source
event_type
horizon
source_event_type
asset_event_type
```

## Scoring Design

### Base Event Score

For a cluster:

```text
base_score =
direction
× impact
× confidence
× novelty
× (1 - pricedness)
```

Mapping:

- `direction`: `+1`, `0`, `-1`
- `impact`: from LLM `impact_hint`, clamped and optionally capped by source rules
- `confidence`: extraction confidence
- `novelty`: harness-computed when possible, LLM `semantic_novelty_hint` as initial hint
- `pricedness`: harness-computed from pre-move; LLM does not own final pricedness

### Weighted Event Score

```text
event_score =
base_score
× source_weight
× event_type_weight
× horizon_weight
× time_decay
× price_move_penalty
```

### Source Weight

Initial source weights:

```text
configured watched account: 1.0
high-value configured source override: 1.1 to 1.3
unknown/unconfigured source: cannot create seed
```

V1 can avoid config complexity by deriving from watched handle and follower count. V2 can add explicit source tiers for `cz`, `elonmusk`, `heyibinance`, etc.

### Price Move Penalty

This solves stale-news and "price already moved" failure.

```text
pre_move = asset return in 30m before seed
recent_vol = realized vol in prior window

if abs(pre_move) > 1.5 * recent_vol:
    pricedness = max(pricedness, 0.75)
```

or:

```text
price_move_penalty = max(0.2, 1 - abs(pre_move) / volatility_threshold)
```

V1 can store missing market state and mark risk `market_baseline_missing`. Missing price data should block driver decisions, not block extraction.

### Combined Score

For one asset/horizon snapshot:

```text
combined_score = sum(event_score_i)
```

Caps:

- unresolved token identity caps driver;
- no market snapshot caps driver;
- author concentration caps high scores;
- stale market caps high scores;
- public-stream coverage risk is always present;
- price pre-move risk caps or rejects.

### Policy and Shadow

Suggested V1:

```text
policy live: disabled
paper long threshold: +0.70
paper short threshold: -0.70
shadow long threshold: +0.35
shadow short threshold: -0.35
```

Signals:

```text
LONG
SHORT_OR_AVOID
NO_TRADE
```

Execution modes:

```text
shadow
paper
canary_live
live
```

V1 records shadow only by default.

## Settlement

The outcome target is not raw return. It is abnormal return.

### Actual Return

```text
actual_return =
forward_price(asset, decision_time + horizon) / price(asset, decision_time) - 1
```

### Expected Return

Minimal crypto baseline:

```text
expected_return =
  0.5 * ETH_return
+ 0.3 * crypto_index_return
+ 0.2 * asset_recent_momentum
```

If no crypto index exists locally, V1 can use:

```text
expected_return =
  0.6 * BTC_or_ETH_benchmark_return
+ 0.4 * asset_recent_momentum
```

For BNB-related signals, benchmark should prefer BNB/major market when available.

### Normalized Outcome

```text
abnormal_return = actual_return - expected_return
y = abnormal_return / max(realized_vol, 1e-6)
y = clip(y, -1, 1)
```

This `y` becomes the learning target.

## Credit Assignment

Multiple events may exist in the same snapshot.

Responsibility:

```text
rho_i = abs(event_score_i) / sum(abs(event_score_j))
```

Credit:

```text
credit_i = rho_i * sign(event_score_i) * normalized_outcome
```

This means:

- positive event and positive abnormal return -> positive credit;
- negative event and positive abnormal return -> negative credit;
- stronger event scores receive more responsibility;
- no single event is declared "the cause".

## Weight Updates

Update only explainable weights:

- source weight;
- event type weight;
- horizon weight;
- source-event type weight;
- asset-event type weight.

Do not update:

- LLM model weights;
- one-off manual event weights;
- historical snapshots;
- settled outcomes.

Formula:

```text
mean_credit_new =
mean_credit_old + (credit - mean_credit_old) / n

shrunk_effect =
n / (n + n0) * mean_credit

weight =
clip(1 + lambda * shrunk_effect, 0.5, 1.5)
```

Suggested:

```text
n0 = 50
lambda = 0.5
```

## Evaluation

The most important daily table:

```text
combined_score bucket        avg abnormal return
------------------------------------------------
score <= -0.8                should be negative
-0.8 ~ -0.4                  less negative
-0.4 ~ 0.4                   near zero
0.4 ~ 0.8                    positive
score >= 0.8                 more positive
```

Promotion requires:

- score bucket monotonicity improves;
- average abnormal return improves;
- cost-adjusted shadow/paper PnL improves;
- max drawdown does not worsen materially;
- turnover remains acceptable;
- rejection rate is explainable;
- sample size is sufficient.

## Runtime Loops

### Online Loop

```text
watched event arrives
  -> enqueue LLM extraction
  -> validate structured output
  -> store social_event_extraction
  -> create attention seed
  -> update/insert event cluster
  -> build shadow snapshot
  -> score
  -> record shadow decision
```

### Link Validation Loop

Existing `narrative_token_linker.py` logic should be retained and adapted:

```text
attention seed
  -> scan post-seed event_token_mentions
  -> match seed terms / symbols / direct CA
  -> score diffusion and tradeability
  -> attach token-link evidence
```

### Settlement Loop

```text
due snapshots
  -> load forward market data
  -> compute actual return
  -> compute expected return
  -> compute abnormal return
  -> write outcome
```

### Learning Loop

```text
unprocessed credits
  -> update weight stats
  -> write candidate weight version
  -> do not auto-promote live config
```

## Migration Strategy

This should be a controlled destructive semantic migration, not an additive compatibility migration.

### Migration Principle

The new harness model replaces the old narrative model. Do not maintain old and new product semantics side by side.

### Storage Migration

Recommended path:

```text
bump schema version
-> create new harness tables
-> remove old narrative product tables from APP_TABLES if no longer used
-> clear/rebuild application tables on schema mismatch according to existing repo practice
-> preserve raw evidence only where the schema already preserves it
```

The safest production interpretation is:

```text
old narrative rows are historical artifacts
new social-event rows are produced only by the new extractor
```

No old row should be silently upgraded without re-running the new prompt and recording new versions.

### Code Migration

Remove or replace:

- `llm_enrichment.py` narrative parser as the primary contract;
- old `NarrativeItem`-dependent worker paths;
- old narrative window materialization as a product path;
- old narrative display fallback in retrieval/API/UI;
- tests that assert old LLM payloads are accepted.

Keep and adapt:

- watched enrichment job queue;
- model run audit records;
- deterministic entity/token extraction;
- token-linking logic if rewritten around attention seeds;
- store-first ingest.

### Product Migration

The primary product view becomes:

```text
Attention Seeds
Attention Frontier
Shadow Snapshots
Outcome/Credit Reports
Weight Drift
```

Old `narrative-flow` should be removed or rebuilt as an alias only if it returns the new social-event/harness model. Do not keep old snake_case narrative labels as the trader-facing view.

## API And CLI Surface

V1 should add read-only surfaces:

```text
gmgn-twitter-intel social-events --window 24h --limit 50
gmgn-twitter-intel harness-snapshots --window 24h --limit 50
gmgn-twitter-intel harness-outcomes --window 7d --limit 100
gmgn-twitter-intel harness-credits --window 7d --limit 100
gmgn-twitter-intel harness-weights --limit 100
gmgn-twitter-intel ops settle-harness --horizon 6h
gmgn-twitter-intel ops update-harness-weights
```

HTTP equivalents:

```text
/api/social-events
/api/harness-snapshots
/api/harness-outcomes
/api/harness-credits
/api/harness-weights
```

No write API for live trading in V1.

## Impact Assessment

### Summary

This change trades short-term compatibility for long-term measurement. The immediate cost is higher because consumers of old narrative payloads must move. The strategic benefit is that every signal becomes testable against future abnormal return.

The expected net effect is:

```text
less narrative readability
more signal auditability
less LLM discretion
more harness accountability
less backward compatibility
more ability to learn whether the system has edge
```

### Product Impact

Expected improvement:

- narrative flow becomes evidence-backed attention seed flow;
- high-value account events become inspectable hypotheses;
- token links explain how attention became tradable;
- users can see why a signal was shadowed, rejected, or watched;
- system can answer whether it is improving over time.

Most important new user questions answered:

```text
What did CZ/Musk/He Yi just create as an attention seed?
Which exact words anchor the seed?
Which tokens picked it up after the seed?
Was this before or after price movement?
Did similar seeds work historically?
Which sources/types/horizons are earning positive credit?
```

Breaking product effects:

- old narrative flow screens will need replacement;
- old Chinese narrative display fallback should disappear;
- users may initially see fewer "signals" because non-settled story-only items are no longer promoted;
- product vocabulary changes from narrative labels to extracted events, attention seeds, snapshots, outcomes, and credits;
- historical narrative rows will not automatically show in the new harness views.

Desired product behavior after migration:

- a watched CZ/Musk/He Yi post first appears as a social event extraction;
- if it has an anchor term, it becomes an attention seed;
- if token uptake appears, it moves into attention frontier;
- if a snapshot is scored, it gets a shadow decision;
- after horizon expiry, it gets an outcome and credit rows.

### Trading Impact

Expected improvement:

- fewer story-only signals;
- stronger stale-news filtering;
- better separation of semantic novelty and tradability;
- measurable score-to-abnormal-return relationship;
- safer iteration through shadow/paper.

Primary success metric:

```text
combined_score bucket monotonicity vs future normalized abnormal return
```

Secondary metrics:

- hit rate by horizon;
- average abnormal return by event type;
- source credit distribution;
- rejection reason distribution;
- shadow PnL after estimated costs;
- max drawdown;
- latency from watched event to extraction.

Expected negative or neutral effects:

- live signal count may drop materially because unresolved story-only narratives no longer qualify;
- early shadow PnL may look worse because the system is now measuring abnormal return instead of cherry-picked raw moves;
- some previously exciting meme phrases will remain "attention only" until deterministic token uptake exists;
- score bucket reports may reveal no edge in some event types, which is a useful but uncomfortable result.

Trading risk reduction:

- lower risk of buying LLM-inferred tickers;
- lower risk of stale news chasing because price-move penalty is explicit;
- lower risk of overfitting single events because credit updates are slow and shrinkage-protected;
- lower risk of false confidence because shadow/paper/live are separated.

### Engineering Impact

Benefits:

- explicit LLM schema reduces parser fragility;
- SQLite state machine improves auditability;
- pure scoring/settlement modules are easy to test;
- current deterministic ingest path remains intact;
- no new external source dependency in V1.

Costs:

- several new tables;
- more CLI/API surfaces;
- more operational jobs for settlement and weights;
- migration from narrative-first mental model to harness-first mental model.

Breaking engineering effects:

- tests for old JSON mode narrative output must be replaced;
- any code depending on `EnrichmentResult.narratives` as product truth must be rewritten;
- old retrieval services that expose narrative windows need removal or semantic rewrite;
- cockpit types for narrative display must be replaced;
- API consumers of narrative/enrichment payloads must update.

Complexity increase:

- new schema version and more tables;
- new pure scoring and settlement modules;
- new repository for harness state;
- new CLI ops for settlement/credit/weights;
- new evaluation read models.

Complexity decrease:

- no dual-contract parser;
- no legacy fallback fields;
- no ambiguous "narrative as signal" path;
- fewer places where LLM output is treated as trader-facing truth.

### Operational Impact

New recurring operations:

- settle due snapshots;
- attribute credits;
- update weights;
- review score bucket reports;
- evaluate candidate config before promotion.

These can start as manual CLI commands and become scheduled jobs later.

Operational costs:

- operators must monitor schema success rate;
- settlement requires sufficient market snapshots;
- score bucket reports need regular review;
- candidate weights/configs need promotion discipline;
- old runtime databases may need destructive rebuild or explicit replay.

Operational benefits:

- every decision has a frozen snapshot;
- every loss can be decomposed into extraction, scoring, market baseline, risk gate, or execution-mode issues;
- prompt/schema/scoring/config versions become auditable;
- learning is slower but much safer.

### Data Impact

New durable facts:

- social event extractions;
- event clusters;
- snapshots;
- decisions;
- outcomes;
- credits;
- weights.

Data deliberately not migrated:

- old narrative windows into new score buckets;
- old narrative labels into event clusters;
- old market interpretations into social event subjects;
- old enrichment rows into strict schema outputs.

Historical analysis remains possible only by replaying original stored events through the new extractor and recording new model/prompt/schema versions.

### API Impact

Breaking changes are expected for narrative/enrichment surfaces.

Endpoints likely removed or rewritten:

- `/api/narrative-flow`;
- `/api/account-narratives`;
- WebSocket `enrichment_update` narrative payload;
- cockpit narrative panels.

Endpoints likely preserved because they are factual:

- `/api/recent`;
- `/api/search`;
- `/api/token-flow`, if its response does not depend on old narrative fields;
- `/api/token-posts`;
- `/api/token-social-timeline`;
- `/api/attention-frontier`, if rewritten over attention seeds/harness links.

### User Impact

Users lose:

- broad narrative labels that are easy to read but not measurable;
- historical narrative continuity without replay;
- some UI convenience during migration.

Users gain:

- clear attention seed evidence;
- explicit reasons a seed is or is not tradable;
- visible shadow decisions;
- post-horizon outcome and credit;
- source/event/horizon learning reports.

### Implementation Impact Matrix

| Area | Change | Compatibility Position | Expected Effect |
| --- | --- | --- | --- |
| LLM contract | Replace narrative JSON with `social-event-v1` | No compatibility parser | Less hallucination surface, more strict failures |
| Enrichment worker | Persist social extraction and harness state | Rewrite old narrative materialization | Turns watched events into replayable hypotheses |
| Storage | Add harness tables, remove old semantic dependency | Destructive semantic migration | More auditability, more migration work |
| Retrieval/API | New harness reports | Old narrative endpoints rewritten or removed | Product shifts from stories to measurable signals |
| UI | New attention/harness views | No fallback to narrative labels | Less clutter, clearer decision chain |
| Ops | Add settlement/credit/weight commands | No old-row reinterpretation | Enables real closed-loop learning |
| Tests | Replace old narrative contract tests | Old payload acceptance tests removed | Test suite enforces new semantics |

## Risks And Mitigations

### Risk: LLM still over-interprets jokes

Mitigation:

- evidence substring requirement;
- enum-bound semantic risks;
- low confidence downgrade;
- harness never accepts LLM trade decisions.

### Risk: Token mapping creates false tradability

Mitigation:

- unresolved symbols cannot become driver;
- direct CA/resolved token identity required for high tradeability;
- token link stores identity status and risks.

### Risk: Sparse market data weakens settlement

Mitigation:

- store `market_baseline_missing`;
- block driver decisions when market data is absent;
- allow shadow-only outcomes with lower confidence;
- improve market snapshot coverage later.

### Risk: Too many tables before proof

Mitigation:

- make schema changes explicit and staged, but do not dual-run old narrative semantics;
- keep loops CLI/manual first;
- implement pure math modules before UI work.

### Risk: Credit assignment is mistaken as causality

Mitigation:

- docs and field names use `credit`, not `cause`;
- all credit is snapshot-relative;
- dashboard reports sample size and confidence.

## Open Decisions

1. Source tiers:
   - V1 can derive source weight from watched status/followers.
   - V2 may add explicit config for `cz`, `elonmusk`, `heyibinance`, etc.

2. Asset expression:
   - V1 can produce snapshots only for deterministic token/major asset expressions.
   - Unknown/meme-only seeds remain attention seeds until token uptake appears.

3. Settlement benchmark:
   - V1 should use available token market snapshots and a simple BTC/ETH/momentum baseline.
   - Better crypto index baseline can be added later.

4. UI:
   - V1 backend/CLI first.
   - UI follows after score/outcome reports are useful.

## Recommended Implementation Path

Use four stages:

1. **Contract and storage:** strict social-event extraction and harness tables.
2. **Scoring and snapshot:** deterministic score, snapshot, shadow decision.
3. **Settlement and learning:** outcome, credit, weights, reports.
4. **Product surfaces:** CLI/API reports, then cockpit UI.

Do not start with UI. Do not start with external sources. Do not start with live trading.
