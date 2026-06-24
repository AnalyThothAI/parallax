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
  primarySupportingTable,
} from "../../model/macroModulePresentation";
import { macroModuleTitle, macroStatusLabel } from "../../model/macroPageViewModel";
import { buildMacroAssetDiagnostics } from "../../model/macroWorkbenchModel";
import { AssetCorrelationPreview } from "../assets/AssetCorrelationPreview";
import { AssetDailyBrief } from "../assets/AssetDailyBrief";
import { AssetDiagnosticsBoard } from "../assets/AssetDiagnosticsBoard";
import { AssetMarketDashboard } from "../assets/AssetMarketDashboard";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroSignalDiagnosticsPanel } from "../workbench/MacroSignalDiagnosticsPanel";

import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import "./macroPages.css";

export function MacroAssetOverviewPage({ module, token }: MacroModulePageProps) {
  const supportingTable = primarySupportingTable(module);
  const dailyBrief = normalizeDailyBrief(module.daily_brief);
  const dataHealthBuckets = buildMacroDataHealthBuckets(module.data_health, "leaf");
  const assetDiagnostics = buildMacroAssetDiagnostics(module);
  const correlationQuery = useMacroAssetCorrelationQuery({ token, window: "60d" });
  const correlationData = correlationQuery.data ?? null;
  const snapshotAsOfLabel = textValue(module.snapshot.asof_label);
  const titleByKey = useMemo(() => assetTitleByKey(correlationData), [correlationData]);
  const positivePairs = useMemo(
    () => strongestCorrelationPairs(correlationData, "positive").slice(0, 3),
    [correlationData],
  );
  const negativePairs = useMemo(
    () => strongestCorrelationPairs(correlationData, "negative").slice(0, 3),
    [correlationData],
  );
  const hasCorrelationPairs = positivePairs.length > 0 || negativePairs.length > 0;
  const showCorrelationSurface =
    correlationQuery.isLoading || correlationQuery.isError || hasCorrelationPairs;
  const correlationMetaLabel = correlationMeta(correlationData, {
    isError: correlationQuery.isError,
    isFetching: correlationQuery.isFetching,
  });
  const assetGroups = useMemo(() => buildAssetMarketGroups(supportingTable), [supportingTable]);
  const assetCount = assetGroups.reduce((count, group) => count + group.rows.length, 0);
  const dataHealthSummaryLabel = textValue(module.data_health.summary_label);
  const diagnosticsSummary = buildAssetDiagnosticsSummary({
    buckets: dataHealthBuckets,
    moduleStatus: macroStatusLabel(module),
    provenance: module.provenance,
  });
  const availabilityTable = module.tables.find((table) => table.id === "availability_proxy_notes");
  const title = macroModuleTitle(module);
  if (!title) {
    return null;
  }

  return (
    <MacroPageScaffold label={`${title}模块页面`} pageKind="leaf">
      <div className="macro-assets-terminal">
        {assetCount > 0 ? (
          <section aria-label="核心资产行情" className="macro-assets-market-surface">
            <div className="macro-assets-surface-head">
              <div>
                <h2>核心资产行情</h2>
              </div>
              <dl aria-label="资产行情状态">
                {snapshotAsOfLabel ? (
                  <div>
                    <dt>截至</dt>
                    <dd>{snapshotAsOfLabel}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>项目</dt>
                  <dd>{assetCount}</dd>
                </div>
              </dl>
            </div>
            <AssetMarketDashboard groups={assetGroups} />
          </section>
        ) : null}

        <MacroSignalDiagnosticsPanel diagnostics={assetDiagnostics} />

        <aside aria-label="资产辅助信息" className="macro-assets-support-rail">
          {dailyBrief ? (
            <section aria-label="今日判断" className="macro-assets-side-section">
              <AssetDailyBrief brief={dailyBrief} />
            </section>
          ) : null}
          <section aria-label="数据诊断" className="macro-assets-side-section">
            <div className="macro-assets-side-title">
              <span>数据诊断</span>
              {dataHealthSummaryLabel ? <b>{dataHealthSummaryLabel}</b> : null}
            </div>
            <AssetDiagnosticsBoard
              availabilityTable={availabilityTable}
              buckets={dataHealthBuckets}
              provenance={module.provenance}
              summary={diagnosticsSummary}
            />
          </section>
        </aside>

        {showCorrelationSurface ? (
          <section aria-label="60日相关性" className="macro-assets-correlation-surface">
            <div className="macro-assets-surface-head">
              <div>
                {correlationMetaLabel ? <span>{correlationMetaLabel}</span> : null}
                <h2>60日相关性</h2>
              </div>
            </div>
            <AssetCorrelationPreview
              data={correlationData}
              errorLabel={correlationQuery.isError ? errorLabel(correlationQuery.error) : null}
              isError={correlationQuery.isError}
              isLoading={correlationQuery.isLoading}
              negativePairs={negativePairs}
              positivePairs={positivePairs}
              titleByKey={titleByKey}
            />
          </section>
        ) : null}
      </div>
    </MacroPageScaffold>
  );
}

function correlationMeta(
  data: unknown,
  { isError, isFetching }: { isError: boolean; isFetching: boolean },
): string | null {
  if (isFetching) return "更新中";
  if (isError) return "暂不可用";
  if (!data || typeof data !== "object") return null;
  const record = data as { asof_label?: string | null };
  return textValue(record.asof_label);
}

function errorLabel(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "请求失败";
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
