# Watched Handle Narrative Token Linking Spec

Date: 2026-05-03

## First Principles

The core product problem is not only token detection. For accounts such as CZ or Musk, the market often reacts to a phrase, product idea, social theme, or meme-able opinion before a tradable token is explicitly mentioned. The useful signal is therefore a causal chain:

```text
watched handle statement
  -> narrative seed
  -> public-stream uptake
  -> linked token candidates
  -> tradable token evidence
  -> trader decision
```

The system should distinguish two roles:

- **Watched handles create attention seeds.** Only configured `handles` can create narrative seeds. This keeps cost, latency, and false-positive risk bounded.
- **The full public stream validates uptake.** All stored GMGN public-stream events remain useful evidence for deciding whether a watched-handle seed is being picked up by market participants.

This separation is the design guardrail. LLM enrichment must not move into the full-stream hot path, and full-stream monitoring must not depend on LLM availability.

## Current Architecture Review

The current repository already has most of the base:

1. `collector/direct_ws.py` receives GMGN anonymous public Twitter frames.
2. `collector/normalizer.py` turns frames into stable `TwitterEvent` records.
3. `collector/service.py` matches configured watched handles and publishes store-first events.
4. `pipeline/ingest_service.py` transactionally persists evidence, entities, token mentions, token windows, and watched-account enrichment jobs.
5. `pipeline/entity_extractor.py` deterministically extracts CA, cashtag, hashtag, mention, URL, and domain entities.
6. `pipeline/token_identity_resolver.py` maps CA and symbol entities into token identities or unresolved symbols.
7. `pipeline/signal_builder.py` writes `event_token_mentions`, account token alerts, and token windows.
8. `pipeline/enrichment_worker.py` asynchronously processes watched-account LLM jobs.
9. `pipeline/llm_enrichment.py` parses evidence-bound token candidates and narrative items.
10. `storage/enrichment_repository.py` stores event enrichments, event narratives, watched-account narrative alerts, and narrative windows.
11. `retrieval/token_flow_service.py` already builds trader-grade token flow with identity, market, flow, source, freshness, signal, and evidence blocks.
12. `retrieval/narrative_service.py` exposes current narrative windows and account narratives.
13. `api/http.py`, `api/ws.py`, `cli.py`, and the React cockpit expose token flow, narrative flow, account alerts, and enrichment status.

The important current invariant is already correct:

```python
if is_watched and _event_text(event):
    enrichment_job_id = self.enrichment.enqueue_watched_event(...)
```

That means full-stream ingest, deterministic entity extraction, token identity resolution, and token-flow materialization continue without LLM. The new feature should preserve this invariant.

## Gap

Current narrative support is event-level and window-level:

- `event_narratives` says what a watched account event was about.
- `account_narrative_alerts` says a watched account produced a narrative alert.
- `narrative_windows` says a narrative label has activity over fixed buckets.
- `event_token_candidates` stores LLM token candidates for the same watched event.

What is missing is the bridge from a watched-handle narrative seed to later public-stream token activity:

```text
CZ says a theme without a token
  -> system records a seed
  -> public stream later mentions symbols/CAs/projects around that theme
  -> system links those token mentions back to the seed
  -> trader sees which tokens are consuming the seed's attention
```

Without that bridge, the product can show "narrative flow" and "token flow" side by side, but it cannot answer the more valuable question: **which tokens are being pulled by this watched-handle narrative?**

## Design Thesis

Add a new bounded context: **Narrative Token Linking**.

This context does not replace current token flow or narrative enrichment. It joins them with auditable evidence and scoring.

### Responsibilities

- Turn watched-account event narratives into durable narrative seeds.
- Search deterministic full-stream token mentions after the seed timestamp.
- Link tokens to seeds using evidence-bound lexical and entity signals.
- Score seed strength, public uptake, token-link quality, and tradeability.
- Expose trader-ready views that start from narrative seeds and drill into linked tokens.

