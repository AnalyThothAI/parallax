import { RemoteState } from "@shared/ui/RemoteState";

import { useMacroModuleQuery } from "./api/useMacroModuleQuery";
import type { MacroModuleId } from "./model/macroRoutes";
import { MacroAssetClassPage } from "./ui/pages/MacroAssetClassPage";
import { MacroAssetsLandingPage } from "./ui/pages/MacroAssetsLandingPage";
import { MacroCreditPage } from "./ui/pages/MacroCreditPage";
import { MacroCryptoDerivativesPage } from "./ui/pages/MacroCryptoDerivativesPage";
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
      <h1>宏观</h1>
      {query.isLoading ? <RemoteState.Loading layout="route" label="加载宏观模块" /> : null}
      {query.isError ? <RemoteState.Error error={query.error} /> : null}
      {module ? (
        <RemoteState.Stale updating={query.isFetching && !query.isLoading}>
          <MacroShell module={module} moduleId={moduleId}>
            <MacroModuleContent module={module} moduleId={moduleId} token={token} />
          </MacroShell>
        </RemoteState.Stale>
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
  if (moduleId === "fed") {
    return <MacroFedPage module={module} moduleId={moduleId} token={token} />;
  }
  if (moduleId.startsWith("liquidity")) {
    return <MacroLiquidityPage module={module} moduleId={moduleId} token={token} />;
  }
  if (moduleId === "volatility") {
    return <MacroVolatilityPage module={module} moduleId={moduleId} token={token} />;
  }
  return <MacroCreditPage module={module} moduleId={moduleId} token={token} />;
}
