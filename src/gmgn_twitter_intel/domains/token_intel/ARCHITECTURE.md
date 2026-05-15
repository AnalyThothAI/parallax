# Token Intel Architecture

> **Scope.** Owns the Token Radar and token-identity map for cold-start agent
> work. Global package boundaries live in `../../../../docs/ARCHITECTURE.md`;
> public API / WebSocket / CLI contracts live in `../../../../docs/CONTRACTS.md`.

Token Radar is a mature, persisted pipeline. It is not "regex in the UI" and it
is not rebuilt from API payloads. The production chain is:

```
GMGN frame
  → CollectorService.handle_frame
  → normalize_gmgn_payload
  → IngestService.ingest_event transaction
      → events + event_entities
      → token_evidence
      → token_intents + token_intent_lookup_keys
      → token_intent_resolutions
      → registry_assets + asset_identity_evidence/current
      → enriched_events + inline market_ticks
  → TokenCaptureTierWorker ranks active market targets
  → MarketTickStreamWorker / MarketTickPollWorker refresh hot market_ticks
  → LivePriceGateway fans out cache-only live market updates
  → TokenRadarProjectionWorker
      → token_radar_rows.factor_snapshot_json
  → read models / Signal Pulse / notifications
  → HTTP / WebSocket / CLI / frontend
```

## Stage Map

| Stage | Code owner | Persisted facts | Invariant |
|-------|------------|-----------------|-----------|
| Upstream collection | `../ingestion/runtime/collector_service.py`, `../ingestion/services/normalizer.py` | raw frames, `events` | GMGN frames are normalized to `TwitterEvent` once. Token snapshots are identity-only (`chain` / `address` / `symbol`); embedded GMGN price fields are not normalized into token evidence. Public-stream coverage remains `public_stream`, not a full Twitter firehose. |
| Entity extraction | `../evidence/services/entity_extractor.py` | `event_entities` | Extracts span-aware CA, Solana, TON, cashtag, hashtag, mention, URL, and domain entities from primary and referenced tweet text. Only CA and cashtag become token evidence. |
| Evidence construction | `services/token_evidence_builder.py` | `token_evidence` | CA/address evidence is strong resolution evidence; cashtag evidence is medium symbol evidence; GMGN token payload evidence is strong provider evidence. Canonical asset display identity is selected later from asset identity evidence. |
| Intent construction | `services/token_intent_builder.py` | `token_intents`, evidence links | One event can produce multiple token intents. Local cashtag aliases may attach to a nearby CA; a free cashtag stays a symbol-only intent. |
| Deterministic resolution | `services/token_intent_resolver.py`, `services/deterministic_token_resolver.py` | `token_intent_resolutions`, `token_intent_lookup_keys` | Resolver outputs identity status and reason codes, not probabilistic guesses. CEX token matches win first; symbol-only confirmed US equities become `MarketInstrument`/`NON_CRYPTO` before DEX same-symbol assets; explicit chain+address wins through the address path as exact asset identity. |
| Asset identity ledger | `../asset_market/identity_evidence_policy.py`, `../asset_market/repositories/identity_evidence_repository.py` | `asset_identity_evidence`, `asset_identity_current` | Tweet CA mentions, GMGN payloads, OKX symbol candidates, and OKX exact address hits are separate evidence kinds. One deterministic policy selects current canonical symbol/name/confidence. |
| Discovery and reprocess | `../asset_market/runtime/resolution_refresh_worker.py`, `../asset_market/repositories/discovery_repository.py` | `token_discovery_results`, `registry_assets`, `asset_identity_evidence/current` | Recent NIL / AMBIGUOUS symbol and address lookup keys are refreshed through OKX DEX, then affected intents are reprocessed. Symbol search writes bounded candidate evidence; exact address lookup writes exact evidence. Successful refresh wakes downstream fact readers; it does not inline Token Radar projection. |
| Asset profile facts | `../asset_market/runtime/asset_profile_refresh_worker.py`, `../asset_market/services/asset_profile_refresh.py`, `../asset_market/repositories/asset_profile_repository.py`, `../asset_market/read_models/token_profile_read_model.py` | `asset_profiles` | Resolved DEX assets are enriched through the GMGN exact-token profile role after deterministic resolution. Profile facts are asset-level current facts and never resolver evidence, ranking factors, or `factor_snapshot_json` fields. Public read models consume persisted profile facts through `TokenProfileReadModel`; API and frontend code do not call providers. |
| Market facts | `../asset_market/runtime/{token_capture_tier_worker.py,market_tick_stream_worker.py,market_tick_poll_worker.py,live_price_gateway.py}`, `../asset_market/services/{event_market_capture.py,asset_market_sync.py}` | `cex_tokens`, `price_feeds`, `market_ticks`, `enriched_events`, `token_capture_tier` | Ingest writes inline event-adjacent market ticks. Capture-tier projection assigns active targets to stream, poll, or inline-only. Stream and poll workers refresh hot market ticks. CEX route sync maintains token/feed routing without refreshing prices. LivePriceGateway may receive high-frequency provider frames, but it is cache-only and does not persist facts. |
| Radar projection | `runtime/token_radar_projection_worker.py`, `services/token_radar_projection.py`, `scoring/factor_snapshot.py`, `scoring/cross_section_normalizer.py`, `scoring/factor_diagnostics.py`, `queries/token_radar_source_query.py` | `token_radar_rows.factor_snapshot_json`, `token_score_evaluations`, `projection_runs`, `projection_offsets` | Projection rebuilds 5m / 1h / 4h / 24h windows for `all` and `matched` scopes, joins current resolutions with events, account profiles, enrichment labels, registry address identity, `asset_identity_current`, `enriched_events`, and `market_ticks`, then emits `token_factor_snapshot_v3_social_attention`. TokenRadarProjectionWorker is the only runtime writer for `token_radar_rows`; wake notifications are hints and missed notifications are covered by periodic catch-up. |
| Search read model | `read_models/search_service.py`, `queries/search_events_query.py`, `services/query_parser.py`, `services/search_aliases.py` | `events.search_tsv`, `token_intent_resolutions`, `cex_tokens`, `registry_assets`, `asset_identity_current` | Search resolves query intent against current production identity first, retrieves target / lexical / trigram route hits, fuses them into cursor pages, and never performs provider calls, extraction, resolution mutation, scoring projection, or legacy `assets / asset_aliases / asset_venues` identity reads. |

