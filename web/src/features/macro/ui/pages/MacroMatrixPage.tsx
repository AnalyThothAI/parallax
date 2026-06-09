import type { MacroAssetCorrelationData, MacroAssetCorrelationWindow } from "@lib/types";
import * as PageState from "@shared/ui/PageState";
import { Button } from "@shared/ui/button";
import { useMemo, useState } from "react";

import { useMacroAssetCorrelationQuery } from "../../api/useMacroAssetCorrelationQuery";
import { assetTitleByKey, strongestCorrelationPairs } from "../../model/macroCorrelationModel";
import { buildMacroBreadcrumbs } from "../../model/macroRoutes";
import { CorrelationRead } from "../correlation/CorrelationRead";
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
              ariaLabel="相关性简报"
              className="macro-correlation-read-panel"
              meta={data.asof_date ? `截至 ${data.asof_date}` : data.window}
              span="full"
              title="相关性简报"
            >
              <CorrelationRead
                data={data}
                negativePair={negativePairs[0] ?? null}
                positivePair={positivePairs[0] ?? null}
                titleByKey={titleByKey}
              />
            </MacroPanel>
            <MacroPanel
              ariaLabel="相关性矩阵"
              meta={data.asof_date ? `截至 ${data.asof_date}` : "暂无日期"}
              span="full"
              title={`${data.window} 矩阵`}
            >
              <MacroCorrelationMatrixTable data={data} titleByKey={titleByKey} />
            </MacroPanel>
            <MacroPanel
              ariaLabel="相关性证据"
              className="macro-correlation-evidence-panel"
              meta={`${positivePairs.length + negativePairs.length} 个配对`}
              span="major"
              title="相关性证据"
            >
              <div className="macro-correlation-lane-grid">
                <section className="macro-correlation-lane" aria-label="最强正相关" role="group">
                  <h4>最强正相关</h4>
                  <MacroCorrelationPairList pairs={positivePairs} titleByKey={titleByKey} />
                </section>
                <section className="macro-correlation-lane" aria-label="最强负相关" role="group">
                  <h4>最强负相关</h4>
                  <MacroCorrelationPairList pairs={negativePairs} titleByKey={titleByKey} />
                </section>
              </div>
            </MacroPanel>
            <MacroPanel
              ariaLabel="数据诊断"
              className="macro-correlation-diagnostics-panel"
              meta={`${data.assets.length} 个资产 · ${data.data_gaps.length} 个缺口`}
              span="minor"
              title="数据诊断"
            >
              <div className="macro-correlation-diagnostics">
                <section className="macro-correlation-lane" aria-label="覆盖状态" role="group">
                  <h4>覆盖状态</h4>
                  <MacroCorrelationAssetCoverage data={data} />
                </section>
                <section className="macro-correlation-lane" aria-label="样本缺口" role="group">
                  <h4>样本缺口</h4>
                  <MacroCorrelationGaps data={data} titleByKey={titleByKey} />
                </section>
              </div>
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
