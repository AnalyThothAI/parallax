import { AlertTriangle, ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import type { ScopeKey, StockRadarRow, WindowKey } from "../api/types";
import { useStocksRadarQuery } from "../api/useStocksRadarQuery";
import {
  compactNumber,
  formatRelativeTime,
  formatRisk,
  formatSignedPercent,
  formatTokenPriceUsd,
} from "../lib/format";

import { RadarControls } from "./RadarControls";

type StocksRadarPageProps = {
  token: string;
  windowKey: WindowKey;
  scope: ScopeKey;
  onWindowChange: (window: WindowKey) => void;
  onScopeChange: (scope: ScopeKey) => void;
};

export function StocksRadarPage({
  token,
  windowKey,
  scope,
  onWindowChange,
  onScopeChange,
}: StocksRadarPageProps) {
  const query = useStocksRadarQuery({ token, window: windowKey, scope });
  const data = query.data;
  const rows = data?.rows ?? [];
  return (
    <section className="radar-panel stocks-radar-panel" aria-label="US stocks radar">
      <header className="radar-toolbar stocks-radar-toolbar">
        <div>
          <h2>US Stocks</h2>
          <span>
            STOCK RADAR <b>{compactNumber(rows.length)}</b>
          </span>
        </div>
        <div className="stocks-health" aria-label="stocks radar health">
          <span>
            {windowKey} · {scope}
          </span>
          <span>
            quotes <b>{compactNumber(data?.health.quote_ready_count ?? 0)}</b>
          </span>
          <span>
            stale <b>{compactNumber(data?.health.quote_unavailable_count ?? 0)}</b>
          </span>
        </div>
        <div className="stocks-radar-controls" aria-label="stocks radar controls">
          <RadarControls
            scope={scope}
            windowKey={windowKey}
            onScopeChange={onScopeChange}
            onWindowChange={onWindowChange}
          />
        </div>
      </header>

      <div className="token-radar-table stocks-radar-table">
        <div className="radar-head stock-radar-head">
          <span>Symbol</span>
          <span>Mentions</span>
          <span>Authors</span>
          <span>Latest</span>
          <span>Price</span>
          <span>Move</span>
          <span>Quote</span>
        </div>
        {query.isLoading ? <StocksSkeleton /> : null}
        {!query.isLoading && rows.length === 0 ? (
          <div className="table-state">
            {query.isError ? "Stocks radar unavailable" : "No stock flow"}
          </div>
        ) : null}
        {rows.map((row) => (
          <StockRow key={row.target.target_id} row={row} />
        ))}
      </div>
    </section>
  );
}

function StockRow({ row }: { row: StockRadarRow }) {
  const change = row.quote.change_pct;
  const direction =
    change === null || change === undefined
      ? "flat"
      : change > 0
        ? "up"
        : change < 0
          ? "down"
          : "flat";
  const quoteReady = row.quote.status === "ready";
  const quoteLabel = quoteReady ? row.quote.provider || "ready" : formatRisk(row.quote.error);
  return (
    <article className="radar-row stock-radar-row" aria-label={`stock ${row.target.symbol}`}>
      <span className="token-cell stock-token-cell">
        <strong className="token-symbol">
          <span className="symbol-line">
            <span>${row.target.symbol}</span>
          </span>
          <small>
            {[row.target.exchange, row.target.name].filter(Boolean).join(" · ") || "US equity"}
          </small>
        </strong>
      </span>

      <span className="metric stock-mentions-cell" data-radar-metric="heat">
        <b className={row.attention.watched_mentions > 0 ? "score-hot" : "score-warn"}>
          {compactNumber(row.attention.mentions)}
        </b>
        <small>{compactNumber(row.attention.watched_mentions)} watched</small>
      </span>

      <span className="metric stock-authors-cell" data-radar-metric="quality">
        <b>{compactNumber(row.attention.unique_authors)}</b>
        <small>unique authors</small>
      </span>

      <span className="phase stock-latest-cell" data-radar-metric="propagation">
        <b>{row.latest_event.author_handle ? `@${row.latest_event.author_handle}` : "-"}</b>
        <small>{formatRelativeTime(row.latest_event.received_at_ms)} ago</small>
      </span>

      <span className="metric stock-price-cell" data-radar-metric="market">
        <b>{formatTokenPriceUsd(row.quote.price)}</b>
        <small>{row.quote.provider_symbol || row.target.symbol || "US equity"}</small>
      </span>

      <span className="phase stock-move-cell" data-radar-metric="timing">
        <span className="stock-move-line">
          {direction === "up" ? <ArrowUpRight aria-hidden /> : null}
          {direction === "down" ? <ArrowDownRight aria-hidden /> : null}
          {direction === "flat" ? <Minus aria-hidden /> : null}
          <b className={`direction ${direction}`}>{formatSignedPercent(change)}</b>
        </span>
        <small>{moveMeta(row)}</small>
      </span>

      <span className={`stock-quote-cell ${quoteReady ? "ready" : "unavailable"}`}>
        {quoteReady ? null : <AlertTriangle aria-hidden />}
        <b>{quoteLabel}</b>
        <small>{row.quote.latency_class || row.quote.freshness_class || row.quote.status}</small>
      </span>
    </article>
  );
}

function StocksSkeleton() {
  return (
    <div className="radar-skeleton" aria-label="loading stocks radar">
      {Array.from({ length: 8 }, (_, index) => (
        <span key={index} />
      ))}
    </div>
  );
}

function moveMeta(row: StockRadarRow): string {
  if (row.quote.reference_close_price !== null && row.quote.reference_close_price !== undefined) {
    return `prev ${formatTokenPriceUsd(row.quote.reference_close_price)}`;
  }
  if (row.row_health.length > 0) {
    return formatRisk(row.row_health[0]);
  }
  return "quote pending";
}
