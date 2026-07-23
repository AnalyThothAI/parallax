import * as PageState from "@shared/ui/PageState";

import { useMacroGrowthLaborQuery } from "../../api/useMacroPageQueries";
import { MacroEvidenceList, MacroMetricList } from "../MacroEvidenceBlocks";
import { MacroPageFrame } from "../MacroPageFrame";
import { MacroSeriesPanel } from "../MacroSeriesPanel";

export function MacroGrowthLaborPage({ token }: { token: string }) {
  const query = useMacroGrowthLaborQuery({ token });

  if (query.isError) {
    return <PageState.Error error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (query.isLoading || !query.data) {
    return <PageState.Loading label="加载增长与就业证据" layout="route" />;
  }

  const data = query.data;
  return (
    <PageState.Stale updating={query.isFetching && !query.isLoading}>
      <MacroPageFrame
        data={data}
        pageId="growth_labor"
        question="增长与就业的领先指标是否已经得到滞后事实确认？"
        title="增长与就业"
      >
        <MacroSeriesPanel
          conceptKeys={[
            "labor:initial_claims",
            "labor:payrolls",
            "labor:unemployment",
            "economy:gdp_real",
          ]}
          title="领先与滞后增长信号"
          token={token}
        />
        <div className="macro-decision-grid">
          <MacroEvidenceList items={data.growth_leading} title="增长领先层" />
          <MacroEvidenceList items={data.growth_lagging} title="增长滞后层" />
          <MacroEvidenceList items={data.labor_leading} title="就业领先层" />
          <MacroEvidenceList items={data.labor_lagging} title="就业滞后层" />
        </div>
        <MacroMetricList items={data.growth_metrics} title="频率一致的增长指标" />
      </MacroPageFrame>
    </PageState.Stale>
  );
}
