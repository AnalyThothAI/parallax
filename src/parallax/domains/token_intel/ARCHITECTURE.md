# Token Intelligence Architecture

## Scope

`token_intel` turns immutable social evidence into deterministic token identity facts and a rebuildable Token Radar read model.
It follows Kappa/CQRS: PostgreSQL facts are business truth; projections are disposable serving state.
Provider payloads and WebSocket frames are inputs only.

## Non-negotiable invariants

1. Facts are append-oriented or explicitly versioned.
2. Every derived read model has one runtime writer.
3. Every public repository write requires an already-active transaction.
4. Worker, service, or application code owns the transaction boundary.
5. Serving identity uses stable product keys, never run, attempt, timestamp, generation, or UUID identity.
6. Replaying unchanged facts writes zero serving rows.
7. Workers re-read PostgreSQL on bounded intervals; there is no wake dependency.
8. Token Radar has one work queue: `token_radar_dirty_targets`.

## Material facts

| Fact | Purpose | Writer |
|---|---|---|
| `events` | Normalized source event | evidence ingest |
| `event_entities` | Deterministic entities extracted from an event | evidence ingest |
| `token_evidence` | Address, symbol, price-feed, and provider evidence | ingest or rebuild service |
| `token_intents` | One or more token mentions constructed from evidence | ingest or rebuild service |
| `token_intent_evidence` | Intent-to-evidence links | intent repository |
| `token_intent_lookup_keys` | Stable keys used for later discovery and re-resolution | resolution service |
| `token_intent_resolutions` | Versioned deterministic resolution decisions | resolution service |
| asset identity facts | Canonical chain asset and exchange identity | asset market domain |
| market tick facts | Immutable market observations and current market projection | asset market domain |

`token_intent_resolutions.is_current` identifies the active decision for an intent.
Superseding and inserting a resolution occur under the same advisory-locked transaction.

## Ingest and resolution flow

```text
raw input
  -> normalized event
  -> extracted entities
  -> token evidence
  -> token intents + lookup keys
  -> deterministic resolution
  -> token_radar_dirty_targets
```

`IngestService` owns one unit of work for event, entity, token fact, resolution, market-anchor request, and dirty-target writes.
`rebuild_recent_token_intents` and `reprocess_recent_token_intents` each own their application transaction.
Repositories validate the active transaction through `require_transaction` before issuing mutation SQL.
Repositories never choose whether to commit and never open implicit transactions.

## Token Radar private projection state

`token_radar_rank_source_events` is a narrow, rebuildable edge table from a target to qualifying source events.
It prevents repeated wide joins when a small target set changes.

`token_radar_target_features` is the private feature cache.
Its stable key is:

```text
(projection_version, window, scope, lane, target_type_key, identity_id)
```

Payload hashes exclude operational timestamps.
An upsert changes a row only when the semantic payload changes.
Expired private rows and edges are pruned in bounded batches.

## Single dirty-target queue

`token_radar_dirty_targets` is keyed by:

```text
(target_type_key, identity_id)
```

The queue coalesces repeated work for the same identity.
Its payload hash, lease owner, and attempt count form the compare-and-delete acknowledgement contract.
Dirty-kind flags distinguish market-only refreshes from full evidence repair without creating another lane.

Queue behavior:

- enqueue unions dirty-kind flags and preserves the first dirty time;
- claim uses `FOR UPDATE SKIP LOCKED` with a bounded lease;
- retry clears the lease and schedules a bounded due time;
- exhausted work is terminalized in the same transaction as source-row deletion;
- acknowledgement deletes only the exact claimed payload, owner, and attempt;
- newer concurrent work therefore survives an older acknowledgement.

The worker commits claim leases before processing.
This makes claimed work visible and recoverable if the process dies.

## Projection flow

The worker composes two explicit services with no compatibility facade:

- `TokenRadarProjector` refreshes private source edges/features and builds ranked row candidates.
- `TokenRadarPublisher` owns current publication, downstream dirty fan-out, and exact claim acknowledgement.

For each claimed target they perform:

1. Refresh rank-source edges when social or repair facts changed.
2. Reuse existing edges for market-only changes.
3. Load source rows once per `(window, scope)` in bounded batches; venue is not a feature-input dimension.
4. Overlay the latest market context when required.
5. Build or delete the target feature row once per `(window, scope)`.
6. Derive the target's venue and touch only the `all` plus actual-venue rank sets.
7. Rank the complete active cohort for each touched set.
8. Publish current rows and publication state.
9. Enqueue downstream work from changed ranked content.
10. Acknowledge the exact dirty claim.

Feature mutation, current-row publication, publication-state update, downstream enqueue, and dirty acknowledgement share the publisher-owned transaction.
A failed publication rolls back its savepoint before failure state is recorded.
No partially published rank set is observable.

## Serving read models

`token_radar_current_rows` is keyed by:

```text
(projection_version, window, scope, venue, lane, target_type_key, identity_id)
```

`token_radar_publication_state` is keyed by:

```text
(projection_version, window, scope, venue)
```

Publication takes an advisory transaction lock for the rank set.
A content-derived generation id describes the semantic row set but is not serving identity.
An older publication timestamp cannot replace a newer current set.
If the incoming semantic signature matches current rows, publication updates no serving rows.

`token_radar_target_first_seen` preserves stable first-listing time independently of publication attempts.
Read APIs join current rows to publication state and expose the last good generation whenever one exists. A failed refresh keeps those rows readable while publication metadata reports the failed attempt as stale/degraded.

The public Radar row has one factor payload authority: `factor_snapshot`. Its
`subject` has the exact keys `target_type`, `target_id`, `symbol`,
`target_market_type`, `chain`, `address`, and `pricefeed_id`. Target, market,
attention, score, decision, and source-event fields are not duplicated beside
the snapshot. The transparent factor families are exactly `social_heat`,
`social_propagation`, and `timing_risk`; every score retains facts, component
factors, weight, and data health. `gates`, `normalization`, and `composite`
retain one producer-owned shape, and consumers reject unknown decision values.

Search inspection and Token Case hydrate resolver, identity, current Radar,
profile, market, timeline, and source-post facts only. They do not publish a
generated brief, admission layer, inferred catalyst, or model-derived factor.

## Runtime ownership

`TokenRadarProjectionWorker` is the only runtime writer of Token Radar serving tables.
Manual repair commands enqueue targets; they do not write serving rows directly.

The worker runs bounded interval catch-up. After restart it re-reads publication
state and the dirty queue from PostgreSQL. Correctness does not depend on an
in-memory cursor or a delivered message.
