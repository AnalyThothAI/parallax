import { getApi } from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

import type {
  DailyMacroJudgmentReadData,
  MacroCreditData,
  MacroCrossAssetData,
  MacroGrowthLaborData,
  MacroLiquidityFundingData,
  MacroOverviewData,
  MacroRatesInflationData,
} from "../model/macroTypes";

export function useMacroOverviewQuery({ token }: { token: string }) {
  return useMacroPageQuery<MacroOverviewData>("overview", "/api/macro/overview", token);
}

export function useDailyMacroJudgmentQuery({ token }: { token: string }) {
  return useMacroPageQuery<DailyMacroJudgmentReadData>(
    "daily_judgment",
    "/api/macro/daily-judgment",
    token,
  );
}

export function useMacroCrossAssetQuery({ token }: { token: string }) {
  return useMacroPageQuery<MacroCrossAssetData>("cross_asset", "/api/macro/cross-asset", token);
}

export function useMacroRatesInflationQuery({ token }: { token: string }) {
  return useMacroPageQuery<MacroRatesInflationData>(
    "rates_inflation",
    "/api/macro/rates-inflation",
    token,
  );
}

export function useMacroGrowthLaborQuery({ token }: { token: string }) {
  return useMacroPageQuery<MacroGrowthLaborData>("growth_labor", "/api/macro/growth-labor", token);
}

export function useMacroLiquidityFundingQuery({ token }: { token: string }) {
  return useMacroPageQuery<MacroLiquidityFundingData>(
    "liquidity_funding",
    "/api/macro/liquidity-funding",
    token,
  );
}

export function useMacroCreditQuery({ token }: { token: string }) {
  return useMacroPageQuery<MacroCreditData>("credit", "/api/macro/credit", token);
}

function useMacroPageQuery<T>(pageId: string, path: string, token: string) {
  return useQuery({
    queryKey: queryKeys.macroPage(pageId),
    queryFn: async () => {
      const response = await getApi<T>(path, { token });
      return response.data;
    },
    enabled: Boolean(token),
    refetchInterval: 60_000,
  });
}