### Non-Responsibilities

- It does not claim full Twitter coverage.
- It does not call LLM on every public-stream event.
- It does not make LLM-inferred tokens tradable facts.
- It does not perform automatic trading.
- It does not require embeddings in the first version.
- It does not demote or remove existing `token-flow`.

## Data Model

### `narrative_seeds`

Durable seed produced only from watched-handle enrichments.

```sql
CREATE TABLE IF NOT EXISTS narrative_seeds (
  seed_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  narrative_label TEXT NOT NULL,
  seed_family TEXT,
  seed_terms_json TEXT NOT NULL DEFAULT '[]',
  market_interpretation TEXT NOT NULL DEFAULT '',
  stance TEXT NOT NULL,
  intent TEXT NOT NULL,
  confidence REAL NOT NULL,
  source_weight REAL NOT NULL,
  novelty_status TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL,
  author_handle TEXT NOT NULL,
  evidence TEXT NOT NULL,
  summary TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_narrative_seeds_event_label
  ON narrative_seeds(event_id, narrative_label);
CREATE INDEX IF NOT EXISTS idx_narrative_seeds_received
  ON narrative_seeds(received_at_ms);
CREATE INDEX IF NOT EXISTS idx_narrative_seeds_label_received
  ON narrative_seeds(narrative_label, received_at_ms);
```

Field notes:

- `seed_family` is a broader grouping such as `ai_agent`, `bnb_chain`, `doge_meme`, `stablecoin`, `privacy`, or `robotics`.
- `seed_terms_json` stores normalized terms derived from evidence-bound narrative text, deterministic entities, and LLM output. These terms are used for lexical matching.
- `market_interpretation` is a short explanation of how the market may interpret the watched-handle statement. It must be evidence-bound to the event.
- `source_weight` should be configuration-light in v1: watched handles are the only seed sources, and the score can be derived from watched status plus available follower count. No separate social-tier config is required for the first version.
- `novelty_status` is `new_global`, `new_author`, or `repeat`.

### `narrative_token_links`

Evidence-bound link between a seed and a token identity observed after that seed.

```sql
CREATE TABLE IF NOT EXISTS narrative_token_links (
  link_id TEXT PRIMARY KEY,
  seed_id TEXT NOT NULL REFERENCES narrative_seeds(seed_id) ON DELETE CASCADE,
  narrative_label TEXT NOT NULL,
  token_identity_key TEXT NOT NULL,
  token_id TEXT,
  identity_status TEXT NOT NULL,
  chain TEXT,
  address TEXT,
  symbol TEXT NOT NULL,
  first_linked_event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  best_evidence_event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  link_reason TEXT NOT NULL,
  matched_terms_json TEXT NOT NULL DEFAULT '[]',
  link_confidence REAL NOT NULL,
  lag_ms INTEGER NOT NULL,
  window TEXT NOT NULL,
  mention_count_after_seed INTEGER NOT NULL,
  watched_mention_count_after_seed INTEGER NOT NULL,
  unique_author_count_after_seed INTEGER NOT NULL,
  weighted_reach_after_seed REAL NOT NULL,
  market_cap REAL,
  market_status TEXT NOT NULL,
  price_change_after_seed_pct REAL,
  seed_score INTEGER NOT NULL,
  diffusion_score INTEGER NOT NULL,
  token_link_score INTEGER NOT NULL,
  tradeability_score INTEGER NOT NULL,
  decision TEXT NOT NULL,
  reasons_json TEXT NOT NULL DEFAULT '[]',
  risks_json TEXT NOT NULL DEFAULT '[]',
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_narrative_token_links_seed_token_window
  ON narrative_token_links(seed_id, token_identity_key, window);
CREATE INDEX IF NOT EXISTS idx_narrative_token_links_label_decision
  ON narrative_token_links(narrative_label, decision, updated_at_ms);
CREATE INDEX IF NOT EXISTS idx_narrative_token_links_token
  ON narrative_token_links(token_identity_key, updated_at_ms);
```

