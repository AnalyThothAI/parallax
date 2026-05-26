import type {
  MacroAssetCorrelationData,
  MacroAssetCorrelationPair,
  MacroAssetCorrelationWindow,
} from "@lib/types";
import * as PageState from "@shared/ui/PageState";
import { Button } from "@shared/ui/button";
import { Database, Link as LinkIcon, TrendingDown, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";

import { useMacroAssetCorrelationQuery } from "../../api/useMacroAssetCorrelationQuery";
import {
  assetLabel,
  assetTitleByKey,
  correlationGapLabel,
  correlationTone,
  matrixCorrelationLabel,
  signedCorrelationLabel,
  sourceLabel,
  strongestCorrelationPairs,
} from "../../model/macroCorrelationModel";
import { buildMacroBreadcrumbs } from "../../model/macroRoutes";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroShell, type MacroShellHeaderModel } from "../shell/MacroShell";
import { MacroTableFrame } from "../tables/MacroTableFrame";

const WINDOWS: MacroAssetCorrelationWindow[] = ["20d", "60d", "120d"];

export function MacroMatrixPage({ token }: { token: string }) {
  const [window, setWindow] = useState<MacroAssetCorrelationWindow>("60d");
  const query = useMacroAssetCorrelationQuery({ token, window });
  const data = query.data ?? null;
  const titleByKey = useMemo(() => assetTitleByKey(data), [data]);
  const positivePairs = useMemo(
    () => strongestCorrelationPairs(data, "positive"),
    [data],
  );
  const negativePairs = useMemo(
    () => strongestCorrelationPairs(data, "negative"),
    [data],
  );

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
              <CorrelationMatrix data={data} titleByKey={titleByKey} />
            </MacroPanel>
            <MacroPanel ariaLabel="最强正相关" title="最强正相关">
              <PairList pairs={positivePairs} titleByKey={titleByKey} />
            </MacroPanel>
            <MacroPanel ariaLabel="最强负相关" title="最强负相关">
              <PairList pairs={negativePairs} titleByKey={titleByKey} />
            </MacroPanel>
            <MacroPanel ariaLabel="覆盖度" title="覆盖度">
              <AssetCoverage data={data} />
            </MacroPanel>
            <MacroPanel ariaLabel="数据缺口" title="数据缺口">
              <CorrelationGaps data={data} titleByKey={titleByKey} />
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

function CorrelationMatrix({
  data,
  titleByKey,
}: {
  data: MacroAssetCorrelationData;
  titleByKey: Record<string, string>;
}) {
  if (data.assets.length === 0) {
    return <span>暂无可用资产</span>;
  }
  return (
    <MacroTableFrame caption={`${data.window} 资产相关性矩阵`} minWidth={720} stickyFirstColumn>
      <table aria-label={`${data.window} 资产相关性矩阵`} className="macro-asset-index-table">
        <caption>{data.window} 资产相关性矩阵</caption>
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

function PairList({
  pairs,
  titleByKey,
}: {
  pairs: MacroAssetCorrelationPair[];
  titleByKey: Record<string, string>;
}) {
  if (pairs.length === 0) {
    return <span>暂无可用配对</span>;
  }
  return (
    <ul>
      {pairs.map((pair) => (
        <li key={`${pair.left}:${pair.right}`}>
          <strong>
            {assetLabel(pair.left, titleByKey)} / {assetLabel(pair.right, titleByKey)}
          </strong>{" "}
          <span data-tone={correlationTone(pair.correlation)}>
            {signedCorrelationLabel(pair.correlation)}
          </span>
          <small>
            {" "}
            样本={pair.sample_size} · {pair.start_date ?? "-"} 至 {pair.end_date ?? "-"}
          </small>
        </li>
      ))}
    </ul>
  );
}

function AssetCoverage({ data }: { data: MacroAssetCorrelationData }) {
  return (
    <ul>
      {data.assets.map((asset) => (
        <li key={asset.concept_key}>
          <strong>{asset.title}</strong>{" "}
          <span>
            收益样本 {asset.return_count} / 观测 {asset.observations_count}
          </span>{" "}
          <small>{asset.sources.map(sourceLabel).join(" / ") || "暂无数据源"}</small>
        </li>
      ))}
    </ul>
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
    return <span>覆盖完整</span>;
  }
  return (
    <ul>
      {data.data_gaps.slice(0, 20).map((gap, index) => (
        <li key={`${gap.code}:${index}`}>{correlationGapLabel(gap, titleByKey)}</li>
      ))}
    </ul>
  );
}
