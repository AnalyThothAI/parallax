import type { MacroAssetCorrelationData, MacroAssetCorrelationPair } from "@lib/types";
import { useState } from "react";
import { Link } from "react-router-dom";

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
    return <div className="macro-assets-inline-state">暂无相关性样本</div>;
  }
  return (
    <div className="macro-assets-correlation-summary">
      <div className="macro-assets-correlation-pairs">
        <PairGroup emptyLabel="暂无" pairs={positivePairs} title="正相关" titleByKey={titleByKey} />
        <PairGroup emptyLabel="暂无" pairs={negativePairs} title="负相关" titleByKey={titleByKey} />
      </div>
      <div className="macro-assets-correlation-actions">
        <Link className="macro-assets-detail-link" to="/macro/assets/correlation">
          相关性详情
        </Link>
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
  emptyLabel,
  pairs,
  title,
  titleByKey,
}: {
  emptyLabel: string;
  pairs: MacroAssetCorrelationPair[];
  title: string;
  titleByKey: Record<string, string>;
}) {
  return (
    <div className="macro-assets-pair-group">
      <h4>{title}</h4>
      <MacroCorrelationPairList
        emptyLabel={emptyLabel}
        pairs={pairs}
        titleByKey={titleByKey}
        variant="summary"
      />
    </div>
  );
}
