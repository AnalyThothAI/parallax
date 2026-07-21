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
          → token_radar_source_dirty_events for resolved source-event edges from formal TokenIntentResolutionDecision results
      → registry_assets + asset_identity_evidence/current
      → enriched_events + inline market_ticks
      → event_anchor_backfill_jobs for short-lived missing-anchor control
  → TokenCaptureTierWorker ranks active market targets
  → MarketTickStreamWorker / MarketTickPollWorker refresh hot market_ticks
  → LivePriceGateway fans out cache-only live market updates
  → TokenRadarProjectionWorker
      → token_radar_rank_source_events
      → token_radar_target_features
      → token_radar_current_rows.factor_snapshot_json
      → token_radar_publication_state
  → read models / notifications
  → HTTP / WebSocket / CLI / frontend
```

## Stage Map

| Stage | Code owner | Persisted facts | Invariant |
|-------|------------|-----------------|-----------|
| Upstream collection | `../ingestion/runtime/collector_service.py`, `../ingestion/services/normalizer.py` | raw frames, `events` | GMGN frames are normalized to `TwitterEvent` once. Token snapshots are identity-only (`chain` / `address` / `symbol`); embedded GMGN price fields are not normalized into token evidence. Public-stream coverage remains `public_stream`, not a full Twitter firehose. |
| Entity extraction | `../evidence/services/entity_extractor.py` | `event_entities` | Extracts span-aware CA, Solana, TON, cashtag, hashtag, mention, URL, and domain entities from primary and referenced tweet text. Only CA and cashtag become token evidence. |
| Evidence construction | `services/token_evidence_builder.py`, `repositories/token_evidence_repository.py` | `token_evidence` | CA/address evidence is strong resolution evidence; cashtag evidence is medium symbol evidence; GMGN token payload evidence is strong provider evidence. Canonical asset display identity is selected later from asset identity evidence. Repository-owned evidence writes require a callable connection transaction before SQL; ingest/rebuild paths keep writes caller-owned with `commit=False` inside their outer transaction. Evidence writes accept formal `TokenEvidenceInput` or mapping rows only; loose `__slots__` objects are not repository input contracts. Evidence upserts require `RETURNING *` with PostgreSQL rowcount=1, while event-scoped deletes require real non-negative rowcount evidence. |
| Intent construction | `services/token_intent_builder.py`, `repositories/token_intent_repository.py` | `token_intents`, evidence links | One event can produce multiple token intents. Local cashtag aliases may attach to a nearby CA; a free cashtag stays a symbol-only intent. Repository-owned intent/evidence-link writes require a callable connection transaction before SQL; ingest/rebuild paths keep writes caller-owned with `commit=False` inside their outer transaction. Intent writes accept formal `TokenIntentInput` or mapping rows only; loose `__slots__` objects are not repository input contracts. Intent upserts require `RETURNING *` with rowcount=1, evidence-link `ON CONFLICT DO NOTHING` accepts only rowcount 0/1, and event-scoped deletes require real non-negative rowcount evidence. |
| Deterministic resolution | `services/token_intent_resolver.py`, `services/deterministic_token_resolver.py`, `repositories/intent_resolution_repository.py`, `repositories/token_intent_lookup_repository.py` | `token_intent_resolutions`, `token_intent_lookup_keys` | Resolver outputs identity status and reason codes, not probabilistic guesses. CEX token matches win first; symbol-only confirmed US equities become `MarketInstrument`/`NON_CRYPTO` before DEX same-symbol assets; explicit chain+address wins through the address path as exact asset identity. Repository-owned lookup-key replacement and resolution writes require a callable connection transaction before SQL; `insert_resolution` enters that transaction before `pg_advisory_xact_lock`. Resolution writes accept formal `DeterministicResolution` or mapping rows only; loose `__slots__` objects are not repository input contracts. Lookup replacement deletes require real non-negative rowcount, each lookup upsert requires rowcount=1, superseding an old current resolution requires update rowcount=1, and resolution upsert returns the written fact only after `RETURNING *` rowcount=1. |
| Watched account alerts | `../evidence/services/ingest_service.py`, `repositories/signal_repository.py`, `../account_quality/read_models/account_alert_service.py` | `account_token_alerts` | Ingest emits watched-account token alerts only after deterministic token resolution and first-seen checks. Ingest keeps alert writes caller-owned with `commit=False` inside the evidence unit of work; repository-owned alert inserts require a callable connection transaction before SQL and never fall back to manual `self.conn.commit()`. `INSERT ... DO NOTHING` created-vs-existing classification requires PostgreSQL single-row `cursor.rowcount` evidence; missing or invalid rowcount is malformed driver state, not an alert-created or existing-row decision. |
| Asset identity ledger | `../asset_market/identity_evidence_policy.py`, `../asset_market/repositories/identity_evidence_repository.py` | `asset_identity_evidence`, `asset_identity_current` | Tweet CA mentions, GMGN payloads, OKX symbol candidates, and OKX exact address hits are separate evidence kinds. One deterministic policy selects current canonical symbol/name/confidence. |
| Discovery and reprocess | `../asset_market/runtime/resolution_refresh_worker.py`, `../asset_market/repositories/discovery_repository.py` | `token_discovery_dirty_lookup_keys`, `token_discovery_results`, `registry_assets`, `asset_identity_evidence/current` | Intent writes and reprocess paths enqueue NIL / AMBIGUOUS symbol and address lookup keys. The worker claims due queue rows, refreshes them through OKX DEX, then reprocesses affected intents using the named `TOKEN_REPROCESS_WINDOW` policy and formal `settings.workers.resolution_refresh` timing/reprocess fields: `lease_ms`, `hot_not_found_retry_ms`, and `reprocess_limit`. DiscoveryRepository receives lookup due/claim/start timing explicitly, does not own repository-local runtime policy constants, and does not expose a read-only due-list helper as a second queue-consumer path. Reprocessed resolved event edges enqueue `token_radar_source_dirty_events` from formal `TokenIntentResolutionDecision` results only; loose resolver decision objects are malformed reprocess state, not empty dirty work. Missing source-dirty repository contract is a failure, not an empty queue. Token intent rebuild and resolution reprocess writes require `RepositorySession.transaction` plus `require_transaction` before token evidence/intent/lookup/resolution/discovery/source-dirty SQL; their public helpers require explicit window/limit arguments and do not expose service-local default limit/window compatibility constants. They do not commit through raw `repos.conn.commit()`. It does not scan recent facts to discover due lookups. Successful refresh wakes downstream fact readers; it does not inline Token Radar projection. |
| Asset profile facts | `../asset_market/runtime/asset_profile_refresh_worker.py`, `../asset_market/runtime/token_profile_current_worker.py`, `../asset_market/services/token_profile_current_projection.py`, `../asset_market/read_models/token_profile_read_model.py` | `asset_profiles`, `cex_token_profiles`, `token_profile_current` | GMGN OpenAPI, Binance Web3, and Binance CEX profile rows are source-cache facts. Public profile/icon facts come from `token_profile_current`, projected from persisted source caches plus GMGN stream exact snapshot and OKX DEX exact-address evidence. Profile facts are never resolver evidence, ranking factors, or `factor_snapshot_json` fields. API and frontend code do not call providers. |
| Market facts | `../asset_market/runtime/{token_capture_tier_worker.py,market_tick_stream_worker.py,market_tick_poll_worker.py,event_anchor_backfill_worker.py,live_price_gateway.py}`, `../asset_market/services/{event_market_capture.py,asset_market_sync.py}` | `cex_tokens`, `price_feeds`, `market_ticks`, `enriched_events`, `token_capture_tier`; `event_anchor_backfill_jobs` control state | Ingest writes inline event-adjacent market ticks or a pending event-anchor fact plus a short-lived backfill job. Capture-tier projection assigns active targets to stream, poll, or inline-only. Stream and poll workers refresh hot market ticks. Event-anchor backfill consumes jobs, not fact rows, and terminalizes anchors it cannot validly attach. LivePriceGateway may receive high-frequency provider frames, but it is cache-only and does not persist facts. |
| Event token projection | `queries/event_token_projection_query.py` | reads `token_intent_resolutions`, `asset_identity_current`, `cex_tokens`, `price_feeds`, `enriched_events`, `market_ticks` | HTTP recent, WebSocket replay/live payloads, and watchlist timelines expose token mentions through this read model. It returns a lean public token-resolution payload with `symbol` and standard message `price`; public surfaces do not serialize raw resolution fact rows. Selected current resolution rows must provide non-empty resolution/intent/event/status fields plus list-shaped `reason_codes_json`, `candidate_ids_json`, and `lookup_keys_json`; malformed rows fail rather than being repaired through JSON string parsing or empty-array defaults. |
| Radar projection | `runtime/token_radar_projection_worker.py`, `services/token_radar_projection.py`, `scoring/`, `queries/token_radar_rank_source_query.py`, `repositories/{token_radar_rank_source_repository.py,token_radar_repository.py,projection_repository.py}` | `token_radar_source_dirty_events`, `token_radar_dirty_targets`, `token_radar_rank_source_events`, `token_radar_target_features`, `token_radar_current_rows`, `token_radar_publication_state`, `projection_runs`, `projection_offsets` | The worker is the single runtime writer. It claims only the domain-specific durable source-event and target queues, applies due gates, and atomically publishes one content-stable generation per `(projection_version, window, scope, venue)`. The generic projection dirty-range queue is retired. Worker widths and timing come from `settings.workers.token_radar_projection`; malformed work identities or windows fail closed. Source/target queue writes and repository-owned projection writes require connection transactions and claimed-row identity. Unchanged projections write zero serving rows. Current-row identity is the stable `target_type_key` plus `identity_id`; unresolved rows use formal lookup keys, never display-symbol reconstruction. `token_radar_current_rows` is the online leaderboard and `token_radar_publication_state` is its readiness/failure state. `token_radar_target_features` remains projection-private. Repair is explicit ops enqueue, not a runtime fact-window scan. |
| Search read model | `read_models/search_service.py`, `queries/search_events_query.py`, `services/query_parser.py`, `services/search_aliases.py` | `events.search_tsv`, `token_intent_resolutions`, `cex_tokens`, `registry_assets`, `asset_identity_current` | Search resolves query intent against current production identity first, retrieves target / lexical / trigram route hits, fuses them into cursor pages, and never performs provider calls, extraction, resolution mutation, scoring projection, or legacy `assets / asset_aliases / asset_venues` identity reads. API/CLI callers own `limit`, `scope`, and `window` defaults/validation and pass them explicitly; `SearchService` does not retain read-service query-boundary defaults or unknown-window fallback. OR-symbol target resolution is one PostgreSQL keyset read through `SearchEventsQuery.resolve_symbols(...)` and `unnest(%s::text[]) WITH ORDINALITY`; it must not loop over symbols and call the single-symbol resolver once per token. |

Token Radar downstream fan-out target identity, rank-input venue selection, and
Token Capture Tier dirty rank-set hashes derive from formal current-row
`target_type_key` plus `identity_id`. Stale `target_type` / `target_id` aliases
must not override formal keys, and alias-only current rows fail before dirty hash
construction or downstream enqueue.
Projection-private `token_radar_target_features` rows must also expose formal
`target_type_key` plus `identity_id` before `_row_from_target_feature(...)`
constructs a current row; missing target-feature identity is malformed private
cache state, not an empty serving identity. The same target-feature-to-current
boundary requires non-empty `projection_version`, `window`, `scope`, `lane`,
integer `latest_event_received_at_ms`, and mapping-shaped
`factor_snapshot_json`; missing private-cache dimensions fail before row-id,
source frontier, lane, or factor payload construction. Current-row
`created_at_ms` at this boundary derives from formal `last_scored_at_ms`; it is
not restored from target-feature `updated_at_ms` or `_now_ms()`. The
target-feature cache writer applies the same hard edge before SQL: `lane`,
`source_max_received_at_ms`, `source_event_ids_json`, `created_at_ms`, and
`factor_snapshot_json` are required projection payload fields, not values to
repair through `attention`, `computed_at_ms`, `[]`, or `{}` defaults. Core
scoring fields inside the snapshot are formal too: `composite.rank_score`,
`composite.recommended_decision`, and `gates.max_decision` must already exist
before payload hashing or SQL, and missing values are not repaired to `0.0` or
`discard`.
Narrative Admission, Token Profile Current, Asset Profile Refresh, and Token
Capture Tier downstream dirty targets derive `source_watermark_ms` only from the current
row's positive `source_max_received_at_ms`; missing or invalid watermarks fail
closed instead of falling back to `computed_at_ms`, `0`, or projection runtime
time. The Narrative Admission dirty repository also rejects missing, zero,
negative, boolean, or string producer watermarks before queue SQL and keeps no
zero-watermark enqueue compatibility branch. Capture-tier rank-set
repair may read bounded current rows, but those rows must also carry positive
source watermarks before enqueue.
Rank-set selection requires each rank input to expose a non-negative
`latest_event_received_at_ms` and a known `lane` before window filtering and
resolved/attention selection; malformed rank inputs fail instead of being
treated as expired rows or dropped from both lanes. Compact rank inputs require
formal `raw_composite_score` and `gates_max_decision`, and ranked rows require
formal `rank_score` and `recommended_decision`; missing score/gate/decision
fields are not repaired to `0.0` or `discard`. Retired snapshot-row sort
helpers are removed: rank publication does not use `_rank_key`, `raw_alpha_score`
fallback, or invalid-snapshot demotion as an alternate ranking path.
Ranked current-row patching requires formal `normalization_status`,
`cohort_status`, `cohort_size`, `cohort_in_cohort`, `cohort_metadata`, complete
per-family `factor_ranks`, `alpha_rank`, `rank`, `rank_score`,
`recommended_decision`, and `latest_event_received_at_ms` before mutating
current rows or `factor_snapshot_json`; missing ranked metadata is malformed
publication state, not permission to publish `no_signal`, `not_ranked`, false
cohort membership, an empty or incomplete rank map, alpha rank `None`, rank `0`,
or source watermark `0`. Family rank values must be `None` or bounded `0..1`
ranks.
Token Radar current-row delete/upsert, target-feature write/delete, and
target-feature retention counts require real PostgreSQL `cursor.rowcount`
evidence. Missing, boolean, negative, or non-integer rowcount is
repository/driver contract drift, not a default no-op or one-row write.
`token_radar_target_first_seen` upsert counts require the same PostgreSQL
`cursor.rowcount` evidence; first-seen write accounting cannot be restored from
projection candidate `len(records)`.
Projection-run stale-running cleanup counts require the same PostgreSQL
`cursor.rowcount` evidence. Missing or invalid rowcount is malformed
repository/driver state, not a default zero abandoned-run count.
Projection work is discovered only through the domain-specific durable
source-event and target dirty queues; the retired generic dirty-range queue is
not a second control plane.
Ordinary ProjectionRepository offset, run-ledger, and finish mutations require
exactly one PostgreSQL rowcount; `start_run`
uses `INSERT ... RETURNING *` and must not fall back to `run_by_id` readback as
proof of the run insert.
Unresolved Token Radar attention rows derive their `LookupKey/...` identity
from formal resolution `lookup_keys_json` only. A missing lookup key is malformed
resolution input, not permission to synthesize identity from `display_symbol`.

Generic dirty enqueue contracts for `token_radar_dirty_targets.enqueue_targets`
and `token_radar_source_dirty_events` require formal queue identity before
payload hashes or queue SQL. Generic target dirty enqueue accepts
`target_type_key` plus `identity_id` only; source dirty enqueue accepts
`source_event_id`, `target_type_key`, and `identity_id` only. Legacy
`target_type`, `target_id`, `intent_id`, and `event_id` aliases are producer
bugs at this boundary and fail instead of being mapped or silently skipped in
repository code.

Target/source dirty queue mutation paths that return changed-row counts require
real PostgreSQL `cursor.rowcount` evidence. Missing, boolean, negative, or
non-integer rowcount is repository/driver contract drift, not a default
zero-row enqueue, completion, retry, or catch-up write count.

Dirty completion keys for `token_radar_dirty_targets` and
`token_radar_source_dirty_events` preserve the claimed-row queue identity and
CAS fields. Target dirty completion requires `target_type_key` plus
`identity_id`; source dirty completion requires `projection_version`,
`source_event_id`, `target_type_key`, and `identity_id`. `attempt_count` must
be positive, `lease_owner` must be non-empty, and `payload_hash` must be
present before rank-source population, source projection, or done/error SQL.
Missing fields are malformed claim rows, not alias-derived identity,
`attempt_count=0`, empty-owner, or empty-payload compatibility tokens.
Rank-source repair target payloads, latest-market-context input/output rows,
affected-target output rows, and projection source request target lists require
the same formal `target_type_key` plus `identity_id` command shape.
`target_type` / `target_id` aliases are not repaired at those helpers, and
malformed source targets fail before edge repair, market-context SQL/result
mapping, source request generation, or target-feature delete/upsert.
Token Radar stable payload canonicalization and hash primitives live in
`token_intel.types.token_radar_payload_hash`; repositories and projection
services import that leaf module directly, with no repository exception for
upward service imports.

After due source-event or target dirty work is claimed, `TokenRadarProjection.rebuild_dirty_targets`
processes rank-source edge updates, target-feature writes/deletes, rank-set publication attempts,
and dirty queue done/error terminalization inside one explicit connection transaction. Worker-level
lease claims may be committed before the processing phase, but the processing/publish/terminal-state
chain must not be split into autocommit statements. On PostgreSQL connections configured with
`autocommit=True`, `commit=False` is only a caller-owned commit boundary when an explicit transaction
is already active. Dirty queue lease timing, retry cadence, and retry budget
belong to `settings.workers.token_radar_projection`: the worker reads
`lease_ms`, `retry_ms`, and `max_attempts` directly and passes them into
`TokenRadarProjection.rebuild_dirty_targets(...)`. The same worker owns dirty
claim width, rank publish width, and lease owner: it passes `limit`,
`rank_limit`, and `lease_owner` explicitly. The projection service does not own
hidden dirty queue or rank-publication policy defaults. Exhausted target/source
dirty error claims are deleted with `RETURNING queue.*` and terminalized into
`worker_queue_terminal_events` inside the same projection transaction instead
of being rescheduled indefinitely. Queue Terminal retry transitions requeue
those snapshots only through `token_radar_dirty_targets.enqueue_targets(...)`
or `token_radar_source_dirty_events.enqueue_events(...)`.
Source/target dirty claim `UPDATE ... RETURNING` paths require cursor rowcount
evidence matching the returned claim rows before the projection service treats
work as claimed.

`TokenIntentResolver` is deterministic resolution logic plus caller-owned persistence only. It exposes
no `commit` flag and never commits `token_intent_resolutions` itself; ingest, rebuild, and reprocess
entrypoints write resolver output inside their surrounding repository-session transaction.
Resolver inputs are formal `TokenIntentInput` / `TokenEvidenceInput` objects or
mapping rows only; loose objects with matching attributes are not resolution
input contracts.
Resolution reprocess must batch token evidence for the selected intent keyset
through `TokenEvidenceRepository.evidence_for_intents(...)`; it must not query
`token_intent_evidence` / `token_evidence` once per intent inside the reprocess
loop.
The underlying token fact repositories (`TokenEvidenceRepository`,
`TokenIntentRepository`, `TokenIntentLookupRepository`, and
`IntentResolutionRepository`) enforce the same boundary when they own commits:
they require callable connection transactions before fact SQL and do not fall
back to naked `self.conn.commit()`. `IntentResolutionRepository` must enter that
transaction before taking the per-intent PostgreSQL advisory transaction lock.
They also require PostgreSQL mutation evidence before reporting fact writes:
token evidence, token intent, and token intent resolution upserts use
`RETURNING *` plus rowcount=1; token-intent evidence links allow only the
explicit `ON CONFLICT DO NOTHING` rowcount 0/1 shape; lookup-key replacement
deletes accept real non-negative rowcount, while each replacement upsert must
affect exactly one row. Missing, boolean, negative, non-integer, zero-row
required-write, multi-row, or returned-row mismatch evidence is malformed
repository/driver state, not an empty fact result or a fallback-read success.

## Factor Snapshot Contract

`token_radar_current_rows.factor_snapshot_json` is the current Token Radar product
contract. It contains:

- `schema_version = "token_factor_snapshot_v3_social_attention"` — the only runtime
  snapshot version accepted by readers.
- `subject` — deterministic target identity selected by the resolver and asset
  identity ledger, plus target-market identity facts.
- `market` — public market context for the social signal. It contains
  `event_anchor`, `decision_latest`, and `readiness` response keys generated
  from `enriched_events` and `market_ticks`; those names are not internal market
  DB concepts or worker/runtime semantics. `event_anchor_backfill_jobs` is never
  part of the Token Radar input contract. Market remains context and gate input,
  not an alpha family.
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
- `composite` — final rank score, recommended decision, and optional display
  aliases such as `family_scores`; formal family diagnostics come from
  `families.*.score`.
- `provenance` — source event ids and computation time.

The private `token_radar_target_features` cache persists the selected
`intent_json` and `resolution_json` beside the factor snapshot and formal source
id lists. Rank publication reads those payloads directly: it does not infer an
intent/event from cache identity, synthesize a resolution status from target
presence, or discard resolver reason/candidate/lookup provenance. The cache key
is the stable product/window target identity; projection-time timestamps are not
row identity.

`token_radar_current_rows` stores `rank_score`, `quality_status`,
`degraded_reasons_json`, and `factor_snapshot_json`. Publication requires
mapping-shaped `intent_json`, `resolution_json`, and `data_health_json`, plus
list-shaped `source_event_ids_json` and `degraded_reasons_json`; the repository
does not synthesize missing JSON objects or arrays. `resolution_json` also
requires non-empty `status` and formal list fields `reason_codes`,
`candidate_ids`, and `lookup_keys`. Token Radar current runtime
explanation source is `factor_snapshot_json`.
The market block is the single product-facing market contract; public readers do
not reconstruct legacy top-level market fields or process-local live market
fallbacks. Legacy score-centered JSON fields, v1 snapshot fields, and old
current-market refresh snapshots are not runtime fallback sources. `profile`
comes from the asset-level `token_profile_current` read model and is intentionally
outside the scoring snapshot.

Latest read models read `token_radar_current_rows`. Online readiness and
last-failure semantics come only
from `token_radar_publication_state`: `fresh` requires a ready latest attempt,
product/window current rows, or an explicitly empty ready publication. A failed
latest attempt with prior current rows is `stale`; a failed latest attempt
without current rows is `failed`; missing state must not be reported as
`fresh`. `current_generation_id` remains attempt audit metadata, not an online
serving join key. `fresh`, `stale`, and `failed` describe publication
freshness, while row `quality_status` describes business credibility. A
degraded row can still be a useful `watch`, but `high_alert` requires market
quality and deterministic gates to pass.

Successful publication generation ids are content-stable over current-row
content. When a rebuild produces unchanged content, publication state refreshes
without deleting or inserting current rows. Timestamp-derived ids are reserved
for failed attempts before row build (`attempt:{...}:{computed_at_ms}`), not
successful generations.

`token_radar_rank_source_events` rows are stable source packets. They are
rewritten only when their normalized source payload hash changes. Latest market
context is a target-level scoring input loaded from current market facts during
projection; market-only dirty targets must not rehydrate or rewrite every
source edge just because a quote changed. Edge population write counts come from
explicit SQL aggregate count rows, and edge prune counts come from PostgreSQL
`cursor.rowcount`; missing, boolean, negative, or non-integer mutation-count
evidence is malformed query/driver state, not a default zero-edge update.

`token_radar_rank_source_events` may be queried for detail/evidence only when
bounded by a current row key and limit. `token_radar_target_features` is a
projection-private intermediate layer, not an online read API. Private cache
retention is owned by `TokenRadarProjectionWorker`, uses formal
`settings.workers.token_radar_projection.private_cache_retention_enabled` and
`private_cache_retention_ms`, and deletes old target-feature / rank-source rows
through bounded repository prune calls outside `refresh_rank_set`. Retired
history/audit/coverage tables are not current-serving or publication-state
sources.

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
- Search Inspect token results delegate to Token Case and must pass the
  persisted `cex_detail_snapshots` repository for `CexToken` dossiers. Missing
  snapshot rows can produce a structured missing CEX detail block, but that
  block must not synthesize `exchange`; only a persisted
  `cex_detail_snapshots` row carries that market identity field. Missing
  repository/session support is not compatible with a successful token result.
  The CEX detail repository also owns query-identity validation, so Token Case
  cannot hide malformed empty `target_type` / `target_id` CEX lookups behind an
  empty PostgreSQL result.
- Token Case and Search Inspect market-live blocks read persisted current
  market ticks through `TokenTargetRepository.latest_market_tick`. Missing
  current tick rows can produce a structured missing market block, but missing
  repository/session support is not compatible with a successful dossier.
- Token Case, `/api/target-posts`, and `/api/target-social-timeline` callers
  own target timeline `window`, `scope`, and page `limit` defaults/validation.
  Token-target read services fail malformed direct-call `window` or `scope`
  contracts before repository reads; they do not restore unknown windows through
  `1h` fallbacks or treat unknown scopes as `all`.
- Token profile provider calls live only in `asset_market` refresh/ops paths.
  Search, Token Radar, and UI surfaces consume `TokenProfileReadModel` output
  from `token_profile_current`.
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
- Token Radar online consumers read `token_radar_current_rows` plus
  `token_radar_publication_state` only. Failed publications must surface
  `stale` or `failed`; they must never be wrapped as `fresh` because older
  current rows still exist.

## Update Triggers

Update this file in the same change when any of these move:

- entity extraction inputs that affect token evidence;
- token evidence, intent construction, lookup key, or resolver policy;
- discovery admission, retained candidate, or reprocess behavior;
- market tick semantics used by Token Radar;
- projection windows, source query joins, factor families, gates, market
  freshness SLOs, evaluation horizons, or persisted radar row shape.
