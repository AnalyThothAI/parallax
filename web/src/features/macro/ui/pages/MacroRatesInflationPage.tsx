import * as PageState from "@shared/ui/PageState";

import { useMacroRatesInflationQuery } from "../../api/useMacroPageQueries";
import {
  formatMacroNumber,
  macroCapabilityLabel,
  macroEvidenceRefsLabel,
  macroLabel,
  macroReasonLabel,
  macroUnitLabel,
  macroWindowLabel,
} from "../../model/macroDisplay";
import { MacroCodeSummary, MacroFactGrid, MacroInflationReleaseList } from "../MacroDomainBlocks";
import { MacroEvidenceList, MacroSection } from "../MacroEvidenceBlocks";
import { MacroPageFrame } from "../MacroPageFrame";
import { MacroSeriesPanel } from "../MacroSeriesPanel";

export function MacroRatesInflationPage({ token }: { token: string }) {
  const query = useMacroRatesInflationQuery({ token });

  if (query.isError) {
    return <PageState.Error error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (query.isLoading || !query.data) {
    return <PageState.Loading label="加载利率与通胀证据" layout="route" />;
  }

  const data = query.data;
  const curve = data.curve_shape;
  const corridor = data.policy_funding_corridor;

  return (
    <PageState.Stale updating={query.isFetching && !query.isLoading}>
      <MacroPageFrame
        data={data}
        pageId="rates_inflation"
        question="名义利率、实际利率与通胀补偿分别在定价什么，曲线水平与曲线变化是否一致？"
        title="利率与通胀"
      >
        <MacroSeriesPanel
          conceptKeys={["rates:dgs2", "rates:dgs10", "rates:real_10y", "inflation:10y_breakeven"]}
          title="名义利率、实际利率与通胀补偿"
          token={token}
        />
        <MacroSection eyebrow={macroLabel(curve.status)} title="收益率曲线：水平与变化分开">
          <div className="macro-domain-card-grid">
            <MacroCodeSummary
              code={curve.level_classification}
              label="当前曲线水平"
              status={curve.status}
            />
            <MacroCodeSummary
              code={curve.move_classification}
              label="20 个交易日曲线变化"
              status={curve.status}
            />
          </div>
          <MacroFactGrid
            facts={[
              {
                label: "2Y 变化",
                value: `${formatMacroNumber(curve.two_year_change)} ${macroUnitLabel("percentage_points")}（percentage_points）`,
              },
              {
                label: "10Y 变化",
                value: `${formatMacroNumber(curve.ten_year_change)} ${macroUnitLabel("percentage_points")}（percentage_points）`,
              },
              {
                label: "变化窗口",
                value: `${macroWindowLabel(curve.change_window)}（${curve.change_window}）`,
              },
              { label: "证据引用", value: macroEvidenceRefsLabel(curve.evidence_refs) },
              { label: "规则版本", value: curve.rule_version },
            ]}
          />
        </MacroSection>

        <MacroEvidenceList items={data.nominal_curve} title="名义曲线与期限轴" />
        <MacroEvidenceList items={data.curve_slopes} title="曲线斜率" />
        <div className="macro-decision-grid">
          <MacroEvidenceList items={data.real_yields} title="实际利率" />
          <MacroEvidenceList items={data.breakevens} title="通胀盈亏平衡率" />
        </div>

        <MacroSection eyebrow={macroLabel(corridor.status)} title="政策与资金走廊">
          <MacroCodeSummary code={corridor.state} label="走廊状态" status={corridor.status} />
          <MacroFactGrid
            facts={[{ label: "证据引用", value: macroEvidenceRefsLabel(corridor.evidence_refs) }]}
          />
        </MacroSection>
        <div className="macro-decision-grid">
          <MacroEvidenceList items={corridor.evidence} title="政策利率与资金价格" />
          <MacroEvidenceList items={corridor.spreads} title="走廊利差" />
        </div>

        <MacroInflationReleaseList items={data.inflation_releases} />
        <MacroSection eyebrow="未评估 · 不计分" title="期限溢价">
          <MacroFactGrid
            facts={[
              {
                code: data.term_premium.capability,
                label: "能力",
                value: macroCapabilityLabel(data.term_premium.capability),
              },
              {
                code: data.term_premium.status,
                label: "状态",
                value: macroLabel(data.term_premium.status),
              },
              {
                code: data.term_premium.reason,
                label: "原因",
                value: macroReasonLabel(data.term_premium.reason),
              },
            ]}
          />
        </MacroSection>
      </MacroPageFrame>
    </PageState.Stale>
  );
}
