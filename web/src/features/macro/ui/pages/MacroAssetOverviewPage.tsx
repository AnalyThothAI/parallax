import { tableCaption } from "../../model/macroModulePageModel";
import {
  buildMacroDataHealthBuckets,
  buildMacroEvidenceGroups,
  buildMacroMetrics,
  macroReadSummary,
  primarySupportingTable,
} from "../../model/macroModulePresentation";
import { macroStatusLabel } from "../../model/macroPageViewModel";
import { MacroDataHealthPanel } from "../primitives/MacroDataHealthPanel";
import { MacroEvidencePanel } from "../primitives/MacroEvidencePanel";
import { MacroMetricStrip } from "../primitives/MacroMetricStrip";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroReadPanel } from "../primitives/MacroReadPanel";
import { MacroTransmissionPanel } from "../primitives/MacroTransmissionPanel";
import { MacroSourceTable } from "../tables/MacroSourceTable";

import { MacroMarketBoard } from "./MacroMarketBoard";
import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import { useMacroPrimarySeries } from "./MacroPrimarySeries";
import "./macroPages.css";

type MacroDailyBriefBlock = {
  id: string;
  title: string;
  stance: string;
  body: string;
};

type MacroDailyBrief = {
  headline: string;
  status: string;
  blocks: MacroDailyBriefBlock[];
};

export function MacroAssetOverviewPage({ module, moduleId, token }: MacroModulePageProps) {
  const metrics = buildMacroMetrics({ tiles: module.tiles });
  const supportingTable = primarySupportingTable(module);
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });
  const evidenceGroups = buildMacroEvidenceGroups(module.module_evidence);
  const dataHealthBuckets = buildMacroDataHealthBuckets(module.data_health, "leaf");
  const dailyBrief = normalizeDailyBrief(module.daily_brief);

  return (
    <MacroPageScaffold label="大类资产模块页面" pageKind="leaf">
      <DailyBriefPanel brief={dailyBrief} />
      <MacroMetricStrip
        ariaLabel="关键指标"
        density={metrics.length > 4 ? "compact" : "card"}
        metrics={metrics}
      />
      <MacroMarketBoard
        chart={module.primary_chart}
        moduleId={moduleId}
        seriesData={series.data}
        seriesLoading={series.isLoading}
        supportingTable={supportingTable.rows?.length ? supportingTable : null}
      />
      <MacroReadPanel
        meta={macroStatusLabel(module)}
        read={module.module_read}
        summary={macroReadSummary(module)}
      />
      <MacroTransmissionPanel meta="大类资产" nodes={module.transmission} />
      <MacroEvidencePanel groups={evidenceGroups} />
      <MacroPanel
        ariaLabel="数据来源"
        meta={sourceMeta(module.provenance)}
        span="half"
        title="数据来源"
      >
        <MacroSourceTable caption="数据源" source={module.provenance} />
      </MacroPanel>
      <MacroDataHealthPanel
        buckets={dataHealthBuckets}
        meta={module.data_health.summary_label ?? module.data_health.summary_status}
      />
      {supportingTable.rows?.length ? null : (
        <MacroPanel ariaLabel="大类资产快照" span="full" title={tableCaption(supportingTable)}>
          <p className="macro-table-source-note">大类资产快照暂无可展示行。</p>
        </MacroPanel>
      )}
    </MacroPageScaffold>
  );
}

function DailyBriefPanel({ brief }: { brief: MacroDailyBrief | null }) {
  return (
    <MacroPanel
      ariaLabel="今日判断"
      className="macro-daily-brief-panel"
      meta={brief?.status ?? "missing"}
      span="full"
      title="今日判断"
    >
      <div className="macro-daily-brief">
        <strong>{brief?.headline ?? "今日判断暂不可用"}</strong>
        <div className="macro-daily-brief-grid">
          {(brief?.blocks ?? []).map((block) => (
            <article className="macro-daily-brief-block" key={block.id}>
              <span>{block.stance}</span>
              <b>{block.title}</b>
              <p>{block.body}</p>
            </article>
          ))}
        </div>
      </div>
    </MacroPanel>
  );
}

function normalizeDailyBrief(value: unknown): MacroDailyBrief | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const blocks = Array.isArray(record.blocks)
    ? record.blocks.flatMap((block) => normalizeDailyBriefBlock(block))
    : [];
  return {
    headline: String(record.headline ?? "今日判断暂不可用"),
    status: String(record.status ?? "unknown"),
    blocks,
  };
}

function normalizeDailyBriefBlock(value: unknown): MacroDailyBriefBlock[] {
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  const id = String(record.id ?? "").trim();
  const title = String(record.title ?? "").trim();
  const body = String(record.body ?? "").trim();
  if (!id || !title || !body) return [];
  return [
    {
      id,
      title,
      body,
      stance: String(record.stance ?? "neutral"),
    },
  ];
}

function sourceMeta(provenance: unknown): string {
  if (!provenance || typeof provenance !== "object") return "来源";
  const rows = (provenance as { rows?: unknown }).rows;
  if (!Array.isArray(rows)) return "来源";
  return `${rows.length} 个来源`;
}
