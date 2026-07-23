import * as PageState from "@shared/ui/PageState";

import { useMacroCreditQuery } from "../../api/useMacroPageQueries";
import {
  formatMacroNumber,
  macroEvidenceRefsLabel,
  macroLabel,
  macroUnitLabel,
  macroWindowLabel,
} from "../../model/macroDisplay";
import { MacroCodeSummary, MacroFactGrid } from "../MacroDomainBlocks";
import { MacroEvidenceList, MacroSection } from "../MacroEvidenceBlocks";
import { MacroPageFrame } from "../MacroPageFrame";
import { MacroSeriesPanel } from "../MacroSeriesPanel";

export function MacroCreditPage({ token }: { token: string }) {
  const query = useMacroCreditQuery({ token });

  if (query.isError) {
    return <PageState.Error error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (query.isLoading || !query.data) {
    return <PageState.Loading label="加载信用证据" layout="route" />;
  }

  const data = query.data;
  const state = data.credit_state;
  const quadrant = data.treasury_spread_quadrant;

  return (
    <PageState.Stale updating={query.isFetching && !query.isLoading}>
      <MacroPageFrame
        data={data}
        pageId="credit"
        question="总量信用是否仍受控，低评级尾部是否正在向更高评级与融资供给扩散？"
        title="信用周期雷达"
      >
        <MacroSeriesPanel
          conceptKeys={[
            "credit:ig_oas",
            "credit:hy_oas",
            "derived:credit_ccc_minus_bb_oas",
            "credit:nfci",
          ]}
          title="总量利差、评级尾部与金融条件"
          token={token}
        />
        <MacroSection eyebrow={macroLabel(state.status)} title="信用状态：阶段与方向分开">
          <div className="macro-domain-card-grid">
            <MacroCodeSummary code={state.stage} label="阶段" status={state.status} />
            <MacroCodeSummary code={state.direction} label="方向" status={state.status} />
          </div>
          <MacroFactGrid
            facts={[
              { label: "证据引用", value: macroEvidenceRefsLabel(state.evidence_refs) },
              { label: "规则版本", value: state.rule_version },
            ]}
          />
        </MacroSection>

        <MacroSection eyebrow={macroLabel(quadrant.status)} title="国债收益率 × 信用利差">
          <MacroCodeSummary
            code={quadrant.quadrant}
            label="20 个交易日象限"
            status={quadrant.status}
          />
          <MacroFactGrid
            facts={[
              {
                label: "国债收益率变化",
                value: `${formatMacroNumber(quadrant.yield_change)} ${macroUnitLabel("percentage_points")}（percentage_points）`,
              },
              {
                label: "信用利差变化",
                value: `${formatMacroNumber(quadrant.spread_change)} ${macroUnitLabel("basis_points")}（basis_points）`,
              },
              {
                label: "变化窗口",
                value: `${macroWindowLabel(quadrant.change_window)}（${quadrant.change_window}）`,
              },
              { label: "证据引用", value: macroEvidenceRefsLabel(quadrant.evidence_refs) },
              { label: "规则版本", value: quadrant.rule_version },
            ]}
          />
        </MacroSection>

        <div className="macro-decision-grid" aria-label="信用六层证据">
          <MacroEvidenceList items={data.aggregate_spreads} title="1. 总量信用利差" />
          <MacroEvidenceList items={data.rating_tail} title="2. 评级尾部" />
          <MacroEvidenceList items={data.effective_yields} title="3. 企业有效融资成本" />
          <MacroEvidenceList items={data.credit_supply} title="4. 信贷供给" />
          <MacroEvidenceList items={data.realized_damage} title="5. 已实现贷款损伤" />
          <MacroEvidenceList
            items={data.financial_conditions_liquidity}
            title="6. 金融条件与信用流动性"
          />
        </div>
      </MacroPageFrame>
    </PageState.Stale>
  );
}
