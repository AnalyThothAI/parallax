import * as PageState from "@shared/ui/PageState";

import { useMacroOverviewQuery } from "../../api/useMacroPageQueries";
import { macroCodeLabel, macroEvidenceRefsLabel, macroLabel } from "../../model/macroDisplay";
import { MacroCatalystList, MacroCodeSummary, MacroFactGrid } from "../MacroDomainBlocks";
import { MacroDecisionList, MacroSection } from "../MacroEvidenceBlocks";
import { MacroPageShell } from "../MacroPageShell";

export function MacroOverviewPage({ token }: { token: string }) {
  const query = useMacroOverviewQuery({ token });

  if (query.isError) {
    return <PageState.Error error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (query.isLoading || !query.data) {
    return <PageState.Loading label="加载宏观总览证据" layout="route" />;
  }

  const data = query.data;
  const shock = data.dominant_shock;

  return (
    <PageState.Stale updating={query.isFetching && !query.isLoading}>
      <MacroPageShell
        data={data}
        pageId="overview"
        question="未来 1–4 周，哪个宏观冲击最需要被跨领域证据确认？"
        title="宏观证据总览"
      >
        <MacroSection eyebrow={macroLabel(shock.status)} title="主导冲击">
          <div className="macro-domain-card-grid">
            <MacroCodeSummary
              code={shock.candidate ?? "insufficient_evidence"}
              label="候选冲击"
              status={shock.status}
            />
            <MacroFactGrid
              facts={[
                {
                  code: shock.primary_trigger?.code,
                  label: "主要触发",
                  value: shock.primary_trigger
                    ? macroCodeLabel(shock.primary_trigger.code)
                    : "未建立",
                },
                {
                  label: "触发证据",
                  value: macroEvidenceRefsLabel(shock.primary_trigger?.evidence_refs ?? []),
                },
                {
                  label: "受影响暴露",
                  value: shock.affected_exposures.map(macroCodeLabel).join(" · ") || "无",
                },
                { label: "命中证据", value: macroEvidenceRefsLabel(shock.hit_evidence) },
                { label: "规则版本", value: shock.rule_version },
              ]}
            />
          </div>
          <div className="macro-decision-grid">
            <div>
              <h3>跨领域确认</h3>
              <MacroDecisionList
                emptyLabel="暂无跨领域确认。"
                items={shock.cross_domain_confirmations}
              />
            </div>
            <div>
              <h3>关键反证</h3>
              <MacroDecisionList
                emptyLabel="暂无关键反证。"
                items={shock.critical_contradictions}
              />
            </div>
          </div>
        </MacroSection>
        <MacroCatalystList items={data.official_catalysts} />
      </MacroPageShell>
    </PageState.Stale>
  );
}
