# Token Posts and Explainable Evidence Scoring Design

## Problem

The trader cockpit currently mixes two different questions:

1. Which token flows deserve attention?
2. Which posts explain why a selected token flow deserves attention?

The backend currently returns a token flow row with a short `evidence` list. That list is built from the latest `top_events`, then sorted by a deterministic score. It is not the full set of token-attributed posts. The UI then truncates it again. This makes a 246-mention flow look like it has only a handful of visible posts, which is a contract bug rather than a visual problem.

## First Principles

The system must separate facts from interpretation.

- A post is a fact when it was stored, normalized, attributed to a resolved tradeable token, and can be replayed from SQLite.
- A highlight is an interpretation sample. It helps explain a signal, but it is never the full evidence set.
- A score is a deterministic accounting ledger. Every point must come from a named feature or a named risk cap.
- LLM output is not part of the hot ranking path. It may enrich narratives asynchronously, but it cannot create token evidence or secretly rerank posts.
- Token flow ranking and post highlighting must remain auditable from persisted evidence, token attribution, market snapshots, and deterministic diffusion features.

## Product Contract

The focus drawer has two token-specific views.

### All Posts

This view answers: "What are all token-attributed posts in this window?"

It uses a new endpoint:

```text
GET /api/token-posts?token_id=...&window=1h&scope=all&limit=50&cursor=...
GET /api/token-posts?chain=eth&address=0x...&window=1h&scope=all&limit=50&cursor=...
```

Response:

```json
{
  "ok": true,
  "data": {
    "query": {
      "token_id": "token:eth:0x...",
      "chain": "eth",
      "address": "0x...",
      "window": "1h",
      "scope": "all",
      "sort": "recent"
    },
    "total_count": 246,
    "returned_count": 50,
    "has_more": true,
    "next_cursor": "opaque",
    "items": [
      {
        "event_id": "event-...",
        "handle": "traderpow",
        "text": "$TOKEN ...",
        "url": "https://x.com/...",
        "received_at_ms": 1777746010000,
        "mention_source": "gmgn_token_payload",
        "attribution_status": "direct",
        "attribution_confidence": 1.0,
        "attribution_weight": 1.0,
        "score": 92,
        "score_version": "post_score_v1",
        "reasons": ["structured_token_payload", "resolved_ca"],
        "risks": [],
        "contributions": [
          {"feature": "identity_certainty", "value": 18, "reason": "resolved_ca"}
        ],
        "risk_caps": []
      }
    ]
  }
}
```

Rules:

- The endpoint queries `event_token_attributions` directly.
- It does not use FTS or search query fallback.
- It returns distinct posts, not duplicate attribution rows.
- Cursor pagination is keyset based on `(received_at_ms, event_id)`.
- `scope=matched` limits to watched-account attributed posts; `scope=all` uses the full stored public stream.
- `total_count` is the distinct attributed post count for the same query and window.

### Signal Explanation

This view answers: "Why did this token flow rank here?"

`/api/token-flow` returns:

```json
{
  "identity": {},
  "market": {},
  "flow": {},
  "baseline": {},
  "diffusion": {},
  "watch": {},
  "attribution": {},
  "signal": {},
  "evidence_highlight_best": {},
  "evidence_highlights": [],
  "evidence_total_count": 246,
  "posts_query": {
    "token_id": "token:eth:0x...",
    "window": "1h",
    "scope": "all"
  }
}
```

Breaking change:

- `evidence` is removed from token flow rows.
- `evidence_best` is removed from token flow rows.
- There is no compatibility alias.

## Scoring Model

### Post Score

Post score estimates how useful one attributed post is as an explanation sample.

Feature families:

- `identity_certainty`: resolved CA beats unresolved or ambiguous symbols.
- `attribution_quality`: direct structured attribution beats selected symbol attribution; confidence and weight matter.
- `source_specificity`: GMGN token payload and contract address text are stronger than cashtag-only evidence.
- `source_trust`: watched-account post receives a deterministic boost.
- `diffusion_context`: multi-author diffusion raises explanatory value; concentrated or repeated diffusion caps score.
- `freshness`: recent posts in the selected window are more useful as highlights.
- `market_context`: fresh market snapshot, market cap, liquidity, and pool presence raise confidence.

Output is an accounting ledger:

```json
{
  "score": 86,
  "score_version": "post_score_v1",
  "reasons": ["resolved_ca", "fresh_market"],
  "risks": ["author_concentration_high"],
  "contributions": [
    {"feature": "identity_certainty", "value": 18, "reason": "resolved_ca"},
    {"feature": "market_context", "value": 8, "reason": "fresh_market"}
  ],
  "risk_caps": [
    {"risk": "author_concentration_high", "cap": 75}
  ]
}
```

Risk caps are applied after additive contributions. They are not hidden penalties.

### Token Flow Score

Token flow remains a first-stage deterministic ranker. It should favor:

- Resolved tradeable token identity.
- Fresh market and pool data.
- High-confidence attribution.
- Rolling acceleration or burst against baseline.
- Independent author diffusion.
- Watched-account direct mention or narrative seed link.

It should penalize:

- Missing market data.
- Stale market data.
- Low attribution confidence.
- Author concentration.
- Repeated text clusters.
- Public-only flows without watched confirmation.

The service should over-fetch candidate rows, compute full signal blocks, and then sort by signal quality. Ranking before scoring can hide high-quality tokens behind high-volume low-quality tokens.

## Storage and Indexing

Add a query-oriented index:

```sql
CREATE INDEX IF NOT EXISTS idx_event_token_attributions_posts_recent
  ON event_token_attributions(token_id, received_at_ms DESC, event_id DESC)
  WHERE token_id IS NOT NULL
    AND attribution_status IN ('direct', 'selected')
    AND attribution_weight > 0
    AND chain IS NOT NULL
    AND address IS NOT NULL
    AND chain NOT IN ('unknown', 'evm', 'evm_unknown');
```

This supports full-post pagination for resolved tradeable tokens.

The address lookup path has its own prefix index because `chain/address` queries should not depend on a token ID being supplied:

```sql
CREATE INDEX IF NOT EXISTS idx_event_token_attributions_posts_ca_recent
  ON event_token_attributions(chain, address, received_at_ms DESC, event_id DESC)
  WHERE token_id IS NOT NULL
    AND attribution_status IN ('direct', 'selected')
    AND attribution_weight > 0
    AND chain IS NOT NULL
    AND address IS NOT NULL
    AND chain NOT IN ('unknown', 'evm', 'evm_unknown');
```

## UI

When a token row is selected:

- The focus drawer defaults to `全部帖子`.
- `全部帖子` shows `total_count`, loaded count, individual post score, and attribution metadata.
- `信号解释` shows `evidence_highlights`, highlight score reasons, token signal reasons, and risks.
- The old display that implied highlights were complete evidence is removed.

For search, live events, and alerts, the existing evidence-focused drawer behavior can remain because those surfaces are not token flow full-post claims.

## Acceptance Criteria

- A token with 246 attributed posts shows `246 total posts` in the UI and can page through all of them.
- `/api/token-posts` returns deterministic full-post pages without FTS.
- `/api/token-flow` no longer returns `evidence` or `evidence_best`.
- Every token flow highlight has `score_version`, `score`, `reasons`, `risks`, `contributions`, and `risk_caps`.
- Token flow ranking is based on computed signal quality, not only pre-score volume ordering.
- Tests cover pagination, counts, scoring explanations, breaking contract removal, and frontend tab behavior.
