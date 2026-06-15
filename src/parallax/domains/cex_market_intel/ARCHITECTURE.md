# CEX Market Intel Architecture

`cex_market_intel` owns derived centralized-exchange market read models. It does
not own provider identity, live WebSocket market ticks, social evidence, or agent
decisions.

## Read Models

- `cex_oi_radar_rows` and `cex_oi_radar_publication_state` power the
  market-wide Binance USDT perpetual OI/radar board as current-only rows.
- `cex_detail_snapshots` powers single-token CEX detail pages and Signal Pulse
  market evidence for CEX targets.
- `cex_derivative_series` is bounded derivative history storage for normalized
  points that can be rebuilt from worker fetches. Provider history fetches can
  overlap previous polls, so unchanged conflict rows must be skipped with
  `IS DISTINCT FROM` guards and required `cursor.rowcount` evidence instead of
  unconditional `DO UPDATE` write amplification. Missing, boolean, negative, or
  non-integer cursor rowcount is malformed driver/wiring state, not a default
  one-row write or no-op count.
  Series identity requires non-empty provider, exchange, native market id,
  metric, and period before hash construction or SQL; PostgreSQL `NOT NULL` is
  not treated as sufficient for empty text.

## Writer Ownership

`CexOiRadarBoardWorker` is the runtime writer for `cex_oi_radar_rows`,
`cex_oi_radar_publication_state`, and the v1 `cex_detail_snapshots` projection.
API routes, Token Case, and Pulse evidence builders only read these tables.
The worker writes board rows, publication state, detail snapshots, and
attempt-state updates inside `RepositorySession.transaction` with
caller-owned repository writes. Repository-owned CEX read-model writes require
a callable connection transaction before SQL and do not fall back to naked
`self.conn.commit()`.

## Data Flow

1. Offline/operator scripts maintain Binance USDT perpetual instruments in
   `price_feeds` with `subject_type='CexToken'`, `provider='binance'`,
   `feed_type='cex_swap'`, and `quote_symbol='USDT'`.
2. `CexOiRadarBoardWorker` scans that universe on its interval, calls Binance
   ticker/premium/OI endpoints in bounded batches, and publishes the current
   radar board with stable row ids by provider/exchange/period/target.
   The worker is constructed only with a concrete OI market provider; provider
   absence is represented by the worker factory's unavailable sentinel rather
   than by a running worker skip path.
3. For the configured top-K rows, the worker can call `coinglass-cli` through a
   worker-side adapter to fetch OI deltas, CVD, long/short, top trader, and
   liquidation levels. It never does this from API or frontend request handlers.
   Runtime provider wiring gates this adapter from the formal
   `settings.workers.cex_oi_radar_board` block. The worker reads period,
   universe limit, batch size, statement timeout, and CoinGlass enrichment
   limits directly from that formal block. The Binance OI row builder receives
   period and build limit explicitly from the worker and requires selected
   universe routes to carry non-empty `native_market_id` and `base_symbol`
   before Binance provider IO or board-row construction; malformed route
   identity is a failed attempt, not a skipped symbol, empty-base board row, or
   successful empty board. Runtime Binance OI provider wiring maps formal
   integration DTO fields into the domain provider DTOs (`CexOiTicker24h`,
   `CexFundingPremium`, and `CexOpenInterestPoint`) and fails malformed
   integration rows before returning those DTOs. The Binance OI builder then
   consumes the domain provider DTOs through their formal fields; an object
   returned by a provider sequence but missing one of those fields is malformed
   provider adapter output, not a `None` metric fallback. When Binance history
   lacks a provider observation timestamp, the builder marks the timestamp as
   `observed_at_source="computed"`;
   that fallback is publication/attempt metadata only and must not enter the
   board payload hash or force serving-row rewrites. The CoinGlass enrichment
   service receives the liquidation level-band limit explicitly from the worker
   and requires row `base_symbol` before CoinGlass provider IO; missing base is
   malformed board-row identity, not `coinglass_status='unavailable'`. The
   enrichment service emits formal `coinglass_status` on every row it returns,
   including `unavailable` when CoinGlass is unconfigured, disabled, or the row
   is outside the configured enrichment budget; the detail builder validates
   this status instead of defaulting it.
   Neither service owns local execution-budget defaults. A missing field is
   malformed runtime configuration, not an implicit disabled, zero-enrichment,
   default-level, default-limit, or default-period state.
4. The worker converts each radar row into a `cex_detail_snapshots` row. The
   detail builder receives the exchange and period explicitly from the worker
   and requires non-empty exchange, period, `native_market_id`, plus stable CEX
   target identity before constructing the current snapshot or mapping OI delta
   slots; route-like Binance market ids, missing periods, and
   `cex_token:unknown` are malformed identity, not fallback targets.
   Missing CoinGlass fields are represented as `coinglass_status='unavailable'`
   or `partial` plus degraded reasons.
5. `/api/token-case`, `/api/search/inspect`, `/api/cex/detail`, and Signal
   Pulse read snapshots from PostgreSQL. They never call Binance or CoinGlass
   on the request path.

## Product Contract

