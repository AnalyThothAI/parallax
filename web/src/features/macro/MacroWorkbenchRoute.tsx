import * as PageState from "@shared/ui/PageState";

import { useMacroModuleQuery } from "./api/useMacroModuleQuery";
import type { MacroModuleId } from "./model/macroRoutes";
import { MacroAssetClassPage } from "./ui/pages/MacroAssetClassPage";
import { MacroAssetsLandingPage } from "./ui/pages/MacroAssetsLandingPage";
import { MacroCreditPage } from "./ui/pages/MacroCreditPage";
import { MacroCryptoDerivativesPage } from "./ui/pages/MacroCryptoDerivativesPage";
import { MacroEconomyPage } from "./ui/pages/MacroEconomyPage";
import { MacroFedPage } from "./ui/pages/MacroFedPage";
import { MacroLiquidityPage } from "./ui/pages/MacroLiquidityPage";
import { MacroOverviewPage } from "./ui/pages/MacroOverviewPage";
import { MacroRatesPage } from "./ui/pages/MacroRatesPage";
import { MacroVolatilityPage } from "./ui/pages/MacroVolatilityPage";
import { MacroShell } from "./ui/shell/MacroShell";

export function MacroWorkbenchRoute({
  moduleId,
  token,
}: {
  moduleId: MacroModuleId;
  token: string;
}) {
  const query = useMacroModuleQuery({ moduleId, token });
  const module = query.data ?? null;

  return (
    <section className="macro-module-route" aria-label="宏观">
      {query.isLoading ? <PageState.Loading layout="route" label="加载宏观模块" /> : null}
      {query.isError ? <PageState.Error error={query.error} /> : null}
      {module ? (
        <PageState.Stale updating={query.isFetching && !query.isLoading}>
          <MacroShell module={module} moduleId={moduleId}>
            <MacroModuleContent module={module} moduleId={moduleId} token={token} />
          </MacroShell>
        </PageState.Stale>
      ) : null}
    </section>
  );
}

function MacroModuleContent({
  module,
  moduleId,
  token,
}: {
  module: Parameters<typeof MacroOverviewPage>[0]["module"];
  moduleId: MacroModuleId;
  token: string;
}) {
  if (moduleId === "overview") {
    return <MacroOverviewPage module={module} moduleId={moduleId} token={token} />;
  }
  if (moduleId === "assets") {
    return <MacroAssetsLandingPage module={module} moduleId={moduleId} token={token} />;
  }
  if (moduleId.startsWith("assets/") && moduleId !== "assets/crypto-derivatives") {
    return <MacroAssetClassPage module={module} moduleId={moduleId} token={token} />;
  }
  if (moduleId === "assets/crypto-derivatives") {
    return <MacroCryptoDerivativesPage module={module} moduleId={moduleId} token={token} />;
  }
  if (moduleId.startsWith("rates")) {
    return <MacroRatesPage module={module} moduleId={moduleId} token={token} />;
  }
  if (moduleId.startsWith("fed")) {
    return <MacroFedPage module={module} moduleId={moduleId} token={token} />;
  }
  if (moduleId.startsWith("liquidity")) {
    return <MacroLiquidityPage module={module} moduleId={moduleId} token={token} />;
  }
  if (moduleId.startsWith("economy")) {
    return <MacroEconomyPage module={module} moduleId={moduleId} token={token} />;
  }
  if (moduleId.startsWith("volatility")) {
    return <MacroVolatilityPage module={module} moduleId={moduleId} token={token} />;
  }
  return <MacroCreditPage module={module} moduleId={moduleId} token={token} />;
}
