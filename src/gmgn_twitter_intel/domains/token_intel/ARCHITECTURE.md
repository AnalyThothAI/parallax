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
      → cex_tokens / price_feeds / price_observations
  → TokenDiscoveryWorker + market observation workers reprocess unresolved keys
  → TokenRadarProjectionWorker
      → token_radar_rows
  → read models
  → HTTP / WebSocket / CLI / frontend
```

## Stage Map

| Stage | Code owner | Persisted facts | Invariant |
|-------|------------|-----------------|-----------|
| Upstream collection | `../ingestion/runtime/collector_service.py`, `../ingestion/services/normalizer.py` | raw frames, `events` | GMGN frames are normalized to `TwitterEvent` once. Public-stream coverage remains `public_stream`, not a full Twitter firehose. |
| Entity extraction | `../evidence/services/entity_extractor.py` | `event_entities` | Extracts span-aware CA, Solana, TON, cashtag, hashtag, mention, URL, and domain entities from primary and referenced tweet text. Only CA and cashtag become token evidence. |
| Evidence construction | `services/token_evidence_builder.py` | `token_evidence` | CA/address evidence is strong resolution evidence; cashtag evidence is medium symbol evidence; GMGN token payload evidence is strong provider evidence. Canonical asset display identity is selected later from asset identity evidence. |
| Intent construction | `services/token_intent_builder.py` | `token_intents`, evidence links | One event can produce multiple token intents. Local cashtag aliases may attach to a nearby CA; a free cashtag stays a symbol-only intent. |
| Deterministic resolution | `services/token_intent_resolver.py`, `services/deterministic_token_resolver.py` | `token_intent_resolutions`, `token_intent_lookup_keys` | Resolver outputs identity status and reason codes, not probabilistic guesses. CEX token matches win before DEX same-symbol assets; explicit chain+address wins as exact asset identity; symbol-only DEX candidates must come from active retained registry candidates. |
| Asset identity ledger | `../asset_market/identity_evidence_policy.py`, `../asset_market/repositories/identity_evidence_repository.py` | `asset_identity_evidence`, `asset_identity_current` | Tweet CA mentions, GMGN payloads, OKX symbol candidates, and OKX exact address hits are separate evidence kinds. One deterministic policy selects current canonical symbol/name/confidence. |
| Discovery and reprocess | `../asset_market/runtime/token_discovery_worker.py`, `../asset_market/repositories/discovery_repository.py` | `token_discovery_results`, `registry_assets`, `asset_identity_evidence/current`, pricefeed / price observations | Recent NIL / AMBIGUOUS symbol and address lookup keys are discovered through OKX DEX, then affected intents are reprocessed. Symbol search writes bounded candidate evidence; exact address lookup writes exact evidence. Symbol candidates do not overwrite exact identity. |
| Market observation | `../asset_market/runtime/{asset_market_sync_worker.py,message_market_observation_worker.py}`, `../asset_market/services/{asset_market_sync.py,message_market_observation.py}` | `cex_tokens`, `price_feeds`, `price_observations`, `asset_identity_evidence/current` | CEX universe sync creates canonical CEX tokens and feeds. GMGN payload and message-level CEX / DEX quotes write price observations. OKX DEX price sync uses `identity_confidence` to decide exact-address verification; price freshness never stands in for identity confidence. |
| Radar projection | `runtime/token_radar_projection_worker.py`, `services/token_radar_projection.py`, `queries/token_radar_source_query.py` | `token_radar_rows`, `projection_runs`, `projection_offsets` | Projection rebuilds 5m / 1h / 4h / 24h windows for `all` and `matched` scopes, joins current resolutions with events, account profiles, enrichment labels, registry address identity, `asset_identity_current`, and market observations, then scores heat / quality / propagation / tradeability / timing / opportunity. Projection does not call providers or preflight-refresh markets. |

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
- LLM enrichment may label watched social events, but token identity resolution
  stays deterministic and does not call an LLM in the hot path.
- A symbol is a recall key, not identity. A chain+address or CEX registry fact
  is identity.
- DEX symbol discovery may add retained candidates, but it must not unboundedly
  expand `registry_assets`.
- Price freshness is market data health. It must not invent a new identity
  status or erase an otherwise valid deterministic identity decision.
- Token Radar target display uses current identity. Intent display symbol is
  preserved separately as what the tweet mentioned.

## Update Triggers

Update this file in the same change when any of these move:

- entity extraction inputs that affect token evidence;
- token evidence, intent construction, lookup key, or resolver policy;
- discovery admission, retained candidate, or reprocess behavior;
- market observation semantics used by Token Radar;
- projection windows, source query joins, score dimensions, or persisted radar
  row shape.
