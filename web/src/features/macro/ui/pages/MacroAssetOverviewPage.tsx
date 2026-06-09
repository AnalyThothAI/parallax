import { useMemo } from "react";

import { useMacroAssetCorrelationQuery } from "../../api/useMacroAssetCorrelationQuery";
import {
  buildAssetDiagnosticsSummary,
  buildAssetMarketGroups,
  normalizeDailyBrief,
} from "../../model/macroAssetOverviewModel";
import { assetTitleByKey, strongestCorrelationPairs } from "../../model/macroCorrelationModel";
import {
  buildMacroDataHealthBuckets,
  macroReadSummary,
  primarySupportingTable,
} from "../../model/macroModulePresentation";
import { macroStatusLabel } from "../../model/macroPageViewModel";
import { AssetCorrelationPreview } from "../assets/AssetCorrelationPreview";
import { AssetDailyBrief } from "../assets/AssetDailyBrief";
import { AssetDiagnosticsBoard } from "../assets/AssetDiagnosticsBoard";
import { AssetMarketDashboard } from "../assets/AssetMarketDashboard";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroPanel } from "../primitives/MacroPanel";

import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import "./macroPages.css";

export function MacroAssetOverviewPage({ module, token }: MacroModulePageProps) {
  const supportingTable = primarySupportingTable(module);
  const dailyBrief = normalizeDailyBrief(module.daily_brief);
  const dataHealthBuckets = buildMacroDataHealthBuckets(module.data_health, "leaf");
  const correlationQuery = useMacroAssetCorrelationQuery({ token, window: "60d" });
  const correlationData = correlationQuery.data ?? null;
  const titleByKey = useMemo(() => assetTitleByKey(correlationData), [correlationData]);
  const positivePairs = useMemo(
    () => strongestCorrelationPairs(correlationData, "positive").slice(0, 3),
    [correlationData],
  );
  const negativePairs = useMemo(
    () => strongestCorrelationPairs(correlationData, "negative").slice(0, 3),
    [correlationData],
  );
  const assetGroups = useMemo(() => buildAssetMarketGroups(supportingTable), [supportingTable]);
  const diagnosticsSummary = buildAssetDiagnosticsSummary({
    buckets: dataHealthBuckets,
    moduleStatus: macroStatusLabel(module),
    provenance: module.provenance,
  });
  const availabilityTable = module.tables.find((table) => table.id === "availability_proxy_notes");

  return (
    <MacroPageScaffold label="大类资产模块页面" pageKind="leaf">
      <MacroPanel
        ariaLabel="市场仪表盘"
        className="macro-assets-dashboard-panel"
        meta={`${module.snapshot.asof_label ?? macroStatusLabel(module)} · ${
          supportingTable.rows?.length ?? 0
        } 项`}
        span="full"
        title="市场仪表盘"
      >
        <AssetMarketDashboard groups={assetGroups} />
      </MacroPanel>
      <MacroPanel
        ariaLabel="今日判断"
        className="macro-assets-judgment-panel"
        meta={dailyBrief?.status ?? macroStatusLabel(module)}
        span="full"
        title="今日判断"
      >
        <AssetDailyBrief brief={dailyBrief} fallback={macroReadSummary(module)} />
      </MacroPanel>
      <MacroPanel
        ariaLabel="60日相关性"
        className="macro-assets-correlation-panel"
        meta={correlationMeta(correlationData, correlationQuery.isFetching)}
        span="major"
        title="60日相关性"
      >
        <AssetCorrelationPreview
          data={correlationData}
          errorLabel={correlationQuery.isError ? errorLabel(correlationQuery.error) : null}
          isError={correlationQuery.isError}
          isLoading={correlationQuery.isLoading}
          negativePairs={negativePairs}
          positivePairs={positivePairs}
          titleByKey={titleByKey}
        />
      </MacroPanel>
      <MacroPanel
        ariaLabel="数据诊断"
        className="macro-assets-diagnostics-panel"
        meta={module.data_health.summary_label ?? module.data_health.summary_status}
        span="minor"
        title="数据诊断"
      >
        <AssetDiagnosticsBoard
          availabilityTable={availabilityTable}
          buckets={dataHealthBuckets}
          provenance={module.provenance}
          summary={diagnosticsSummary}
        />
      </MacroPanel>
    </MacroPageScaffold>
  );
}

function correlationMeta(data: unknown, isFetching: boolean): string {
  if (isFetching) return "更新中";
  if (!data || typeof data !== "object") return "暂无";
  const record = data as { asof_date?: string | null; window?: string };
  return record.asof_date ? `截至 ${record.asof_date}` : (record.window ?? "相关性");
}

function errorLabel(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "请求失败";
}
