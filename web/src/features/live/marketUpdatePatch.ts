import type { QueryClient } from "@tanstack/react-query";
import type { ApiResponse, AssetFlowData, AssetFlowRow, MarketUpdatePayload } from "../../api/types";

export function patchTokenRadarMarketUpdate(queryClient: QueryClient, update: MarketUpdatePayload) {
  queryClient.setQueriesData<ApiResponse<AssetFlowData>>({ queryKey: ["token-radar"] }, (response) => {
    if (!response?.data) {
      return response;
    }
    const data = patchAssetFlowData(response.data, update);
    return data === response.data ? response : { ...response, data };
  });
}

export function patchAssetFlowData(data: AssetFlowData, update: MarketUpdatePayload): AssetFlowData {
  const targets = patchAssetFlowRows(data.targets, update);
  const attention = patchAssetFlowRows(data.attention, update);
  if (targets === data.targets && attention === data.attention) {
    return data;
  }
  return { ...data, targets, attention };
}

export function patchAssetFlowRows(rows: AssetFlowRow[], update: MarketUpdatePayload): AssetFlowRow[] {
  let changed = false;
  const next = rows.map((row) => {
    if (!assetFlowRowMatchesMarketUpdate(row, update)) {
      return row;
    }
    changed = true;
    return { ...row, current_market: update.current_market };
  });
  return changed ? next : rows;
}

function assetFlowRowMatchesMarketUpdate(row: AssetFlowRow, update: MarketUpdatePayload): boolean {
  return row.target?.target_type === update.target_type && row.target?.target_id === update.target_id;
}
