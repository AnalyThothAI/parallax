import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import type {
  ApiResponse,
  AssetFlowData,
  AssetFlowRow,
  LiveMarketUpdatePayload,
} from "../../api/types";

import { patchAssetFlowData, patchTokenRadarLiveMarketUpdate } from "./liveMarketUpdatePatch";

describe("liveMarketUpdatePatch", () => {
  it("patches matching token radar target rows", () => {
    const row = assetFlowRow("Asset", "asset:solana:token:abc");
    const other = assetFlowRow("Asset", "asset:solana:token:other");
    const data = assetFlowData({ targets: [row], attention: [other] });
    const update = liveMarketUpdate("Asset", "asset:solana:token:abc", 42);

    const patched = patchAssetFlowData(data, update);

    expect(patched.targets[0].live_market.price_usd).toBe(42);
    expect(patched.targets[0]).not.toBe(row);
    expect(patched.attention[0]).toBe(other);
  });

  it("keeps non-matching data referentially stable", () => {
    const data = assetFlowData({
      targets: [assetFlowRow("Asset", "asset:solana:token:abc")],
      attention: [],
    });

    const patched = patchAssetFlowData(
      data,
      liveMarketUpdate("Asset", "asset:solana:token:missing", 99),
    );

    expect(patched).toBe(data);
  });

  it("patches every cached token radar query with a matching target", () => {
    const queryClient = new QueryClient();
    const first = apiResponse(
      assetFlowData({ targets: [assetFlowRow("Asset", "asset:solana:token:abc")], attention: [] }),
    );
    const second = apiResponse(
      assetFlowData({ targets: [], attention: [assetFlowRow("Asset", "asset:solana:token:abc")] }),
    );
    const unrelated = apiResponse(
      assetFlowData({
        targets: [assetFlowRow("Asset", "asset:solana:token:other")],
        attention: [],
      }),
    );
    queryClient.setQueryData(["token-radar", "1h", "all"], first);
    queryClient.setQueryData(["token-radar", "5m", "all"], second);
    queryClient.setQueryData(["token-radar", "1h", "matched"], unrelated);

    patchTokenRadarLiveMarketUpdate(
      queryClient,
      liveMarketUpdate("Asset", "asset:solana:token:abc", 77),
    );

    expect(
      queryClient.getQueryData<ApiResponse<AssetFlowData>>(["token-radar", "1h", "all"])?.data
        .targets[0].live_market.price_usd,
    ).toBe(77);
    expect(
      queryClient.getQueryData<ApiResponse<AssetFlowData>>(["token-radar", "5m", "all"])?.data
        .attention[0].live_market.price_usd,
    ).toBe(77);
    expect(
      queryClient.getQueryData<ApiResponse<AssetFlowData>>(["token-radar", "1h", "matched"]),
    ).toBe(unrelated);
  });
});

function apiResponse(data: AssetFlowData): ApiResponse<AssetFlowData> {
  return { ok: true, data };
}

function assetFlowData({
  targets,
  attention,
}: {
  targets: AssetFlowRow[];
  attention: AssetFlowRow[];
}): AssetFlowData {
  return {
    window: "1h",
    scope: "all",
    generated_at_ms: 1,
    targets,
    attention,
    projection: {},
  } as unknown as AssetFlowData;
}

function assetFlowRow(targetType: string, targetId: string): AssetFlowRow {
  return {
    target: { target_type: targetType, target_id: targetId },
    live_market: {
      target_type: targetType,
      target_id: targetId,
      status: "missing",
    },
  } as unknown as AssetFlowRow;
}

function liveMarketUpdate(
  targetType: string,
  targetId: string,
  price: number,
): LiveMarketUpdatePayload {
  return {
    type: "live_market_update",
    target_type: targetType,
    target_id: targetId,
    live_market: {
      status: "live",
      price_usd: price,
      price_basis: "usd",
      observed_at_ms: 2,
      received_at_ms: 2,
      age_ms: 0,
      provider: "test",
    },
  };
}
