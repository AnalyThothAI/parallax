import type {
  MacroAssetCorrelationData,
  MacroAssetCorrelationWindow,
} from "@lib/types";
import * as PageState from "@shared/ui/PageState";
import { Button } from "@shared/ui/button";
import { useMemo, useState } from "react";

import { useMacroAssetCorrelationQuery } from "../../api/useMacroAssetCorrelationQuery";
import {
  assetTitleByKey,
  strongestCorrelationPairs,
} from "../../model/macroCorrelationModel";
import { buildMacroBreadcrumbs } from "../../model/macroRoutes";
import {
  MacroCorrelationAssetCoverage,
  MacroCorrelationGaps,
  MacroCorrelationMatrixTable,
  MacroCorrelationPairList,
} from "../correlation/MacroCorrelationTables";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroShell, type MacroShellHeaderModel } from "../shell/MacroShell";

const WINDOWS: MacroAssetCorrelationWindow[] = ["20d", "60d", "120d"];

export function MacroMatrixPage({ token }: { token: string }) {
  const [window, setWindow] = useState<MacroAssetCorrelationWindow>("60d");
  const query = useMacroAssetCorrelationQuery({ token, window });
  const data = query.data ?? null;
  const titleByKey = useMemo(() => assetTitleByKey(data), [data]);
  const positivePairs = useMemo(() => strongestCorrelationPairs(data, "positive"), [data]);
  const negativePairs = useMemo(() => strongestCorrelationPairs(data, "negative"), [data]);

  return (
    <MacroShell
      header={matrixHeader({
        data,
        isFetching: query.isFetching,
        window,
        onWindowChange: setWindow,
      })}
      pageKind="matrix"
      productTier="primary"
    >
      <MacroPageScaffold label="资产相关性矩阵页面" pageKind="matrix">
        {query.isLoading ? <PageState.Loading layout="route" label="加载相关性" /> : null}
        {query.isError ? <PageState.Error error={query.error} /> : null}
        {data ? (
          <>
            <MacroPanel
              ariaLabel="资产相关性矩阵"
              meta={data.asof_date ? `截至 ${data.asof_date}` : "暂无日期"}
              span="full"
              title={`${data.window} 矩阵`}
            >
              <MacroCorrelationMatrixTable data={data} titleByKey={titleByKey} />
            </MacroPanel>
            <MacroPanel ariaLabel="最强正相关" title="最强正相关">
              <MacroCorrelationPairList pairs={positivePairs} titleByKey={titleByKey} />
            </MacroPanel>
            <MacroPanel ariaLabel="最强负相关" title="最强负相关">
              <MacroCorrelationPairList pairs={negativePairs} titleByKey={titleByKey} />
            </MacroPanel>
            <MacroPanel ariaLabel="覆盖度" title="覆盖度">
              <MacroCorrelationAssetCoverage data={data} />
            </MacroPanel>
            <MacroPanel ariaLabel="数据缺口" title="数据缺口">
              <MacroCorrelationGaps data={data} titleByKey={titleByKey} />
            </MacroPanel>
          </>
        ) : null}
      </MacroPageScaffold>
    </MacroShell>
  );
}

function matrixHeader({
  data,
  isFetching,
  onWindowChange,
  window,
}: {
  data: MacroAssetCorrelationData | null;
  isFetching: boolean;
  onWindowChange: (window: MacroAssetCorrelationWindow) => void;
  window: MacroAssetCorrelationWindow;
}): MacroShellHeaderModel {
  return {
    actions: (
      <>
        {WINDOWS.map((windowOption) => (
          <Button
            aria-pressed={windowOption === window}
            data-state={windowOption === window ? "active" : undefined}
            key={windowOption}
            size="xs"
            type="button"
            variant={windowOption === window ? "secondary" : "ghost"}
            onClick={() => onWindowChange(windowOption)}
          >
            {windowOption}
          </Button>
        ))}
      </>
    ),
    breadcrumbs: buildMacroBreadcrumbs("assets/correlation"),
    eyebrow: "后端滚动收益",
    question: "跨资产收益相关性矩阵",
    statusItems: [
      { label: "窗口", value: window },
      { label: "截至", value: data?.asof_date ?? "暂无日期" },
      { label: "状态", value: isFetching ? "更新中" : "可用" },
    ],
    title: "资产相关性",
  };
}