Field notes:

- `token_identity_key` reuses the existing token identity model: resolved CA tokens stay precise; unresolved symbols stay risky.
- `first_linked_event_id` is the first event after the seed that created the link.
- `best_evidence_event_id` is the strongest evidence event after scoring.
- `lag_ms` is measured from seed `received_at_ms` to first linked token evidence.
- `window` starts with `1h` as the main product window, with `5m` and `24h` useful for fast/slow views.

### Optional Later Table: `narrative_link_windows`

The first version can compute link views directly from `event_token_mentions` and store only `narrative_token_links`. If query cost grows, add materialized link windows:

```text
narrative_label
seed_id
token_identity_key
window
window_start_ms
window_end_ms
mention_count
unique_author_count
top_authors_json
top_events_json
```

Do not add this table until there is a measured query or rebuild need.

## LLM Output Contract

Current `NarrativeItem` has:

```text
label
description
evidence
confidence
```

The seed-aware contract replaces narrative output with an explicit seed shape:

```json
{
  "narratives": [
    {
      "label": "ai_agent_grok",
      "description": "Grok product progress as an AI-agent attention seed",
      "seed_family": "ai_agent",
      "trigger_terms": ["grok", "ai agent", "xai"],
      "market_interpretation": "Market may look for Grok, xAI, or AI-agent themed tokens.",
      "evidence": "Grok is getting scary good",
      "confidence": 0.86
    }
  ]
}
```

Validation rules:

- `evidence` must be a substring of the event text or referenced text.
- `label` is normalized to snake case.
- `trigger_terms` are lowercased, deduplicated, and capped.
- `trigger_terms` must appear in the watched event text; ungrounded expansion terms are rejected instead of stored.
- No hidden ticker inference. If the watched event does not mention `$TOKEN` or CA, the model may describe market interpretation, but the linker must wait for public-stream evidence before creating token links.

## Linking Algorithm

The first version should be deterministic after seed creation.

### Candidate Scope

For each seed:

```text
start_ms = seed.received_at_ms
end_ms = seed.received_at_ms + selected_window_ms
source = all event_token_mentions in [start_ms, end_ms)
```

Use the full stored public stream for candidate mentions. Do not require the candidate event author to be watched.

### Candidate Evidence Sources

Primary:

- `event_token_mentions`: symbol, CA, identity status, token ID, source event.
- `events.text_clean` / `events.search_text`: text containing narrative terms.
- `tokens` and `token_aliases`: resolved identity metadata.
- `token_market_snapshots`: market cap, price, market freshness.

Secondary:

- `event_entities`: hashtag, mention, URL/domain matching around the seed terms.
- `event_token_candidates`: LLM candidates on the watched seed event, useful only as weak prior evidence unless later confirmed by full-stream token mentions.

### Link Reasons

Allowed `link_reason` values:

- `seed_term_and_token_mention`: candidate event contains seed terms and token mention.
- `seed_symbol_candidate_confirmed`: seed event had an LLM token candidate and later public stream confirmed the same symbol/CA.
- `name_or_alias_overlap`: token symbol/name/alias overlaps seed terms.
- `watched_seed_direct_token`: watched seed itself explicitly mentioned the token.

Disallowed in v1:

- Pure semantic similarity without lexical/entity evidence.
- Linking only because a token is generally in the same sector.
- Linking an ambiguous symbol as high-confidence tradeable evidence.

### Scoring

Scores are integer `0..100`. Keep scoring in a dedicated module, not in repository code.

#### `seed_score`

Measures whether the watched event is a strong attention source.

Inputs:

- watched handle status, always required.
- event recency.
- author followers when available.
- narrative confidence.
- stance/intent.
- novelty status.

Suggested scoring:

