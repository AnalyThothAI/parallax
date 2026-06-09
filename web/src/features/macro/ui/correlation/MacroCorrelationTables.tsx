import type { MacroAssetCorrelationData, MacroAssetCorrelationPair } from "@lib/types";

import {
  assetLabel,
  correlationGapLabel,
  correlationTone,
  matrixCorrelationLabel,
  signedCorrelationLabel,
  sourceLabel,
} from "../../model/macroCorrelationModel";
import { MacroTableFrame } from "../tables/MacroTableFrame";

import "./macroCorrelation.css";

export function MacroCorrelationMatrixTable({
  className,
  data,
  label,
  minWidth = 720,
  titleByKey,
}: {
  className?: string;
  data: MacroAssetCorrelationData;
  label?: string;
  minWidth?: number;
  titleByKey: Record<string, string>;
}) {
  const caption = label ?? `${data.window} 资产相关性矩阵`;
  if (data.assets.length === 0) {
    return <span className="macro-correlation-empty">暂无可用资产</span>;
  }
  return (
    <MacroTableFrame caption={caption} minWidth={minWidth} stickyFirstColumn>
      <table
        aria-label={caption}
        className={["macro-correlation-matrix-table", className].filter(Boolean).join(" ")}
      >
        <caption>{caption}</caption>
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
    </MacroTableFrame>
  );
}

export function MacroCorrelationPairList({
  emptyLabel = "暂无可用配对",
  pairs,
  titleByKey,
  variant = "detail",
}: {
  emptyLabel?: string;
  pairs: MacroAssetCorrelationPair[];
  titleByKey: Record<string, string>;
  variant?: "detail" | "summary";
}) {
  if (pairs.length === 0) {
    return <span className="macro-correlation-empty">{emptyLabel}</span>;
  }
  return (
    <ul className="macro-correlation-pair-list" data-variant={variant}>
      {pairs.map((pair) => (
        <li key={`${pair.left}:${pair.right}`}>
          <strong>
            {assetLabel(pair.left, titleByKey)} / {assetLabel(pair.right, titleByKey)}
          </strong>
          <span data-tone={correlationTone(pair.correlation)}>
            {signedCorrelationLabel(pair.correlation)}
          </span>
          {variant === "detail" ? (
            <small>
              样本={pair.sample_size} · {pair.start_date ?? "-"} 至 {pair.end_date ?? "-"}
            </small>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function MacroCorrelationAssetCoverage({ data }: { data: MacroAssetCorrelationData }) {
  return (
    <ul className="macro-correlation-coverage-list">
      {data.assets.map((asset) => (
        <li key={asset.concept_key}>
          <strong>{asset.title}</strong>
          <span>
            收益样本 {asset.return_count} / 观测 {asset.observations_count}
          </span>
          <small>{asset.sources.map(sourceLabel).join(" / ") || "暂无数据源"}</small>
        </li>
      ))}
    </ul>
  );
}

export function MacroCorrelationGaps({
  data,
  titleByKey,
}: {
  data: MacroAssetCorrelationData;
  titleByKey: Record<string, string>;
}) {
  if (data.data_gaps.length === 0) {
    return <span className="macro-correlation-empty">覆盖完整</span>;
  }
  return (
    <ul className="macro-correlation-gap-list">
      {data.data_gaps.slice(0, 20).map((gap, index) => (
        <li key={`${gap.code}:${index}`}>{correlationGapLabel(gap, titleByKey)}</li>
      ))}
    </ul>
  );
}
