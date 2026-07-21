# Asset Market Architecture

Asset Market owns deterministic asset identity, append-only market facts,
current projections, and their durable work queues. Token Radar consumes these
persisted facts; it never calls Asset Market providers.

## Truth and ownership

PostgreSQL is the business truth. Provider responses are inputs until they are
validated and persisted as one of these facts:

- `registry_assets`, `cex_tokens`, `price_feeds`, and `us_equity_symbols` own deterministic identity and routing.
- `asset_identity_evidence` is append-only; `asset_identity_current` is its deterministic current selection.
- `market_ticks` is the append-only normalized market tape.
- `enriched_events` stores the event-adjacent market capture outcome.
- `asset_profiles`, `cex_token_profiles`, and `token_image_assets` are persisted source facts.

The rebuildable serving and control tables are:

- `market_tick_current`, keyed by `(target_type, target_id)`.
- `token_profile_current`, keyed by `(target_type, target_id)`.
- `event_anchor_backfill_jobs`, discovery lookup work, and the surviving
  profile/image dirty-target tables are worker control state rather than
  product facts.

Every current table has one write service. Stable keys contain no run/generation/
attempt/timestamp/UUID identity, and unchanged projections write zero serving rows.

## Runtime lanes

| Lane | Durable input | Single writer / output |
|---|---|---|
| Identity discovery | `token_discovery_dirty_lookup_keys` | `ResolutionRefreshWorker` writes registry assets, identity evidence/current, and discovery results |
| Event capture | committed event and resolution facts | ingest writes an inline `market_tick` and `enriched_events`, or enqueues `event_anchor_backfill_jobs` |
| Event anchor repair | due anchor jobs | `EventAnchorBackfillWorker` writes a tick, capture outcome, job state, and terminal evidence |
| Tier 1 stream | ranked Token Radar chain targets | `MarketTickStreamWorker` appends `market_ticks`, advances `market_tick_current`, and enqueues changed targets |
| Tier 2 poll | ranked Token Radar chain/CEX targets | `MarketTickPollWorker` performs the same fact/current transaction |
| Market current | newly inserted `market_ticks` | `MarketTickPersistenceService` advances the monotonic current row in the fact transaction; the bounded operator rebuild uses the same service against existing facts |
| Asset profile refresh | `asset_profile_refresh_targets` | `AssetProfileRefreshWorker` writes provider-scoped `asset_profiles` and enqueues profile-current work |
| Image mirror | `token_image_source_dirty_targets` | `TokenImageMirrorWorker` writes local `token_image_assets` lifecycle state |
| Profile current | `token_profile_current_dirty_targets` | `TokenProfileCurrentWorker` writes `token_profile_current` and admits missing image work |
| Live fan-out | committed changed current rows | stream/poll publish directly to WebSocket subscribers after commit |

Route, CEX profile, and US-equity sync are operator applications that write facts, not Token Radar projections.

## Transaction boundary

Repositories are pure SQL adapters: no `commit` switch, `commit()` call, or
implicit transaction. The caller owns the boundary with `repos.transaction()`.

The atomic groups are deliberately small:

- A queue claim is committed before slow provider or projection work so an
  attempt cannot disappear when later work fails.
- A successful projection, its downstream dirty enqueue, and its CAS completion
  share one transaction.
- A retry reschedule or exhausted-row delete and terminal-ledger insert share
  one transaction.
- Market tick insert, monotonic current upsert, and Token Radar dirty enqueue
  share one transaction.
- Event-anchor tick/capture/job completion is atomic per claimed job.
- Token-profile source loading may be batched, but publication and completion
  are atomic per claim so one malformed target cannot poison its peers.
- Registry/evidence/current-identity writes for one discovered candidate share
  the resolution worker transaction.
- Route, CEX-profile, and equity-symbol sync services use one application-owned
  `RepositorySession.transaction()` for their database mutations.

Services may assert an existing boundary with `repos.require_transaction()`.
There is no raw commit fallback, repository transaction helper, or compatibility wrapper.

## External I/O

Provider and filesystem I/O never holds a database session:

- stream and poll workers fetch ticks before opening their write transaction;
- resolution lookup calls OKX outside the start/finish persistence boundaries;
- asset profile fetch runs between claim and result transactions;
- image download and file validation run outside DB sessions;
- operator sync clients fetch route/profile/symbol data before their transaction.

Providers use the protocols in `providers.py`; workers do not import concrete
integrations. Missing capabilities are explicit unavailable/degraded state.

## Queue and CAS contract

Durable queues use `FOR UPDATE SKIP LOCKED` claims with bounded batch and lease
settings. A completion must match the claimed stable key plus:

- non-empty `lease_owner`;
- positive `attempt_count`;
- the claimed `payload_hash` where the queue carries one;
- `source_url_hash` for image-source work.

Done, retry, and terminal transitions do not reconstruct missing claim fields.
A stale completion changes zero rows. Exhausted claims are deleted with
`RETURNING` and copied to `worker_queue_terminal_events` in the same caller
transaction. Queue Terminal retry re-enqueues through the current repository
contract; it does not revive a historical run identity.

Mutation counts come from validated `cursor.rowcount`; `RETURNING` rowcount must
equal returned rows. Missing, boolean, negative, or mismatched evidence fails.

Dirty payload hashes describe stable product input, excluding publication-only
timestamps. Re-enqueuing identical work does not churn a serving row; a changed
payload clears stale lease/error state and resets the retry budget where the
queue contract requires it.

## Market fact contract

`types/market_tick.py` defines the frozen cross-domain `MarketTick` value:

- target is `chain_token` or `cex_symbol` with a deterministic `target_id`;
- `source_tier` records stream, poll, or inline capture;
- `source_provider` records the concrete evidence path;
- `price_usd` is positive and finite; other normalized scalar fields are optional;
- `raw_payload_json` preserves audit evidence but is not itself business truth.

Capture lanes use append-only `INSERT ... DO NOTHING RETURNING *`.
`MarketTickPersistenceService` derives `market_tick_current` from rows that
were actually inserted. Older or duplicate facts cannot regress or churn the
current row. A bounded explicit application operation can scan stable target
keys in `market_ticks` and repair missing/stale current rows through the same
service; this recovery path is not a second worker, queue, or writer.
Provider frames never update current state directly.
Structured derivatives require their own append-only fact model and writer.

## Profiles and images

`asset_profiles` and `cex_token_profiles` are source caches.
`token_profile_current` is the public current projection. It exact-loads
persisted sources through `RepositorySession.source_query`; it does not scan
providers or match DEX icons by symbol.

Remote logo URLs are mirror inputs only. Public rows expose `NULL` or a local
`/api/token-images/{image_id}` URL. An unresolved image terminal event blocks
automatic re-admission until an operator acts.

## Catch-up

Workers always re-read PostgreSQL and run bounded interval catch-up.
Correctness depends only on durable facts, queues, and stable read-model keys;
there is no injected wake dependency.

`market_tick_current` is normally maintained in the fact transaction. Operators
repair it with bounded `ops rebuild-market-current` batches over the append-only
fact tape, carrying the returned `(target_type, target_id)` cursor forward until
the batch is no longer full.

## Hard boundaries

- Asset identity is deterministic and does not call an LLM.
- Provider raw frames never enter Token Radar factor snapshots.
- Product reads never expose worker queue rows as business state.
- Live-market REST reads durable `market_tick_current`; WebSocket updates are
  post-commit presentation events, not another cache or business truth.
- Public reads do not call market, profile, image, or discovery providers.
- CLI provider construction is limited to explicit operator commands.

Update this map when a fact, stable key, writer, transaction group, or provider boundary changes.