```text
+30 watched_handle_seed
+10 author_followers_present
+10 confidence >= 0.75
+10 intent in product/macro/meme/technical commentary
+10 novelty_status in new_global/new_author
-15 repeat seed within same author and 24h
clamp 0..100
```

#### `diffusion_score`

Measures whether the public stream picked up the seed.

Inputs:

- post-seed mention count.
- unique author count.
- watched mention count after seed.
- mention delta vs previous equivalent window.
- top author concentration.
- weighted reach as weak secondary signal.

This can reuse concepts from `token_signal_scoring.source_quality`.

#### `token_link_score`

Measures whether the token is actually about the seed.

Inputs:

- matched seed terms in token evidence text.
- CA vs symbol specificity.
- LLM token candidate confirmation.
- alias/name overlap.
- lag from seed to first token evidence.
- repeated evidence across independent authors.

Resolved CA links can score higher. Unresolved symbols should stay watch/discard unless later resolved.

#### `tradeability_score`

Measures whether the linked token is usable in the trader radar.

Inputs:

- existing `TokenFlowService` market block.
- market freshness.
- market cap presence.
- price change after seed when available.
- identity status.
- source concentration risk.

Reuse existing token-flow risk language where possible:

- `resolved_ca`
- `resolved_alias`
- `unresolved_symbol`
- `ambiguous_symbol`
- `market_missing`
- `market_stale`
- `author_concentration_high`

### Decision

`decision` is derived from the four scores and hard risk gates:

```text
discard:
  unresolved_symbol with no market data
  market_missing for a claimed tradeable link
  only one non-watched low-quality source and no seed-term evidence

driver:
  strong seed_score
  strong token_link_score
  resolved_ca or resolved_alias
  fresh market data
  public-stream diffusion beyond a single concentrated author

watch:
  everything else with evidence
```

The decision is explanatory, not an execution instruction.

## Retrieval Views

### `narrative-seeds`

Primary question: what watched handles just said that can become market attention?

Response shape:

```json
{
  "seed": {
    "seed_id": "...",
    "narrative_label": "ai_agent_grok",
    "seed_family": "ai_agent",
    "author_handle": "elonmusk",
    "received_at_ms": 1777770000000,
    "evidence": "Grok is getting scary good",
    "summary": "...",
    "seed_score": 72
  },
  "linked_token_count": 3,
  "top_decision": "driver"
}
```

### `narrative-token-flow`

Primary question: which tokens are consuming a watched-handle seed?

Response shape:

```json
{
  "seed": {},
  "links": [
    {
      "identity": {},
      "market": {},
      "flow": {},
      "scores": {
        "seed": 72,
        "diffusion": 61,
        "token_link": 80,
        "tradeability": 74
      },
      "signal": {
        "decision": "watch",
        "reasons": ["watched_handle_seed", "seed_term_and_token_mention"],
        "risks": ["coverage_public_stream"]
      },
      "evidence": []
    }
  ]
}
```

### `attention-frontier`

Primary question: what changed now?

This view ranks recent narrative seeds and linked tokens together:

```text
fresh watched-handle seed
  + first linked CA
  + token acceleration
  + market-cap availability
  + evidence recency
```

This should become the cockpit's narrative-first panel once the backend is stable.

## API and CLI Surface

Add HTTP endpoints:

- `GET /api/narrative-seeds?window=24h&limit=50&handles=cz,elonmusk`
- `GET /api/narrative-token-flow?seed_id=...&window=1h&limit=20`
- `GET /api/attention-frontier?window=1h&limit=30`

Add CLI commands:

```bash
uv run gmgn-twitter-intel narrative-seeds --window 24h --limit 50
uv run gmgn-twitter-intel narrative-token-flow --seed-id <seed_id> --window 1h --limit 20
uv run gmgn-twitter-intel attention-frontier --window 1h --limit 30
```

Keep existing commands:

