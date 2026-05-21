import type {
  MacroAssetCorrelationData,
  MacroAssetCorrelationPair,
  MacroAssetCorrelationWindow,
} from "@lib/types";
import { RemoteState } from "@shared/ui/RemoteState";
import clsx from "clsx";
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
import "./macro.css";

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
    <section className="macro-workbench macro-correlation-page" aria-label="Asset Correlation">
      <header className="macro-correlation-head">
        <div>
          <button className="macro-icon-action" type="button" onClick={onBack}>
            <ArrowLeft aria-hidden />
            <span>Macro assets</span>
          </button>
          <span className="macro-eyebrow">Backend rolling returns</span>
          <h2>Asset Correlation</h2>
        </div>
        <div className="macro-correlation-controls" aria-label="Correlation window">
          {WINDOWS.map((windowOption) => (
            <button
              className={clsx(windowOption === window && "active")}
              key={windowOption}
              type="button"
              onClick={() => setWindow(windowOption)}
            >
              {windowOption}
            </button>
          ))}
        </div>
      </header>

      {query.isLoading ? (
        <RemoteState.Loading layout="route" label="loading correlations" />
      ) : null}
      {query.isError ? <RemoteState.Error error={query.error} /> : null}

      {data ? (
        <div className="macro-correlation-layout">
          <section className="macro-map-panel wide">
            <div className="macro-correlation-meta">
              <SectionLabel icon={Grid3X3} title={`${data.window} matrix`} />
              <span>{data.asof_date ?? "asof pending"}</span>
            </div>
            <CorrelationMatrix data={data} titleByKey={titleByKey} />
          </section>

          <section className="macro-map-panel">
            <SectionLabel icon={TrendingUp} title="Strongest positive" />
            <PairList pairs={positivePairs} titleByKey={titleByKey} />
          </section>

          <section className="macro-map-panel">
            <SectionLabel icon={TrendingDown} title="Strongest negative" />
            <PairList pairs={negativePairs} titleByKey={titleByKey} />
          </section>

          <section className="macro-map-panel">
            <SectionLabel icon={Database} title="Coverage" />
            <AssetCoverage data={data} />
          </section>

          <section className="macro-map-panel">
            <SectionLabel icon={LinkIcon} title="Data gaps" />
            <CorrelationGaps data={data} titleByKey={titleByKey} />
          </section>
        </div>
      ) : null}
    </section>
  );
}

function SectionLabel({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <div className="macro-section-head">
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
    return <span className="macro-muted">no assets available</span>;
  }
  return (
    <div className="macro-correlation-table-wrap">
      <table className="macro-correlation-table">
        <thead>
          <tr>
            <th scope="col">asset</th>
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
              <th scope="row">{titleByKey[row.concept_key] ?? row.concept_key}</th>
              {data.assets.map((asset) => {
                const value = row.correlations[asset.concept_key];
                return (
                  <td className={correlationTone(value)} key={asset.concept_key}>
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
    return <span className="macro-muted">no available pairs</span>;
  }
  return (
    <div className="macro-correlation-pairs">
      {pairs.map((pair) => (
        <article className="macro-correlation-pair" key={`${pair.left}:${pair.right}`}>
          <span>
            <b>
              {titleByKey[pair.left] ?? pair.left} / {titleByKey[pair.right] ?? pair.right}
            </b>
            <small>
              n={pair.sample_size} · {pair.start_date ?? "-"} to {pair.end_date ?? "-"}
            </small>
          </span>
          <strong className={correlationTone(pair.correlation)}>
            {signedCorrelationLabel(pair.correlation)}
          </strong>
        </article>
      ))}
    </div>
  );
}

function AssetCoverage({ data }: { data: MacroAssetCorrelationData }) {
  return (
    <div className="macro-feature-table">
      {data.assets.map((asset) => (
        <article className="macro-feature-row" key={asset.concept_key}>
          <span>
            <b>{asset.title}</b>
            <small>{asset.concept_key}</small>
          </span>
          <strong>{asset.return_count}</strong>
          <span className="macro-feature-deltas">
            <small>{asset.start_date ?? "-"}</small>
            <small>{asset.latest_observed_at ?? "-"}</small>
            <small>{asset.sources.join(" / ") || "source pending"}</small>
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
    return <span className="macro-muted">coverage complete</span>;
  }
  return (
    <div className="macro-chip-list">
      {data.data_gaps.slice(0, 20).map((gap, index) => (
        <span className="macro-chip gap" key={`${gap.code}:${index}`}>
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
  return Object.fromEntries(
    (data?.assets ?? []).map((asset) => [asset.concept_key, asset.title]),
  );
}

function gapLabel(
  gap: MacroAssetCorrelationData["data_gaps"][number],
  titleByKey: Record<string, string>,
): string {
  if (gap.left || gap.right) {
    return `${gap.code}: ${gap.left ? titleByKey[gap.left] ?? gap.left : "-"} / ${
      gap.right ? titleByKey[gap.right] ?? gap.right : "-"
    }`;
  }
  if (gap.concept_key) {
    return `${gap.code}: ${titleByKey[gap.concept_key] ?? gap.concept_key}`;
  }
  return gap.code;
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
