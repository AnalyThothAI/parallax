import * as PageState from "@shared/ui/PageState";

import { useMacroCrossAssetQuery } from "../../api/useMacroPageQueries";
import {
  MacroAssetReturnList,
  MacroCorrelationList,
  MacroDivergenceList,
} from "../MacroDomainBlocks";
import { MacroEvidenceList } from "../MacroEvidenceBlocks";
import { MacroPageFrame } from "../MacroPageFrame";
import { MacroSeriesPanel } from "../MacroSeriesPanel";

export function MacroCrossAssetPage({ token }: { token: string }) {
  const query = useMacroCrossAssetQuery({ token });

  if (query.isError) {
    return <PageState.Error error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (query.isLoading || !query.data) {
    return <PageState.Loading label="加载跨资产证据" layout="route" />;
  }

  const data = query.data;
  return (
    <PageState.Stale updating={query.isFetching && !query.isLoading}>
      <MacroPageFrame
        data={data}
        pageId="cross_asset"
        question="风险资产、美元、信用与波动率是否在同一截止日给出一致方向？"
        title="跨资产确认"
      >
        <MacroSeriesPanel
          conceptKeys={["asset:spy", "asset:tlt", "asset:hyg", "fx:dxy"]}
          title="风险资产、久期、信用与美元"
          token={token}
        />
        <MacroAssetReturnList items={data.asset_returns} />
        <div className="macro-decision-grid">
          <MacroCorrelationList items={data.correlations_20} title="20 个交易日相关性" />
          <MacroCorrelationList items={data.correlations_60} title="60 个交易日相关性" />
        </div>
        <MacroDivergenceList items={data.divergences} />
        <MacroEvidenceList items={data.volatility} title="波动率证据" />
      </MacroPageFrame>
    </PageState.Stale>
  );
}