```bash
uv run gmgn-twitter-intel token-flow --window 5m --limit 20
uv run gmgn-twitter-intel narrative-flow --window 1h --limit 20
uv run gmgn-twitter-intel account-narratives --window 24h --limit 50
```

The new commands complement existing surfaces. They do not replace `token-flow`.

## WebSocket Behavior

Existing event payload shape remains stable; the new feature adds a separate update type:

```json
{
  "type": "event",
  "event": {},
  "entities": [],
  "alerts": [],
  "enrichment": null
}
```

Add a new update payload after narrative linking commits:

```json
{
  "type": "narrative_link_update",
  "seed": {},
  "links": []
}
```

Subscription matching remains event/handle/token based for v1. Narrative subscriptions can be added later if the cockpit needs them.

## Cockpit Impact

Current cockpit can remain token-first:

- Token Flow remains the main radar.
- Narrative Flow remains the side panel.
- Account alerts remain unchanged.

Add narrative linking in two incremental UI steps:

1. Add narrative badges to token rows when a token has an active `narrative_token_link`.
2. Add a Narrative Frontier panel that starts from watched-handle seeds and expands into linked tokens.

The UI must not imply that LLM produced a tradable token. Copy should show:

- seed evidence from watched handle.
- link evidence from full stream.
- token identity status.
- market data status.
- reasons and risks.

## Impact on Full Monitoring

Full monitoring remains an input and is not degraded:

```text
full public stream
  -> raw/evidence persistence
  -> deterministic entities
  -> token mentions
  -> token flow
  -> optional use as post-seed link evidence
```

No full-stream event should enqueue an LLM job unless it matches configured watched handles. If the LLM provider is unavailable:

- `recent` still works.
- `search` still works.
- `token-flow` still works.
- `account-alerts` still works for deterministic token mentions.
- narrative seeds and narrative links stop updating until enrichment recovers.

Operationally, the new feature adds read/query work and post-enrichment write work, not hot-path LLM work.

## Rollout Strategy

1. Add tables and read models behind new APIs.
2. Keep existing narrative and token APIs as separate product surfaces while adding new seed/link APIs.
3. Run linker only from enrichment worker after watched-event enrichment completes.
4. Add an explicit ops rebuild command for historical backfill.
5. Add cockpit badges after backend snapshots are stable.
6. Promote Narrative Frontier to a primary UI panel only after live data validates the scoring.

## Risks

### False Causality

The public stream may mention a token after a watched-handle seed for unrelated reasons. Mitigation: require evidence terms, author dispersion, and explicit link reasons.

### LLM Overreach

The model may produce broad trigger terms. Mitigation: evidence-bound validation, rejection of terms not present in event text, and no pure semantic linking in v1.

### Symbol Ambiguity

Multiple tokens can share the same ticker. Mitigation: keep unresolved or ambiguous symbols downgraded until resolved CA or unique alias evidence exists.

### Query Cost

Scanning post-seed token mentions can grow expensive. Mitigation: start with bounded windows and indexes, then add `narrative_link_windows` only when needed.

### UI Misinterpretation

A user may read narrative links as recommendations. Mitigation: show evidence, status, reasons, and risks; keep `driver/watch/discard` as signal state rather than trade instruction.

## Acceptance Criteria

- Only watched-handle events can create narrative seeds.
- Full public-stream monitoring continues to ingest, extract, search, and generate token-flow independent of LLM.
- A watched-handle narrative seed can be linked to later full-stream token mentions.
- Every link has a reason, evidence event, confidence, lag, and risk list.
- Resolved CA links rank above unresolved symbols when evidence quality is comparable.
- No token link is created from pure LLM inference without later public-stream token evidence.
- Existing `/api/token-flow`, `/api/narrative-flow`, `/api/account-alerts`, `/ws`, and CLI commands continue to work as first-class product surfaces; no legacy aliases or fallback contracts are added.
- The system can rebuild narrative links for historical data idempotently.