The board and detail snapshots are intentionally compact current read models.
The board is one row per provider/exchange/period/target plus one publication
state row; detail is one current row per exchange and native market. They can be
deleted and rebuilt. They should contain enough bounded context for a CEX board,
detail rail, and agent evidence packet, but not unbounded run history or
intraday history.
`cex_oi_radar_rows` write and payload-hash boundaries use provider-observed
market freshness only. The repository requires non-empty `period`, `target_id`,
`native_market_id`, `base_symbol`, and `quote_symbol` plus a formal
`observed_at_ms` / `observed_at_source` tuple before board key construction,
row-id hashing, payload hashing, or upsert SQL. `observed_at_source` is limited
to `provider` or `computed`; missing or unknown source is malformed writer
output, not provider freshness. Computed fallback observed timestamps and
successful empty board attempt times are not content signatures; unchanged
projections must record attempt state at most and write zero serving rows.
`score_components` is a formal scoring-stage output required before board
payload hashing or upsert SQL; missing components are malformed writer output,
not an empty JSON object fallback.
Board delete/upsert write accounting requires real PostgreSQL `cursor.rowcount`
evidence instead of repository-owned default counts; boolean, negative, or
non-integer rowcount values fail before CEX board write counts are returned.
`/api/cex/radar-board` preserves that repository payload contract: `rows` must
be present as a list, and each row must carry mapping-shaped
`score_components_json`; the route must not synthesize empty rows or empty score
components when repository output is malformed.
`cex_detail_snapshots` write and payload-hash boundaries require formal
`snapshot_id`, `target_type`, `target_id`, `exchange`, and `native_market_id`
fields plus non-empty `base_symbol` and `quote_symbol`. `status`,
`baseline_status`, and `coinglass_status` are also formal writer-output enum
fields before detail snapshot construction, payload hash, or upsert SQL. The
repository and builder must not restore missing identity, market symbols,
period, or states through local `CexToken`, `binance`, `unknown`, empty string,
`USDT`, `partial`, `missing`, or `unavailable` defaults; malformed detail
identity, period, or status fails before serving-row SQL. The builder must not
emit empty native-market snapshot ids, route ids as CEX token identity,
`cex_token:unknown` placeholders, builder-local `binance` exchange fallbacks,
builder-local unknown-period degraded reasons, or builder-local
base/quote/status defaults. The Binance worker passes `exchange="binance"`
explicitly when it builds detail snapshots. Detail snapshot upsert write
accounting requires real PostgreSQL `cursor.rowcount` evidence instead of
default no-op counts; boolean, negative, or non-integer rowcount values fail
before CEX detail write counts are returned. Detail payload hashes use only the formal writer fields
`level_bands`, `degraded_reasons`, and `source_refs`;
legacy DB column aliases such as `level_bands_json`,
`degraded_reasons_json`, and `source_refs_json` are rejected on writer input and
are allowed only inside the repository read-row to public-payload mapping. The
detail builder also rejects `level_bands_json` so storage-column aliases cannot
be laundered back into the board/enrichment DTO shape. When the builder receives
`level_bands`, each band must carry formal `kind` and numeric `price` before
source refs or snapshot payload are built; missing kind cannot become `level`,
and missing price cannot be silently skipped. The builder and CoinGlass
enrichment stage also treat present `degraded_reasons` as a formal string-list
contract; scalar strings, mappings, non-string items, or blank items are
malformed writer/enrichment output rather than compatibility reasons to coerce.
The same builder requires formal
`observed_at_ms` and `observed_at_source=provider|computed` from the
board/enrichment row and must not infer observation source by comparing
timestamps with `computed_at_ms`. The detail repository payload hash applies the
same rule whenever `observed_at_ms` is present, so direct repository callers
cannot rely on timestamp equality to recover a missing source. The repository
also requires `level_bands`, `degraded_reasons`, and `source_refs` to be present
and list-shaped before payload hashing or SQL; missing list fields are
malformed writer output, not empty arrays.
`cex_derivative_series` history identity requires non-empty provider, exchange,
native market id, metric, and period before the `series_id` hash or upsert SQL.
The repository normalizes those key fields once at the boundary so the
PostgreSQL unique business key and primary hash id cannot diverge.
Each derivative history point must also carry a mapping-shaped `raw_payload`
before JSONB upsert; missing or non-mapping raw payload is malformed provider
history output, not an empty JSON object fallback.

If a snapshot has fresh Binance baseline data but no CoinGlass enrichment,
frontend displays a partial CEX panel and Pulse caps the route at `token_watch`.
Only fresh baseline plus derivative/level enrichment can unlock a complete CEX
market contract for trade-candidate analysis.

Token Case and Search Inspect require the `cex_detail_snapshots.latest_snapshot`
repository contract for `CexToken` dossiers. A missing snapshot row is product
state and returns a structured missing detail block without synthetic
`snapshot_id` or `exchange`; a missing repository method or session binding is
a server contract failure. Detail snapshot read methods require non-empty
`target_type` / `target_id` or `exchange` / `native_market_id` query identity
before SQL, so malformed read keys fail at the repository boundary rather than
running empty-string PostgreSQL lookups. `/api/cex/detail` must form the same
paired target or market query identity before calling the repository, rejecting
partial public query params as `invalid_cex_detail_query` rather than returning
`data: null`; if both lookup modes are present, the route rejects the ambiguous
query before opening a repository session instead of silently choosing one
identity.
