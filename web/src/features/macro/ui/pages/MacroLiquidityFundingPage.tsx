import * as PageState from "@shared/ui/PageState";

import { useMacroLiquidityFundingQuery } from "../../api/useMacroPageQueries";
import { MacroEvidenceList } from "../MacroEvidenceBlocks";
import { MacroPageShell } from "../MacroPageShell";

export function MacroLiquidityFundingPage({ token }: { token: string }) {
  const query = useMacroLiquidityFundingQuery({ token });

  if (query.isError) {
    return <PageState.Error error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (query.isLoading || !query.data) {
    return <PageState.Loading label="加载流动性与资金证据" layout="route" />;
  }

  const data = query.data;
  return (
    <PageState.Stale updating={query.isFetching && !query.isLoading}>
      <MacroPageShell
        data={data}
        pageId="liquidity_funding"
        question="央行资产负债表、准备金、财政现金与资金市场是否共同收紧？"
        title="流动性与资金"
      >
        <div className="macro-decision-grid">
          <MacroEvidenceList items={data.central_bank_balance_sheet} title="央行资产负债表" />
          <MacroEvidenceList items={data.reserves} title="准备金" />
          <MacroEvidenceList items={data.reverse_repo} title="逆回购" />
          <MacroEvidenceList items={data.treasury_cash} title="财政现金" />
        </div>
        <MacroEvidenceList items={[data.net_liquidity]} title="净流动性会计代理（不作因果判断）" />
        <div className="macro-decision-grid">
          <MacroEvidenceList items={data.secured_funding.evidence} title="有担保资金价格" />
          <MacroEvidenceList items={data.secured_funding.spreads} title="有担保资金利差" />
          <MacroEvidenceList items={data.unsecured_funding.evidence} title="无担保资金价格" />
          <MacroEvidenceList items={data.unsecured_funding.spreads} title="无担保资金利差" />
        </div>
      </MacroPageShell>
    </PageState.Stale>
  );
}
