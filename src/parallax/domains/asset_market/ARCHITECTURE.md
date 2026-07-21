# Asset Market Architecture

> **Scope.** Owns asset identity evidence, the `MarketTick` fact
> model, capture-tier / stream / poll market workers, cache-only live
> market fan-out, profile refresh/current projection, and discovery workers. Global package boundaries live in
> `../../../../docs/ARCHITECTURE.md`; Token Radar projection lives in
> `../token_intel/ARCHITECTURE.md`; public payload shapes live in
> `../../../../docs/CONTRACTS.md`.

Asset Market is the only domain that may call market and identity
providers in the service runtime. It writes the facts that Token Radar
projection and Signal Pulse consume; it does not own ranking, decisions,
or read-model projection.

## Stage Map

| Stage | Code owner | Persisted facts | Invariant |
|-------|------------|-----------------|-----------|
| Asset identity evidence | `identity_evidence_policy.py`, `repositories/identity_evidence_repository.py`, `repositories/registry_repository.py` | `registry_assets`, `asset_identity_evidence`, `asset_identity_current` | Tweet CA mentions, GMGN payloads, OKX symbol candidates, and OKX exact address hits are separate evidence kinds. One deterministic policy selects current canonical symbol/name/confidence. Repository-owned registry asset, evidence, and current identity mutations require a callable connection transaction before SQL; worker/ingest/reprocess paths keep these writes caller-owned inside `RepositorySession.transaction` or ingest `unit_of_work`. Registry asset upserts require `RETURNING` rowcount=1 plus a returned row; fallback readback is not write evidence. Current identity `RETURNING true AS changed` booleans require PostgreSQL rowcount evidence matching returned-row presence before `rows_written` is reported. |
| Event market capture | `services/event_market_capture.py`, ingest runtime | `market_ticks(source_tier='tier3_inline')`, `enriched_events`; `event_anchor_backfill_jobs` control rows for missing anchors | Ingest captures an event-adjacent market sample from existing ticks only, then commits event facts and tick facts together. Capture commit accepts only formal `CaptureResult` or `EnrichedEventCapture` DTOs; loose result-like objects are malformed ingest input. Missing anchors are queued in the control plane, not by scanning fact rows. Pending-job active lifetime comes from the formal `event_anchor_backfill.active_window_ms` worker setting; ingest service/helpers must not keep their own `300_000` ms default. |
| Event anchor backfill | `runtime/event_anchor_backfill_worker.py`, `repositories/event_anchor_backfill_job_repository.py`, `repositories/enriched_event_repository.py` | `market_ticks`, narrow `enriched_events` lifecycle updates, `event_anchor_backfill_jobs` control state | Consumes due jobs, first attaches a persisted tick near event time, calls providers only inside the anchor lag budget, and terminalizes expired or unavailable anchors. Stale cleanup terminalizes job rows and matching `enriched_events` lifecycle state inside worker-session `unit_of_work`; missing UoW support fails before cleanup writes and must not fall back to manual commit. Repository terminal paths also require a connection transaction before writing job terminal state or terminal ledger rows; missing transaction support is a contract failure, not a `nullcontext` fallback. Temporary retry, done, and terminal guards require the positive claimed-row `attempt_count` and do not restore malformed job rows to zero attempts. Terminal retry from Queue Terminal must reopen the job with an active window derived from the persisted terminal source snapshot, not requeue it at an already-expired boundary. `event_anchor_backfill_jobs` `UPDATE ... RETURNING` paths for claim, stale cleanup, terminal retry, historical-ready reconcile, done, terminal, and reschedule require PostgreSQL cursor rowcount evidence matching returned rows before worker results, terminal ledger writes, retry rows, reconcile counts, or booleans are reported. `enriched_events` attach/terminal lifecycle writes require PostgreSQL single-row `cursor.rowcount` evidence, so missing or invalid driver evidence cannot be reported as a no-op anchor transition. |
| Market capture tier projection | `runtime/token_capture_tier_worker.py`, `repositories/token_capture_tier_repository.py`, `repositories/token_capture_tier_dirty_target_repository.py` | `token_capture_tier`, `token_capture_tier_dirty_targets` | Dirty targets wake a bounded rank-set recompute. Active Token Radar targets are ranked into stream, poll, or inline-only capture tiers. This table is a rebuildable control plane, not a market fact. Dirty rank-set payloads require formal Token Radar current identity `target_type_key` plus `identity_id`; stale `target_type` / `target_id` aliases cannot override those keys or restore alias-only rows. Dirty rank-set enqueue requires positive producer-supplied `source_watermark_ms`; the repository and ops repair must not repair it from row-level `source_max_received_at_ms`, legacy `source_watermark_ms`, `0`, or runtime `now_ms`. The lease claim commits before projection so a failed projection cannot roll back its attempt counter. Tier row writes/demotions and claim done/error/terminal state then share one `RepositorySession.transaction`; exhausted attempts move to `worker_queue_terminal_events`. A terminal capture-tier snapshot does not contain the ranked row set, so generic queue retry is intentionally unsupported: operators must use the explicit bounded capture-tier rank-set repair command with a valid window; archive/quarantine remain available for the terminal event. `project_once` requires an active transaction and must not commit manually. Repository-owned dirty target enqueue, claim, done, and error mutations require a connection transaction before queue SQL when they own commit. Tier upsert changed booleans, tier demotion, and dirty-target enqueue/done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence; tier `RETURNING true AS changed` rowcount must match returned-row presence before worker `rows_written` is reported. Missing or invalid rowcount fails instead of reporting zero changed capture-tier work. |
| Tier 1 market stream | `runtime/market_tick_stream_worker.py` | `market_ticks(source_tier='tier1_ws')` | Stream targets come from `token_capture_tier(tier=1)`. The worker receives the formal `settings.workers.market_tick_stream` object, DB pool bundle, configured stream provider, and wake emitter from the worker factory; subscription limit and stream cycle cadence are settings fields, not constructor overrides or runtime defaults. Provider IO never holds a DB session. Each bounded stream cycle closes the async price iterator through direct `aclose()`; missing iterator `aclose()` is degraded stream contract evidence, not a no-op cleanup fallback. |
| Tier 2 market poll | `runtime/market_tick_poll_worker.py` | `market_ticks(source_tier='tier2_poll')` | Poll targets come from `token_capture_tier(tier=2)`. DEX and CEX provider calls run outside DB sessions. The worker reads the formal Asset Market provider-bundle fields `dex_quote_market` and `cex_market` directly; missing fields are malformed runtime wiring, while present `None` values represent unavailable concrete providers. |
| Market tick current projection | `runtime/market_tick_current_projection_worker.py`, `repositories/market_tick_current_repository.py`, `repositories/market_tick_current_dirty_target_repository.py` | `market_tick_current`, `market_tick_current_dirty_targets`, downstream `token_radar_dirty_targets` | Claims due dirty targets, selects the latest append-only `market_ticks` fact per target, and writes one stable current market row only when the visible tick changes. The worker reads statement timeout, batch size, lease, retry cadence, and retry budget from `settings.workers.market_tick_current_projection` directly; runtime default constants and settings fallback probes are not part of this contract. Dirty target enqueue, claim, done, and error mutations require a connection transaction when the repository owns commit; missing transaction support fails before queue SQL instead of falling back to manual commit. Done/error completion keys require positive claimed-row `attempt_count`; malformed keys fail before SQL rather than being restored to zero attempts. Error mutations before the retry budget reschedule the claimed row; exhausted claims delete the dirty row with `RETURNING queue.*` and write `worker_queue_terminal_events` in the same transaction. Queue Terminal retry requeues terminal snapshots through the formal dirty-target repository. Enqueue and done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting zero changed market-current targets or candidate dirty width. Repository-owned `market_tick_current` upsert `RETURNING true AS changed` results require PostgreSQL rowcount evidence matching returned-row presence before changed booleans, downstream dirty enqueue decisions, or wake counts are reported. |
| Live market fan-out | `runtime/live_price_gateway.py` | in-process cache only | Reads the bounded live target set from `token_capture_tier`, then updates process-local latest state and WebSocket subscribers through the async WebSocket hub `publish(payload)` contract. Target limit and tick TTL are formal `settings.workers.live_price_gateway` fields. The gateway does not write market facts, scan Token Radar current rows, own upstream price providers, or accept synchronous publish callbacks as a compatibility shape. |
| DEX profile source refresh | `runtime/asset_profile_refresh_worker.py`, `services/asset_profile_refresh.py`, `repositories/asset_profile_repository.py`, `repositories/asset_profile_refresh_target_repository.py` | `asset_profiles`, `asset_profile_refresh_targets`, `token_profile_current_dirty_targets` | Resolved DEX assets are enriched only after a provider-scoped dirty target is claimed. `asset_profiles` is a provider source cache, not the public profile read model. The worker reads statement timeout, batch size, lease, provider-block retry cadence, and ready/missing/error source-cache refresh cadences from `settings.workers.asset_profile_refresh` directly; runtime default constants, repository refresh constants, service-local refresh policy, and settings fallback probes are not part of this contract. The normal worker loop consumes only due `asset_profile_refresh_targets` and performs no Token Radar discovery scan when the queue is empty. `ops refresh-asset-profiles` owns the bounded repair discovery from stable `token_radar_current_rows` Asset identities in the default `all` venue; it excludes existing source-cache rows and active refresh targets and carries the current row's positive `source_max_received_at_ms` into the queue. The worker computes the next ready/missing/error refresh time once and passes it explicitly to both `asset_profiles.next_refresh_at_ms` writes and `asset_profile_refresh_targets.due_at_ms` reschedules. Source fact changes wake profile-current projection with the claimed source watermark; this worker does not own image admission and must not repair missing profile-current dirty source watermarks with `now_ms`. Refresh target enqueue requires positive producer-supplied `source_watermark_ms` and must not repair it from source-cache `updated_at_ms` or runtime `now_ms`. Refresh target enqueue, ops repair discovery, claim, reschedule, and error mutations require a connection transaction when the repository owns commit; enqueue/reschedule/error changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting input width or zero changed refresh targets. Reschedule/error completion keys require positive claimed-row `attempt_count` and do not restore malformed keys to zero attempts. Repository-owned `asset_profiles` ready/status writes require the same connection transaction before source-cache SQL. Worker service writes keep `commit=False` inside `RepositorySession.transaction`. Missing transaction support fails before SQL instead of falling back to manual commit. |
| Token image mirror | `runtime/token_image_mirror_worker.py`, `services/token_image_mirror.py`, `repositories/token_image_asset_repository.py`, `repositories/token_image_source_dirty_target_repository.py` | `token_image_assets`, `token_image_source_dirty_targets`, local files under `cache/token-images` | Reads due `token_image_source_dirty_targets` only and does not scan source tables. Provider logo URLs from dirty source rows are mirrored into local media. The worker reads statement timeout, batch size, lease, retry cadence, and retry budget from `settings.workers.token_image_mirror` directly; runtime default constants, service-local retry defaults, and settings fallback probes are not part of this contract. Dirty source enqueue requires positive producer-supplied `source_watermark_ms` and must not repair it from target-level `observed_at_ms`, source-row `updated_at_ms`, or runtime `now_ms`. Dirty source enqueue, claim, done, and error mutations require a connection transaction when the repository owns commit; done/error completion keys require positive claimed-row `attempt_count`, non-empty claimed-row `lease_owner`, claimed `payload_hash`, and claimed `source_url_hash`; malformed keys fail before SQL instead of being restored to zero attempts, empty owners, empty payloads, or a URL-derived source hash. Error mutations before the retry budget reschedule the claimed row; exhausted claims delete the dirty row and write `worker_queue_terminal_events` with `image_mirror_retry_budget_exhausted` evidence in the same transaction. Unresolved terminal events are queried by exact `source_url_hash:target_type:target_id` and block source re-admission until operator action. Done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting zero changed image-source targets. Repository-owned `token_image_assets` pending/ready/error/unsupported lifecycle mutations also require a connection transaction, PostgreSQL single-row rowcount evidence, and worker-settings retry cadence; pending/ready RETURNING paths require rowcount to match returned-row presence before affected counts or ready rows are reported. Worker mirror terminal writes use `RepositorySession.transaction` with caller-owned `commit=False`. Missing transaction support fails before SQL instead of falling back to manual commit. Only ready local rows may become public logo URLs; provider URLs are never served directly. |
| Token profile current projection | `runtime/token_profile_current_worker.py`, `services/token_profile_current_projection.py`, `repositories/token_profile_current_repository.py`, `repositories/token_profile_current_dirty_target_repository.py`, `repositories/token_image_source_dirty_target_repository.py`, `queries/token_profile_source_query.py` | `token_profile_current`, `token_profile_current_dirty_targets`, `token_image_source_dirty_targets` | Public profile/icon facts are projected after claiming dirty target ids and exact-loading persisted GMGN OpenAPI rows, Binance Web3 rows, GMGN stream exact snapshot evidence, OKX DEX exact-address evidence, `cex_token_profiles`, full lifecycle `token_image_assets` states, existing image dirty targets, and unresolved image mirror terminal events through the formal `RepositorySession.source_query` contract. Source rows and image state are loaded once per batch, then each claim publishes and completes in its own transaction so one malformed target cannot roll back or terminalize valid peers. The worker reads profile-current statement timeout, batch size, lease, retry cadence, and max-attempt budget from `settings.workers.token_profile_current`; helper calls must pass those values explicitly and must not use runtime default constants. Missing source-query support is a worker/session contract failure, not a reason to construct an ad hoc query from `repos.conn`. Dirty target enqueue requires mapping-shaped targets with positive `source_watermark_ms`; `TokenProfileCurrentDirtyTargetRepository`, ops image repair, Asset Profile refresh, and Token Image Mirror must not repair missing watermarks from `computed_at_ms`, `updated_at_ms`, tuple target identity, or runtime `now_ms`. Image-source admission for Token Image Mirror requires positive source-row `observed_at_ms` and must not repair image-source dirty watermarks from `updated_at_ms`, target-level `observed_at_ms`, or runtime `now_ms`. Dirty target claim, done, and error mutations require a connection transaction when the repository owns commit; done/error completion keys require positive claimed-row `attempt_count` and do not restore malformed keys to zero attempts; exhausted claims are deleted and copied to `worker_queue_terminal_events`; done/error changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting zero changed profile-current targets. Repository-owned `token_profile_current` upsert also requires a connection transaction before serving-row SQL, requires formal `quality_flags_json` and `source_payload_json` row fields without accepting old `quality_flags` / `source_payload` aliases, and its `RETURNING true AS changed` path requires PostgreSQL rowcount evidence matching returned-row presence before changed booleans or worker `rows_written` are reported. Missing transaction support fails before SQL instead of falling back to manual commit. It writes image source dirty targets for usable logo candidates only when there is no active dirty target and no unresolved image terminal event. Public `TokenProfileReadModel` may synthesize pending/unsupported blocks only when the current row is absent; present rows must carry formal `status`, `source_kind`, `quality_flags_json`, and `source_payload_json` fields and cannot be laundered into pending, empty flags, or empty source payloads. CEX profile absence is explicit `unsupported`; no symbol-only DEX icon matching; no remote logo URL fallback. |
| Resolution refresh and discovery | `runtime/resolution_refresh_worker.py`, `repositories/discovery_repository.py`, `repositories/registry_repository.py` | `token_discovery_dirty_lookup_keys`, refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results` | Intent writes and reprocess paths enqueue unresolved lookup keys. The worker claims due queue rows, refreshes them through OKX DEX, then reprocesses affected intents. It reads chain ids, retry budget, claim batch size, lookup lease/running timeout, hot not-found retry cadence, and reprocess limit from `settings.workers.resolution_refresh` directly; constructor chain overrides, unused quote providers, wake aliases, settings fallback probes, repository-local lookup timing constants, read-only due-lookup peek helpers, and service-local reprocess limit/window defaults are not part of this contract. Affected reprocess uses `TOKEN_REPROCESS_WINDOW` plus the formal `reprocess_limit`, and the token reprocess/rebuild helpers require explicit window/limit arguments. Reprocessed resolved event edges enqueue Token Radar source-dirty rows from formal `TokenIntentResolutionDecision` results only; malformed loose resolver objects fail before source-dirty enqueue and are not treated as empty dirty work. It does not scan recent facts or call a read-only due-list helper to find due lookup keys; due work is consumed only by `claim_due_lookup_keys(...)`. DiscoveryRepository repository-owned lookup queue/result enqueue/claim/done/reschedule/start/finish/fail mutations require a callable connection transaction before SQL; due/claim/start lookup timing is passed explicitly from worker settings rather than module constants. Lookup queue enqueue/done/reschedule changed-row counts require PostgreSQL `cursor.rowcount` evidence and fail on missing or invalid rowcount instead of reporting zero changed lookup work. Lookup claim done/reschedule/terminal completion keys and worker retry-budget decisions require positive claimed-row `attempt_count`, while completion keys also require non-empty `lease_owner` and claimed `payload_hash`; malformed keys must not be restored to zero attempts, empty owners, or empty payloads. Provider-unavailable batch handling uses the same retry budget as provider-error and not-found completion: retryable claimed rows are rescheduled, while exhausted claimed rows are deleted and terminalized instead of being re-admitted indefinitely. Lookup running/finish/fail/claim completion writes require `RepositorySession.transaction`; provider IO stays outside the transaction and runtime code must not fall back to direct `repos.conn.commit()`. Repository-owned registry asset writes require a callable connection transaction before SQL and require `RETURNING` rowcount=1 with a returned row before facts are returned; worker/reprocess paths pass `commit=False` inside their outer transaction. Terminal lookup-claim delete and terminal-ledger writes require connection transaction and the deleted queue source row `payload_hash`; missing transaction or source payload-hash support fails before delete/ledger SQL instead of using `nullcontext`, manual commit, or empty terminal signatures. Successful refresh emits `resolution_updated` so downstream readers wake; the worker itself does not run inline Token Radar projection. |
| CEX route and profile sync | `services/asset_market_sync.py`, `services/cex_token_profile_sync.py`, `repositories/registry_repository.py`, `repositories/cex_token_profile_repository.py` | `cex_tokens`, `price_feeds`, `cex_token_profiles` | Maintains token/feed routing without refreshing prices. Binance CEX profiles enrich existing routed CEX tokens through a separate source cache; they do not create CEX routes or call providers from public reads. Provider/client reads happen outside DB transactions; route/feed/profile DB writes share a callable connection transaction and must not fall back to naked `conn.commit()`. Binance route sync consumes formal `BinanceUsdtPerpRoute` DTOs produced by the app-layer Binance adapter; loose objects with `native_market_id` / `base_symbol` / `quote_symbol` attributes are malformed route input, not compatibility data. Binance CEX profile provider output is a formal mapping record with required `base_symbol`, `provider`, `symbol`, `logo_url`, `source_ref`, and mapping-shaped `raw_payload`; object-attribute reflection, missing-provider defaults, symbol-from-base fallbacks, and empty raw-payload defaults are malformed provider output rather than compatibility input. Binance route dry-run/execute plan counts read persisted route/feed deltas only through `RegistryRepository.binance_usdt_perp_sync_plan_counts(...)`; missing method support is a repository contract failure, not an input-count estimate. Repository-owned CEX token and price-feed writes in `RegistryRepository` and repository-owned `cex_token_profiles` source-cache writes in `CexTokenProfileRepository` also require callable connection transaction before SQL. CEX token and price-feed upserts require `RETURNING *` rowcount=1 plus a returned row before route/feed facts are returned. CEX profile source-cache upserts validate optional single-row `RETURNING` rowcount evidence: rowcount=0/no row is the only valid no-existing-token result, and rowcount=1/row is the only valid source-cache write result. |
| US equity symbol sync | `services/us_equity_symbol_sync.py`, `repositories/registry_repository.py` | `us_equity_symbols` and market-instrument ids | Confirms US equity symbols so the deterministic resolver can elevate them above DEX same-symbol assets. Nasdaq Trader file fetch/parse happens outside the DB transaction; symbol upsert/deactivation writes share a callable connection transaction and must not fall back to naked `conn.commit()`. Repository-owned US equity symbol upsert/deactivation writes in `RegistryRepository` also require callable connection transaction before SQL. US equity symbol upserts require `RETURNING *` rowcount=1 plus a returned row before symbol facts are returned. US equity symbol deactivation counts from `UPDATE ... RETURNING symbol` require cursor rowcount evidence and the rowcount must match returned symbols before deactivation counts are reported. |

Asset Market dirty completion keys preserve the claimed-row CAS fields across
market-current, profile-current, image-source, asset-profile-refresh, discovery
lookup, and event-anchor queues: `attempt_count` must be valid and `lease_owner`
must be non-empty; dirty queues that carry payload hashes also require
`payload_hash` before done/error/reschedule SQL. Image-source completion also
requires the claimed `source_url_hash` target key and must not rebuild it from
`source_url`. Missing claim fields are malformed queue state, not zero-attempt,
empty-owner, empty-payload, or URL-derived compatibility tokens.
Asset Market dirty-target claim `UPDATE ... RETURNING` paths also require
PostgreSQL cursor rowcount to match returned claimed rows before worker payload
loading, provider IO, or projection work treats the rows as claimed.
Discovery terminal-ledger evidence also preserves the deleted lookup source row
`payload_hash`; missing source hashes fail before `worker_queue_terminal_events`
SQL instead of being recorded as empty terminal signatures. Terminal lookup
delete counts also require PostgreSQL `cursor.rowcount` evidence, and rowcount
must match returned deleted lookup rows before terminal ledger writes or terminal
counts are reported.

## MarketTick Schema

`domains/asset_market/types/market_tick.py` defines the cross-domain
market fact contract. All providers normalise into this frozen value
type before any persistence call.

- `market_ticks` are append-only provider tick facts. Rows are not updated
  into a current-market table, and provider frames that never become ticks are
  not business facts.
- `target_type` is `chain_token` or `cex_symbol`.
- `target_id` is the deterministic market target key, such as
  `solana:<address>` or `binance:<symbol>USDT`.
- `source_tier` records whether the sample came from Tier 1 stream,
  Tier 2 poll, or inline event capture.
- `source_provider` records the concrete provider path, such as
  `okx_dex_ws`, `okx_dex_rest`, or `binance_cex_rest`.
- Numeric market fields are optional except `price_usd`, which must be a
  positive finite decimal. CEX derivatives scalars such as
  `open_interest_usd` belong on the tick only when normalized as scalar market
  facts for the same instrument/observation.
- CEX liquidation levels / heatmap zones are not tick facts. CoinGlass-derived
  level snapshots should enter through an Asset Market provider + append-only
  derivatives snapshot table with one runtime writer, then be copied into Token
  Case and Pulse evidence packets from persisted facts. Public reads and agents
  must not shell out to CoinGlass directly.
- `raw_payload_json` stores the provider payload needed for audit without
  making provider frames the business fact.

## Capture Roles

- Inline event capture answers "what market sample was observed close to
  this event commit?" It writes Tier 3 ticks and the event projection rows
  committed with `events`.
- Tier 1 stream capture keeps the hottest live targets fresh with OKX DEX
  WebSocket samples. `MarketTickStreamWorker` writes these ticks as
  `market_ticks(source_tier='tier1_ws')`.
- Tier 2 poll capture keeps the broader active set fresh through OKX DEX
  and CEX quote providers. `MarketTickPollWorker` writes these ticks as
  `market_ticks(source_tier='tier2_poll')`.
- All market tick capture lanes use append-only `market_ticks`
  `INSERT ... DO NOTHING RETURNING tick_id` writes. Created-vs-duplicate
  classification requires PostgreSQL cursor rowcount evidence matching
  returned-row presence: rowcount=1 with a row is inserted, rowcount=0 with no
  row is deduped, and missing, invalid, multi-row, or mismatched evidence is a
  repository/driver contract failure.
- `market_tick_current` is a rebuildable current read model with one runtime
  writer: `MarketTickCurrentProjectionWorker`. Its dirty target repository
  requires a connection transaction for enqueue, claim, done, and error
  mutations whenever the repository owns commit; missing transaction support
  fails before `market_tick_current_dirty_targets` SQL instead of falling back
  to manual `self.conn.commit()`. Current-row upsert changed booleans require
  PostgreSQL rowcount evidence matching returned-row presence.
- `token_capture_tier` is a rebuildable projection with one runtime writer:
  `TokenCaptureTierWorker`. Its dirty target claim, tier write/demotion, and
  dirty target done state run inside one `RepositorySession.transaction`;
  missing session transaction support fails before claim/write instead of
  falling back to manual commit. Tier demotion changed-row accounting requires
  PostgreSQL `cursor.rowcount` evidence and fails on missing or invalid
  rowcount instead of reporting zero demoted rows. Tier upsert changed booleans
  also require rowcount evidence matching `RETURNING` row presence.
- Event-anchor terminal transitions write `event_anchor_backfill_jobs` and the
  worker terminal ledger inside the repository connection transaction. Missing
  connection transaction support fails before terminal SQL and must not be
  hidden by `nullcontext`. Claimed job retry/done/terminal guards require a
  positive `attempt_count` from the claimed row.
- Event-anchor `enriched_events` attach/terminal lifecycle transitions require
  PostgreSQL single-row `cursor.rowcount` evidence. Missing, boolean, negative,
  multi-row, or otherwise invalid rowcount fails before the repository reports a
  no-op, attach, or terminal state change.
- Resolution-refresh terminal transitions delete claimed
  `token_discovery_dirty_lookup_keys` rows and write the worker terminal ledger
  inside the repository connection transaction. Missing connection transaction
  support fails before delete/ledger SQL and must not be hidden by `nullcontext`
  or manual commit. Retry-budget decisions require the same positive claimed-row
  `attempt_count`; terminal evidence also requires the deleted lookup source row
  `payload_hash` before ledger SQL. Terminal delete rowcount must match returned
  deleted lookup rows before `worker_queue_terminal_events` writes.
- DiscoveryRepository ordinary lookup queue/result mutations - enqueue, claim,
  done, reschedule, start, finish, and fail - also require a callable
  connection transaction when the repository owns commit. Missing connection
  transaction support fails before queue/result SQL and cannot be hidden by
  manual `self.conn.commit()` compatibility. Lookup queue enqueue/done/reschedule
  changed-row accounting requires PostgreSQL `cursor.rowcount` evidence and
  fails on missing or invalid rowcount instead of reporting zero changed lookup
  work. Due-lookup claims validate rowcount against returned claim rows before
  work is treated as leased; lookup result start/fail writes return through
  required `RETURNING *` rowcount=1 evidence, and finish writes require
  rowcount=1 before changed result state is reported. Write-after-readback is
  not a discovery result-state proof.
- LivePriceGateway is presentation-only cache and WebSocket fan-out; it
  is not a fact writer, reads target limit / tick TTL from formal worker
  settings, and its fan-out callback is the async WebSocket hub publish
  contract rather than a sync/async dual-shape callback.
- Token Case and Search Inspect read market-live state from persisted current
  market tick facts through the Token Intel target repository. Missing rows are
  product missing state; missing repository support is a backend contract
  failure and must not be hidden as a missing market snapshot.

## Provider Capability Model

`providers.py` exposes narrow protocols; there is no `MarketDataSource`
god interface.

- `MarketCapability` enum: `QUOTE_CEX`, `QUOTE_DEX_EXACT`, `STREAM_DEX`,
  `SEARCH_DEX`, `PROFILE_DEX_EXACT`, `CANDLES_DEX_EXACT`.
- `ProviderHealth(provider, capabilities, configured, last_error)` —
  health reports the configured capabilities, not every capability the
  provider could theoretically support. Keep health aligned with actual
  wiring.
- `DexMarketStreamProvider.connection_state_payload()` is a formal runtime
  contract for configured streaming providers. Market stream worker degraded
  notes, readiness, ops diagnostics, and OKX adapter wiring call it directly;
  missing or malformed state payloads are failed provider state.
- Configured provider instances are not optional capability bags. If GMGN
  OpenAPI is configured and `gmgn_dex_market(...)` returns a provider object,
  it must expose both `token_quotes(...)` and `token_profile(...)`; malformed
  objects fail wiring instead of silently falling back to OKX quotes or dropping
  the GMGN profile source.
- Startup failure cleanup is not a looser compatibility path. Once an
  `OkxProviderBundle` object exists, Asset Market cleanup reads its
  `dex_discovery_market`, `dex_quote_market`, and `stream_dex_market` fields
  directly and records malformed bundle shape as cleanup evidence on the
  original startup error.

Concrete provider clients (Binance USD-M CEX, OKX DEX, OKX DEX WS,
GMGN OpenAPI, GMGN direct WS, macrodata-cli) are wired in
`app/runtime/providers_wiring.py`. Asset Market services and workers
receive provider protocols by injection and may not import
`integrations/*`.
If `asset_profile_refresh` or `resolution_refresh` is enabled but its required
profile/discovery provider is absent, the worker factory must surface an
`unavailable` sentinel worker with a redacted missing-provider reason. It must
not mark the worker `disabled`, because disabled means operator intent and
would hide a broken fact-refresh lane from readiness.

## Wake Channels

| Channel | Emitter | Listener |
|---------|---------|----------|
| `market_tick_written` | `MarketTickStreamWorker`, `MarketTickPollWorker`, `EventAnchorBackfillWorker` | `MarketTickCurrentProjectionWorker` |
| `market_tick_current_updated` | `MarketTickCurrentProjectionWorker` | `TokenRadarProjectionWorker` |
| `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` |

Market tick writers append `market_ticks` and emit `market_tick_written`;
`MarketTickCurrentProjectionWorker` owns `market_tick_current` and emits
`market_tick_current_updated` only after the current row changes. Wake channels
are hints; listeners re-read the database and catch up by their configured
interval by claiming durable queues or reading bounded read models, not by
scanning recent facts. Wake mechanics are composed in
`app/runtime/bootstrap.py` through `DBPoolBundle.wake_emitter()` and
`wake_listener()`. Asset Market workers receive wake dependencies by injection;
they never call `pg_notify` directly. See `../../../../docs/WORKERS.md` for the
cross-domain inventory.

## Hard Boundaries

- Provider raw frames never reach `factor_snapshot_json`. Token Radar
  projection reads `market_ticks` and `enriched_events`, not provider clients.
- `event_anchor_backfill_jobs` is worker control state. Product surfaces and
  Token Radar never read it; they read the terminal or ready event-anchor fact
  in `enriched_events`.
- Identity evidence and asset identity selection never feed scoring
  families. They are gates and `data_health` inputs only.
- `LivePriceGateway` may fan out raw frames to WS for recent display through
  the async hub publish contract, but Token Radar business state comes from
  persisted market tick facts.
- CLI ops commands may instantiate concrete provider clients for explicit
  operator commands; service runtime wiring stays centralised in
  `app/runtime/providers_wiring.py`.
- LLM enrichment may label watched social events, but token identity
  resolution stays deterministic and does not call an LLM in the hot
  path.
- Provider logo URLs are mirror inputs only. Public profile reads expose
  `identity.logo_url` as `NULL` or `/api/token-images/{image_id}`; no
  frontend or API path may call GMGN, Binance, OKX, or CEX image URLs directly.

## Update Triggers

Update this file in the same change as any of:

- `MarketTick` / market context / market readiness schema.
- A new market tick persistence trigger or capture-tier threshold.
- A new market `MarketCapability` value or `ProviderHealth` field.
- A worker gaining or losing a wake-in or wake-out channel.
- Asset identity evidence kinds or the policy that selects current
  identity.
- Discovery admission, retained candidate, or reprocess behaviour visible
  to Token Radar.
