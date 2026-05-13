import {
  formatPercentShare,
  formatPropagationPhase,
  formatRelativeTime,
  formatSignedPercent,
  formatTokenPriceUsd,
} from "@lib/format";
import type { MarketCandle, SearchTokenResult, TokenSocialTimelineData } from "@lib/types";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type LineData,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";


type SearchTimelinePanelProps = {
  timeline: TokenSocialTimelineData;
  marketOverlay: SearchTokenResult["market_overlay"];
  activeStageId: string;
  onStageSelect: (stageId: string) => void;
};

type TimelineChartData = {
  candles: CandlestickData<UTCTimestamp>[];
  anchorLine: LineData<UTCTimestamp>[];
  social: HistogramData<UTCTimestamp>[];
  latestPrice: number | null;
  hasMarket: boolean;
};

export function SearchTimelinePanel({
  timeline,
  marketOverlay,
  activeStageId,
  onStageSelect,
}: SearchTimelinePanelProps) {
  const chartData = useMemo(
    () => buildChartData(timeline, marketOverlay),
    [timeline, marketOverlay],
  );
  const priceSeriesType = String(marketOverlay.price_series_type ?? "anchor_line");
  const candleStatus = String(
    marketOverlay.candle_status ?? (chartData.candles.length ? "ready" : "anchor"),
  );
  const candleBar = String(marketOverlay.candle_bar ?? timeline.query.bucket ?? "");
  const marketLabel = chartData.candles.length
    ? `${candleBar} OHLC`
    : `${priceSeriesType} · ${candleStatus}`;

  return (
    <section className="search-panel search-timeline-panel" id="timeline">
      <header>
        <h3>Social x Market Timeline</h3>
        <span>{marketLabel}</span>
      </header>

      <div className="search-stage-rail" aria-label="stage narrative">
        <button
          className={activeStageId === "all" ? "active" : ""}
          onClick={() => onStageSelect("all")}
          type="button"
        >
          <b>All</b>
          <span>{timeline.summary.posts} posts</span>
        </button>
        {timeline.stages.map((stage) => (
          <button
            className={activeStageId === stage.stage_id ? "active" : ""}
            key={stage.stage_id}
            onClick={() => onStageSelect(stage.stage_id)}
            type="button"
          >
            <b>{formatPropagationPhase(stage.phase)}</b>
            <span>
              {stage.people.posts} posts · {stage.people.authors} authors
            </span>
            <em>{formatSignedPercent(stage.price.delta_pct)}</em>
          </button>
        ))}
      </div>

      <div className="search-chart-shell">
        <div className="search-chart-legend" aria-label="chart legend">
          <span>
            <i className="legend-candle" />
            {chartData.candles.length ? "market candles" : "anchor price"}
          </span>
          <span>
            <i className="legend-social" />
            social posts
          </span>
          <b>
            {chartData.latestPrice === null
              ? "price -"
              : formatTokenPriceUsd(chartData.latestPrice)}
          </b>
        </div>
        <TimelineChart data={chartData} />
        {!chartData.hasMarket ? (
          <div className="search-chart-empty">
            <b>No K-line from provider</b>
            <span>{marketOverlay.candle_error ?? candleStatus}</span>
          </div>
        ) : null}
      </div>

      <div className="search-timeline-summary">
        <span>{timeline.summary.posts} posts</span>
        <span>{timeline.summary.authors} authors</span>
        <span>{timeline.summary.watched_posts ?? 0} watched</span>
        <span>{formatPropagationPhase(timeline.summary.phase)}</span>
        <span>top {formatPercentShare(timeline.summary.top_author_share)}</span>
        <span>
          latest{" "}
          {timeline.summary.latest_seen_ms
            ? `${formatRelativeTime(timeline.summary.latest_seen_ms)} ago`
            : "-"}
        </span>
      </div>
    </section>
  );
}

