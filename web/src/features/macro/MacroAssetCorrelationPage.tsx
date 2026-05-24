import type {
  MacroAssetCorrelationData,
  MacroAssetCorrelationPair,
  MacroAssetCorrelationWindow,
} from "@lib/types";
import * as PageState from "@shared/ui/PageState";
import { Button } from "@shared/ui/button";
import {
  ArrowLeft,
  Database,
  Grid3X3,
  Link as LinkIcon,
  TrendingDown,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { useMacroAssetCorrelationQuery } from "./api/useMacroAssetCorrelationQuery";
import "./MacroAssetCorrelation.css";

const WINDOWS: MacroAssetCorrelationWindow[] = ["20d", "60d", "120d"];

export function MacroAssetCorrelationPage({
  onBack,
  token,
}: {
  onBack?: () => void;
  token: string;
}) {
  const [window, setWindow] = useState<MacroAssetCorrelationWindow>("60d");
  const query = useMacroAssetCorrelationQuery({ token, window });
  const data = query.data ?? null;
  const titleByKey = useMemo(() => assetTitleByKey(data), [data]);
  const positivePairs = useMemo(() => strongestPairs(data, "positive"), [data]);
  const negativePairs = useMemo(() => strongestPairs(data, "negative"), [data]);

  return (
    <section className="macro-correlation-page" aria-label="资产相关性">
      <header className="macro-correlation-head">
        <div>
          <Button
            className="macro-correlation-action"
            size="sm"
            type="button"
            variant="ghost"
            onClick={onBack}
          >
            <ArrowLeft aria-hidden />
            <span>大类资产</span>
          </Button>
          <span className="macro-correlation-eyebrow">后端滚动收益</span>
          <h2>资产相关性</h2>
        </div>
        <div className="macro-correlation-controls" aria-label="相关性窗口">
          {WINDOWS.map((windowOption) => (
            <Button
              aria-pressed={windowOption === window}
              data-state={windowOption === window ? "active" : undefined}
              key={windowOption}
              size="xs"
              type="button"
              variant={windowOption === window ? "secondary" : "ghost"}
              onClick={() => setWindow(windowOption)}
            >
              {windowOption}
            </Button>
          ))}
        </div>
      </header>

      {query.isLoading ? <PageState.Loading layout="route" label="加载相关性" /> : null}
      {query.isError ? <PageState.Error error={query.error} /> : null}

      {data ? (
        <div className="macro-correlation-layout">
          <section className="macro-correlation-panel macro-correlation-panel-wide">
            <div className="macro-correlation-meta">
              <SectionLabel icon={Grid3X3} title={`${data.window} 矩阵`} />
              <span>{data.asof_date ? `截至 ${data.asof_date}` : "暂无日期"}</span>
            </div>
            <CorrelationMatrix data={data} titleByKey={titleByKey} />
          </section>

          <section className="macro-correlation-panel">
            <SectionLabel icon={TrendingUp} title="最强正相关" />
            <PairList pairs={positivePairs} titleByKey={titleByKey} />
          </section>

          <section className="macro-correlation-panel">
            <SectionLabel icon={TrendingDown} title="最强负相关" />
            <PairList pairs={negativePairs} titleByKey={titleByKey} />
          </section>

          <section className="macro-correlation-panel">
            <SectionLabel icon={Database} title="覆盖度" />
            <AssetCoverage data={data} />
          </section>

          <section className="macro-correlation-panel">
            <SectionLabel icon={LinkIcon} title="数据缺口" />
            <CorrelationGaps data={data} titleByKey={titleByKey} />
          </section>
        </div>
      ) : null}
    </section>
  );
}

function SectionLabel({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <div className="macro-correlation-section-head">
      <Icon aria-hidden />
      <h4>{title}</h4>
    </div>
  );
}

function CorrelationMatrix({
  data,
  titleByKey,
}: {
  data: MacroAssetCorrelationData;
  titleByKey: Record<string, string>;
}) {
  if (data.assets.length === 0) {
    return <span className="macro-correlation-muted">暂无可用资产</span>;
  }
  return (
    <div className="macro-correlation-table-wrap">
      <table className="macro-correlation-table">
        <thead>
          <tr>
            <th scope="col">资产</th>
            {data.assets.map((asset) => (
              <th key={asset.concept_key} scope="col">
                {asset.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.matrix.map((row) => (
            <tr key={row.concept_key}>
              <th scope="row">{assetLabel(row.concept_key, titleByKey)}</th>
              {data.assets.map((asset) => {
                const value = row.correlations[asset.concept_key];
                return (
                  <td data-tone={correlationTone(value)} key={asset.concept_key}>
                    {matrixCorrelationLabel(value)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PairList({
  pairs,
  titleByKey,
}: {
  pairs: MacroAssetCorrelationPair[];
  titleByKey: Record<string, string>;
}) {
  if (pairs.length === 0) {
    return <span className="macro-correlation-muted">暂无可用配对</span>;
  }
  return (
    <div className="macro-correlation-pairs">
      {pairs.map((pair) => (
        <article className="macro-correlation-pair" key={`${pair.left}:${pair.right}`}>
          <span>
            <b>
              {assetLabel(pair.left, titleByKey)} / {assetLabel(pair.right, titleByKey)}
            </b>
            <small>
              样本={pair.sample_size} · {pair.start_date ?? "-"} 至 {pair.end_date ?? "-"}
            </small>
          </span>
          <strong data-tone={correlationTone(pair.correlation)}>
            {signedCorrelationLabel(pair.correlation)}
          </strong>
        </article>
      ))}
    </div>
  );
}

function AssetCoverage({ data }: { data: MacroAssetCorrelationData }) {
  return (
    <div className="macro-correlation-feature-table">
      {data.assets.map((asset) => (
        <article className="macro-correlation-feature-row" key={asset.concept_key}>
          <span>
            <b>{asset.title}</b>
            <small>
              收益样本 {asset.return_count} / 观测 {asset.observations_count}
            </small>
          </span>
          <strong>{asset.return_count}</strong>
          <span className="macro-correlation-feature-deltas">
            <small>{asset.start_date ?? "-"}</small>
            <small>{asset.latest_observed_at ?? "-"}</small>
            <small>{asset.sources.map(sourceLabel).join(" / ") || "暂无数据源"}</small>
          </span>
        </article>
      ))}
    </div>
  );
}

function CorrelationGaps({
  data,
  titleByKey,
}: {
  data: MacroAssetCorrelationData;
  titleByKey: Record<string, string>;
}) {
  if (data.data_gaps.length === 0) {
    return <span className="macro-correlation-muted">覆盖完整</span>;
  }
  return (
    <div className="macro-correlation-chip-list">
      {data.data_gaps.slice(0, 20).map((gap, index) => (
        <span className="macro-correlation-chip" data-tone="gap" key={`${gap.code}:${index}`}>
          {gapLabel(gap, titleByKey)}
        </span>
      ))}
    </div>
  );
}

function strongestPairs(
  data: MacroAssetCorrelationData | null,
  direction: "positive" | "negative",
): MacroAssetCorrelationPair[] {
  const pairs =
    data?.pairs.filter(
      (pair) =>
        pair.available &&
        typeof pair.correlation === "number" &&
        (direction === "positive" ? pair.correlation >= 0 : pair.correlation < 0),
    ) ?? [];
  return pairs
    .sort((left, right) =>
      direction === "positive"
        ? Number(right.correlation) - Number(left.correlation)
        : Number(left.correlation) - Number(right.correlation),
    )
    .slice(0, 8);
}

function assetTitleByKey(data: MacroAssetCorrelationData | null): Record<string, string> {
  return Object.fromEntries((data?.assets ?? []).map((asset) => [asset.concept_key, asset.title]));
}

function gapLabel(
  gap: MacroAssetCorrelationData["data_gaps"][number],
  titleByKey: Record<string, string>,
): string {
  if (gap.label) {
    return gap.label;
  }
  const prefix = CORRELATION_GAP_LABELS[gap.code] ?? "相关性样本不足";
  if (gap.left || gap.right) {
    return `${prefix}：${gap.left ? (titleByKey[gap.left] ?? "资产") : "资产"} / ${
      gap.right ? (titleByKey[gap.right] ?? "资产") : "资产"
    }`;
  }
  if (gap.concept_key) {
    return `${prefix}：${titleByKey[gap.concept_key] ?? "资产"}`;
  }
  return prefix;
}

function assetLabel(conceptKey: string, titleByKey: Record<string, string>): string {
  return titleByKey[conceptKey] ?? "资产";
}

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? (looksInternalSource(source) ? "数据源" : source);
}

function looksInternalSource(value: string): boolean {
  return /^[a-z][a-z0-9_:.-]*$/.test(value);
}

function matrixCorrelationLabel(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "-";
  }
  return value.toFixed(2);
}

function signedCorrelationLabel(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

const CORRELATION_GAP_LABELS: Record<string, string> = {
  insufficient_history: "历史样本不足",
  insufficient_overlap: "重叠样本不足",
  missing_observations: "观测缺失",
};

const SOURCE_LABELS: Record<string, string> = {
  fred: "FRED",
  nyfed: "NY Fed",
  yahoo: "Yahoo",
};

function correlationTone(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "gap";
  }
  if (value >= 0.55) {
    return "constructive";
  }
  if (value <= -0.35) {
    return "stress";
  }
  return "neutral";
}
