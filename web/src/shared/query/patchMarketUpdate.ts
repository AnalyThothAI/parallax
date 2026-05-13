import type {
  ApiResponse,
  AssetFlowData,
  AssetFlowRow,
  LiveMarketUpdatePayload,
} from "@lib/types";
import type { QueryClient } from "@tanstack/react-query";


import { queryKeys } from "./queryKeys";

export function patchTokenRadarLiveMarketUpdate(
  queryClient: QueryClient,
  update: LiveMarketUpdatePayload,
) {
  queryClient.setQueriesData<ApiResponse<AssetFlowData>>(
    { queryKey: queryKeys.tokenRadarRoot() },
    (response) => {
      if (!response?.data) {
        return response;
      }
      const data = patchAssetFlowData(response.data, update);
      return data === response.data ? response : { ...response, data };
    },
  );
}

export function patchAssetFlowData(
  data: AssetFlowData,
  update: LiveMarketUpdatePayload,
): AssetFlowData {
  const targets = patchAssetFlowRows(data.targets, update);
  const attention = patchAssetFlowRows(data.attention, update);
  if (targets === data.targets && attention === data.attention) {
    return data;
  }
  return { ...data, targets, attention };
}

export function patchAssetFlowRows(
  rows: AssetFlowRow[],
  update: LiveMarketUpdatePayload,
): AssetFlowRow[] {
  let changed = false;
  const next = rows.map((row) => {
    if (!assetFlowRowMatchesMarketUpdate(row, update)) {
      return row;
    }
    changed = true;
    return {
      ...row,
      market: {
        ...row.market,
        decision_latest: {
          target_type: update.target_type,
          target_id: update.target_id,
          ...update.market.decision_latest,
        },
        readiness: {
          ...row.market.readiness,
          latest_status: "live",
          stale_fields: (row.market.readiness.stale_fields ?? []).filter(
            (field) => field !== "decision_latest",
          ),
        },
      },
    };
  });
  return changed ? next : rows;
}

function assetFlowRowMatchesMarketUpdate(
  row: AssetFlowRow,
  update: LiveMarketUpdatePayload,
): boolean {
  return (
    row.target?.target_type === update.target_type && row.target?.target_id === update.target_id
  );
}
