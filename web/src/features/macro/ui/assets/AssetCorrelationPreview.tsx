import type { MacroAssetCorrelationData, MacroAssetCorrelationPair } from "@lib/types";
import { useState } from "react";

import {
  MacroCorrelationMatrixTable,
  MacroCorrelationPairList,
} from "../correlation/MacroCorrelationTables";

import "./macroAssetOverview.css";

export function AssetCorrelationPreview({
  data,
  errorLabel,
  isError,
  isLoading,
  negativePairs,
  positivePairs,
  titleByKey,
}: {
  data: MacroAssetCorrelationData | null;
  errorLabel: string | null;
  isError: boolean;
  isLoading: boolean;
  negativePairs: MacroAssetCorrelationPair[];
  positivePairs: MacroAssetCorrelationPair[];
  titleByKey: Record<string, string>;
}) {
  const [matrixOpen, setMatrixOpen] = useState(false);

  if (isLoading) {
    return <div className="macro-assets-inline-state">相关性加载中</div>;
  }
  if (isError) {
    return <div className="macro-assets-inline-state">相关性暂不可用：{errorLabel}</div>;
  }
  if (!data) {
    return null;
  }
  return (
    <div className="macro-assets-correlation-summary">
      <div className="macro-assets-correlation-pairs">
        {positivePairs.length > 0 ? (
          <PairGroup pairs={positivePairs} title="正相关" titleByKey={titleByKey} />
        ) : null}
        {negativePairs.length > 0 ? (
          <PairGroup pairs={negativePairs} title="负相关" titleByKey={titleByKey} />
        ) : null}
      </div>
      <div className="macro-assets-correlation-actions">
        <details
          className="macro-assets-correlation-details"
          onToggle={(event) => setMatrixOpen(event.currentTarget.open)}
        >
          <summary>矩阵</summary>
          {matrixOpen ? (
            <MacroCorrelationMatrixTable
              className="macro-assets-correlation-matrix"
              data={data}
              label="60日资产相关性矩阵"
              minWidth={560}
              titleByKey={titleByKey}
            />
          ) : null}
        </details>
      </div>
    </div>
  );
}

function PairGroup({
  pairs,
  title,
  titleByKey,
}: {
  pairs: MacroAssetCorrelationPair[];
  title: string;
  titleByKey: Record<string, string>;
}) {
  return (
    <div className="macro-assets-pair-group">
      <h4>{title}</h4>
      <MacroCorrelationPairList pairs={pairs} titleByKey={titleByKey} variant="summary" />
    </div>
  );
}