## Factor Snapshot Contract

`token_radar_rows.factor_snapshot_json` is the current Token Radar product
contract. It contains:

- `schema_version = "token_factor_snapshot_v3_social_attention"` — the only runtime
  snapshot version accepted by readers.
- `subject` — deterministic target identity selected by the resolver and asset
  identity ledger, plus target-market identity facts.
- `market` — market context for the social signal. It contains explicit
  `event_anchor`, `decision_latest`, and `readiness` roles. `event_anchor`
  describes the event-time observation; `decision_latest` describes the latest
  material observation available to ranking, UI, and Signal Pulse. Market remains
  context and gate input, not an alpha family.
- `gates` — deterministic blockers, risk reasons, high-alert eligibility, and
  maximum decision. Identity readiness, CEX native-market identity, DEX
  market-cap / liquidity / holder floors, and market freshness are gates or
  data-health facts; they are not alpha factors.
- `data_health` — identity, market, social, and alpha readiness.
- `families` — social attention families only: `social_heat`,
  `social_propagation`, `semantic_catalyst`, and `timing_risk`.
  `timing_risk.weight = 0.0`, so timing contributes risk/gate context without
  positive alpha.
- `normalization` — cohort definition, per-family ranks, alpha rank, and status.
- `composite` — raw alpha score, cross-section rank score, family scores, and
  recommended decision derived from alpha families plus gates.
- `provenance` — source event ids and computation time.

Token Radar current runtime explanation source is `factor_snapshot_json`.
The market block is the single product-facing market contract; public readers do
not reconstruct legacy top-level market fields or process-local live market
fallbacks. Legacy score-centered JSON fields, v1 snapshot fields, and old
current-market refresh snapshots are not runtime fallback sources. `profile`
comes from the asset-level `asset_profiles` read model and is intentionally
outside the scoring snapshot. Signal Lab Pulse decisions consume v3 factor
snapshots, `market.decision_latest`, and deterministic gates.

Historical `token_radar_rows` are retained by `computed_at_ms` so
`TokenFactorEvaluationService` can settle forward returns point-in-time. Latest
read models select the newest run per target/window/scope; diagnostics use
`token_score_evaluations` and v3 score-version keys to keep populations
comparable.

## Identity Boundary

Current resolver output is:

```
EXACT / UNIQUE_BY_CONTEXT / AMBIGUOUS / NIL
```

The schema and specs reserve `PROJECT_ONLY` and `INVALID`, but agents should not
assume current production code emits them until `services/deterministic_token_resolver.py`
does. Resolution statuses are identity facts and must not be overloaded with
storage lifecycle values such as `demoted_search`.

Resolution history is represented by `record_status`, `is_current`, and
supersession fields. Runtime reads use the current resolution for the configured
resolver policy.

Canonical asset display identity is not stored on `registry_assets`.
`registry_assets` owns chain/address identity and lifecycle status only.
`asset_identity_evidence` stores claims, and `asset_identity_current` stores the
selected current symbol/name/confidence plus reason metadata. Tweet mentions are
mention context; they do not become target identity when stronger exact provider
evidence exists. If an asset has no selected current identity, a resolved target
symbol remains `None` rather than falling back to the mention symbol.

## Hard Boundaries

- API, WebSocket, CLI, and frontend surfaces read projected rows or read models;
  they never perform entity extraction, token resolution, provider calls,
  scoring, SQL joins, or notification decisions.
- Token profile provider calls live only in `asset_market` refresh/ops paths.
  Search, Token Radar, and UI surfaces consume `TokenProfileReadModel` output.
- LLM enrichment may label watched social events, but token identity resolution
  stays deterministic and does not call an LLM in the hot path.
- A symbol is a recall key, not identity. A chain+address or CEX registry fact
  is identity.
- DEX symbol discovery may add retained candidates, but it must not unboundedly
  expand `registry_assets`.
- Price freshness is market data health. It must not invent a new identity
  status or erase an otherwise valid deterministic identity decision.
- Market data health, duplicate clean state, and `social_signal_start_ms` do not
  create positive alpha. Duplicate concentration can penalize diffusion quality;
  clean duplication only removes that penalty.
- Token Radar target display uses current identity. Intent display symbol is
  preserved separately as what the tweet mentioned.
- Signal Pulse reads v3 `factor_snapshot_json`, first-class `decision_*`
  columns, `decision_json`, and deterministic gate output. Product decisions
  must not fall back to legacy Signal Pulse `thesis_json`, `radar_score_json`,
  or `market_context_json`.

## Update Triggers

Update this file in the same change when any of these move:

- entity extraction inputs that affect token evidence;
- token evidence, intent construction, lookup key, or resolver policy;
- discovery admission, retained candidate, or reprocess behavior;
- market observation semantics used by Token Radar;
- projection windows, source query joins, factor families, gates, market
  freshness SLOs, evaluation horizons, or persisted radar row shape.
