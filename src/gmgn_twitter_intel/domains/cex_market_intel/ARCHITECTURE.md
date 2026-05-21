# CEX Market Intel Architecture

`cex_market_intel` owns derived centralized-exchange market read models. It does
not own provider identity, live WebSocket market ticks, social evidence, or agent
decisions.

## Read Models

- `cex_oi_radar_runs` and `cex_oi_radar_rows` power the market-wide Binance USDT
  perpetual OI/radar board.
- `cex_detail_snapshots` powers single-token CEX detail pages and Signal Pulse
  market evidence for CEX targets.
- `cex_derivative_series` is bounded derivative history storage for normalized
  points that can be rebuilt from worker fetches.

## Writer Ownership

`CexOiRadarBoardWorker` is the runtime writer for `cex_oi_radar_runs`,
`cex_oi_radar_rows`, and the v1 `cex_detail_snapshots` projection. API routes,
Token Case, and Pulse evidence builders only read these tables.

## Data Flow

1. Offline/operator scripts maintain Binance USDT perpetual instruments in
   `price_feeds` with `subject_type='CexToken'`, `provider='binance'`,
   `feed_type='cex_swap'`, and `quote_symbol='USDT'`.
2. `CexOiRadarBoardWorker` scans that universe on its interval, calls Binance
   ticker/premium/OI endpoints in bounded batches, and ranks the radar board.
3. For the configured top-K rows, the worker can call `coinglass-cli` through a
   worker-side adapter to fetch OI deltas, CVD, long/short, top trader, and
   liquidation levels. It never does this from API or frontend request handlers.
4. The worker converts each radar row into a `cex_detail_snapshots` row. Missing
   CoinGlass fields are represented as `coinglass_status='unavailable'` or
   `partial` plus degraded reasons.
5. `/api/token-case`, `/api/cex/detail`, and Signal Pulse read snapshots from
   PostgreSQL. They never call Binance or CoinGlass on the request path.

## Product Contract

The detail snapshot is intentionally compact: one current row per exchange and
native market. It can be deleted and rebuilt. It should contain enough bounded
context for a CEX detail rail and an agent evidence packet, but not unbounded
intraday history.

If a snapshot has fresh Binance baseline data but no CoinGlass enrichment,
frontend displays a partial CEX panel and Pulse caps the route at `token_watch`.
Only fresh baseline plus derivative/level enrichment can unlock a complete CEX
market contract for trade-candidate analysis.