function TimelineChart({ data }: { data: TimelineChartData }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof ResizeObserver === "undefined" || container.clientWidth <= 0) {
      return;
    }
    if (!data.social.length && !data.candles.length && !data.anchorLine.length) {
      return;
    }

    const chart = createSearchChart(container);
    const socialSeries = chart.addSeries(HistogramSeries, {
      color: "rgba(231, 169, 39, 0.48)",
      lastValueVisible: false,
      priceFormat: { type: "volume" },
      priceLineVisible: false,
      priceScaleId: "social",
    });
    socialSeries.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
    socialSeries.setData(data.social);

    if (data.candles.length) {
      const candleSeries = chart.addSeries(CandlestickSeries, {
        borderDownColor: "#e66f5c",
        borderUpColor: "#55c7ae",
        downColor: "rgba(230, 111, 92, 0.84)",
        priceFormat: { type: "price", precision: 8, minMove: 0.00000001 },
        wickDownColor: "#e66f5c",
        wickUpColor: "#55c7ae",
        upColor: "rgba(85, 199, 174, 0.84)",
      });
      candleSeries.setData(data.candles);
    } else if (data.anchorLine.length) {
      const lineSeries = chart.addSeries(LineSeries, {
        color: "#55c7ae",
        lastValueVisible: false,
        lineWidth: 2,
        priceFormat: { type: "price", precision: 8, minMove: 0.00000001 },
        priceLineVisible: false,
      });
      lineSeries.setData(data.anchorLine);
    }

    const resize = () => {
      chart.applyOptions({
        width: Math.max(320, Math.floor(container.clientWidth)),
        height: Math.max(280, Math.floor(container.clientHeight)),
      });
      chart.timeScale().fitContent();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, [data]);

  return (
    <div
      ref={containerRef}
      className="search-lightweight-chart"
      aria-label="market candles and social posts"
    />
  );
}

function createSearchChart(container: HTMLDivElement): IChartApi {
  return createChart(container, {
    height: Math.max(280, container.clientHeight),
    width: Math.max(320, container.clientWidth),
    crosshair: {
      horzLine: { color: "rgba(229, 234, 227, 0.16)" },
      vertLine: { color: "rgba(229, 234, 227, 0.16)" },
    },
    grid: {
      horzLines: { color: "rgba(118, 128, 121, 0.12)" },
      vertLines: { color: "rgba(118, 128, 121, 0.1)" },
    },
    layout: {
      background: { color: "transparent", type: ColorType.Solid },
      textColor: "rgba(229, 234, 227, 0.64)",
    },
    rightPriceScale: {
      borderColor: "rgba(118, 128, 121, 0.28)",
      scaleMargins: { top: 0.12, bottom: 0.28 },
    },
    timeScale: {
      borderColor: "rgba(118, 128, 121, 0.28)",
      fixLeftEdge: true,
      fixRightEdge: true,
      timeVisible: true,
    },
  });
}

function buildChartData(
  timeline: TokenSocialTimelineData,
  marketOverlay: SearchTokenResult["market_overlay"],
): TimelineChartData {
  const candles = parseCandles(marketOverlay.candles);
  const anchorLine = timeline.buckets
    .map((bucket) => {
      const price = numberValue(bucket.price?.price_usd);
      if (price === null) {
        return null;
      }
      return { time: toChartTime(bucket.start_ms), value: price } satisfies LineData<UTCTimestamp>;
    })
    .filter((item): item is LineData<UTCTimestamp> => item !== null);
  const social = timeline.buckets.map((bucket) => ({
    time: toChartTime(bucket.start_ms),
    value: Math.max(0, Number(bucket.posts) || 0),
    color: bucket.watched_posts ? "rgba(85, 199, 174, 0.52)" : "rgba(231, 169, 39, 0.42)",
  }));
  const latestCandle = candles.at(-1);
  const latestAnchor = anchorLine.at(-1);

  return {
    candles,
    anchorLine,
    social,
    latestPrice: latestCandle?.close ?? latestAnchor?.value ?? null,
    hasMarket: candles.length > 0 || anchorLine.length > 0,
  };
}

function parseCandles(value: unknown): CandlestickData<UTCTimestamp>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => candleData(item))
    .filter((item): item is CandlestickData<UTCTimestamp> => item !== null)
    .sort((left, right) => Number(left.time) - Number(right.time));
}

function candleData(value: unknown): CandlestickData<UTCTimestamp> | null {
  const candle = value as Partial<MarketCandle> | null;
  if (!candle || typeof candle !== "object") {
    return null;
  }
  const timeMs = numberValue(candle.time_ms);
  const open = numberValue(candle.open);
  const high = numberValue(candle.high);
  const low = numberValue(candle.low);
  const close = numberValue(candle.close);
  if (timeMs === null || open === null || high === null || low === null || close === null) {
    return null;
  }
  return { time: toChartTime(timeMs), open, high, low, close };
}

function toChartTime(ms: number): UTCTimestamp {
  return Math.floor(ms / 1000) as UTCTimestamp;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
