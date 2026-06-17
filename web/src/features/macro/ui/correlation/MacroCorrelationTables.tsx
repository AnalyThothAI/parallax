import type { MacroAssetCorrelationData, MacroAssetCorrelationPair } from "@lib/types";

import {
  assetLabel,
  correlationTone,
  matrixCorrelationLabel,
  signedCorrelationLabel,
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
  const caption = textValue(label);
  if (!caption) {
    return null;
  }
  const rows = data.matrix
    .map((row) => {
      const rowLabel = assetLabel(row.concept_key, titleByKey);
      return rowLabel ? { row, rowLabel } : null;
    })
    .filter(
      (row): row is { row: MacroAssetCorrelationData["matrix"][number]; rowLabel: string } =>
        row !== null,
    );
  if (data.assets.length === 0 || rows.length === 0) {
    return null;
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
          {rows.map(({ row, rowLabel }) => (
            <tr key={row.concept_key}>
              <th scope="row">{rowLabel}</th>
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

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

export function MacroCorrelationPairList({
  pairs,
  titleByKey,
  variant = "detail",
}: {
  pairs: MacroAssetCorrelationPair[];
  titleByKey: Record<string, string>;
  variant?: "detail" | "summary";
}) {
  const labelledPairs = pairs
    .map((pair) => {
      const leftLabel = assetLabel(pair.left, titleByKey);
      const rightLabel = assetLabel(pair.right, titleByKey);
      return leftLabel && rightLabel ? { pair, leftLabel, rightLabel } : null;
    })
    .filter(
      (pair): pair is { pair: MacroAssetCorrelationPair; leftLabel: string; rightLabel: string } =>
        pair !== null,
    );
  if (labelledPairs.length === 0) {
    return null;
  }
  return (
    <ul className="macro-correlation-pair-list" data-variant={variant}>
      {labelledPairs.map(({ pair, leftLabel, rightLabel }) => (
        <li key={`${pair.left}:${pair.right}`}>
          <strong>
            {leftLabel} / {rightLabel}
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
