import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import type { ApiResponse } from "../../api/types";
import type { AssetFlowData, AssetFlowRow, MarketUpdatePayload } from "../../api/types";
import {
  patchAssetFlowData,
  patchTokenRadarMarketUpdate
} from "./marketUpdatePatch";

describe("marketUpdatePatch", () => {
  it("patches matching token radar target rows", () => {
    const row = assetFlowRow("Asset", "asset:solana:token:abc");
    const other = assetFlowRow("Asset", "asset:solana:token:other");
    const data = assetFlowData({ targets: [row], attention: [other] });
    const update = marketUpdate("Asset", "asset:solana:token:abc", 42);

    const patched = patchAssetFlowData(data, update);

    expect(patched.targets[0].current_market.fields.price_usd.value).toBe(42);
    expect(patched.targets[0]).not.toBe(row);
    expect(patched.attention[0]).toBe(other);
  });

  it("keeps non-matching data referentially stable", () => {
    const data = assetFlowData({
      targets: [assetFlowRow("Asset", "asset:solana:token:abc")],
      attention: []
    });

    const patched = patchAssetFlowData(data, marketUpdate("Asset", "asset:solana:token:missing", 99));

    expect(patched).toBe(data);
  });

  it("patches every cached token radar query with a matching target", () => {
    const queryClient = new QueryClient();
    const first = apiResponse(assetFlowData({ targets: [assetFlowRow("Asset", "asset:solana:token:abc")], attention: [] }));
    const second = apiResponse(assetFlowData({ targets: [], attention: [assetFlowRow("Asset", "asset:solana:token:abc")] }));
    const unrelated = apiResponse(assetFlowData({ targets: [assetFlowRow("Asset", "asset:solana:token:other")], attention: [] }));
    queryClient.setQueryData(["token-radar", "1h", "all"], first);
    queryClient.setQueryData(["token-radar", "5m", "all"], second);
    queryClient.setQueryData(["token-radar", "1h", "matched"], unrelated);

    patchTokenRadarMarketUpdate(queryClient, marketUpdate("Asset", "asset:solana:token:abc", 77));

    expect((queryClient.getQueryData<ApiResponse<AssetFlowData>>(["token-radar", "1h", "all"])?.data.targets[0].current_market.fields.price_usd.value)).toBe(77);
    expect((queryClient.getQueryData<ApiResponse<AssetFlowData>>(["token-radar", "5m", "all"])?.data.attention[0].current_market.fields.price_usd.value)).toBe(77);
    expect(queryClient.getQueryData<ApiResponse<AssetFlowData>>(["token-radar", "1h", "matched"])).toBe(unrelated);
  });
});

function apiResponse(data: AssetFlowData): ApiResponse<AssetFlowData> {
  return { ok: true, data };
}

function assetFlowData({ targets, attention }: { targets: AssetFlowRow[]; attention: AssetFlowRow[] }): AssetFlowData {
  return {
    window: "1h",
    scope: "all",
    generated_at_ms: 1,
    targets,
    attention,
    projection: {}
  } as unknown as AssetFlowData;
}

function assetFlowRow(targetType: string, targetId: string): AssetFlowRow {
  return {
    target: { target_type: targetType, target_id: targetId },
    current_market: {
      target_type: targetType,
      target_id: targetId,
      market_status: "missing",
      fields: {}
    }
  } as unknown as AssetFlowRow;
}

function marketUpdate(targetType: string, targetId: string, price: number): MarketUpdatePayload {
  return {
    type: "market_update",
    target_type: targetType,
    target_id: targetId,
    current_market: {
      target_type: targetType,
      target_id: targetId,
      market_status: "fresh",
      fields: {
        price_usd: {
          value: price,
          status: "fresh",
          observed_at_ms: 2,
          age_ms: 0,
          provider: "test"
        }
      }
    }
  };
}
